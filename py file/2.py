"""
Pull ALL horror films from TMDB into raw CSVs (no averaging, no filtering by votes).

Setup:
    pip install requests
    export TMDB_API_KEY="your key"        # v3 key or v4 read-access token both work
    python tmdb_horror.py

Optional env vars:
    START_YEAR (default 1900)   END_YEAR (default current year)
    MIN_VOTES  (default 0)      keep every film, including ones nobody has rated
    WORKERS    (default 8)      parallel detail requests

Outputs:
    horror_movies.csv      one row per horror film, raw values only
    baseline_by_year.csv   all-genre vs horror film counts per year (counts only)
    cache_details.jsonl    resume cache - delete it to force a fresh pull

Country columns:
    origin_country       TMDB's "origin country" field for the film
    production_countries countries of the production companies (kept for comparison)

TMDB limits handled here:
    - discover only pages through the first 10,000 results of a query, so big date
      ranges are split in half until each piece fits.
    - discover reports total_results as 20001 once the true count is higher, so counts
      are also made by splitting the date range and adding the pieces up.

Attribution: "This product uses the TMDB API but is not endorsed or certified by TMDB."
"""
import csv
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta

import requests

BASE = "https://api.themoviedb.org/3"
RAW_KEY = os.environ.get("TMDB_API_KEY", "f2afbf32d115ea62a7d9be9bcdfabb92").strip()
if not RAW_KEY:
    sys.exit("Set TMDB_API_KEY first (export TMDB_API_KEY=...)")

START_YEAR = int(os.environ.get("START_YEAR", 1900))
END_YEAR = int(os.environ.get("END_YEAR", date.today().year))
MIN_VOTES = int(os.environ.get("MIN_VOTES", 0))
WORKERS = int(os.environ.get("WORKERS", 8))
HORROR = 27
CACHE = "cache_details.jsonl"
PAGE_LIMIT_RESULTS = 10_000   # 500 pages x 20 results is all discover will page through
COUNT_CAP = 20_000            # total_results shows 20001 when the real count is above this

FIELDS = [
    "id", "imdb_id", "title", "original_title", "release_date", "year", "decade",
    "original_language", "spoken_languages",
    "origin_country", "production_countries", "production_country_names",
    "vote_average", "vote_count", "popularity", "runtime",
    "budget", "revenue", "genres", "is_horror_only",
    "companies", "keywords", "us_certification", "status", "adult",
]

session = requests.Session()
if RAW_KEY.startswith("eyJ"):  # v4 bearer token
    session.headers["Authorization"] = f"Bearer {RAW_KEY}"
    AUTH = {}
else:  # v3 api key
    AUTH = {"api_key": RAW_KEY}


def get(path, **params):
    """GET with retry/backoff (handles 429 rate limits and transient errors)."""
    params = {**AUTH, **params}
    for attempt in range(6):
        try:
            r = session.get(f"{BASE}{path}", params=params, timeout=30)
            if r.status_code == 429:
                time.sleep(int(r.headers.get("Retry-After", 2)) + attempt)
                continue
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            time.sleep(1.5 * (attempt + 1))
    return None


def range_params(start, end, genre=None, page=1):
    params = {
        "include_adult": "false",
        "sort_by": "primary_release_date.asc",
        "primary_release_date.gte": start.isoformat(),
        "primary_release_date.lte": end.isoformat(),
        "page": page,
    }
    if MIN_VOTES > 0:
        params["vote_count.gte"] = MIN_VOTES
    if genre:
        params["with_genres"] = genre
    return params


def split(start, end):
    mid = start + (end - start) // 2
    return (start, mid), (mid + timedelta(days=1), end)


def count_range(start, end, genre=None):
    """True count of films in a date range, splitting when TMDB's capped total shows up."""
    if start > end:
        return 0
    first = get("/discover/movie", **range_params(start, end, genre))
    total = first["total_results"] if first else 0
    if total < COUNT_CAP or start >= end:
        return total
    left, right = split(start, end)
    return count_range(*left, genre) + count_range(*right, genre)


def fetch_range(start, end, genre=None):
    """Every film in a date range; splits the range if it holds more than discover will page through."""
    if start > end:
        return []
    first = get("/discover/movie", **range_params(start, end, genre))
    if not first:
        return []
    if first["total_results"] > PAGE_LIMIT_RESULTS and start < end:
        left, right = split(start, end)
        return fetch_range(*left, genre) + fetch_range(*right, genre)
    results = list(first["results"])
    for p in range(2, min(first["total_pages"], 500) + 1):
        data = get("/discover/movie", **range_params(start, end, genre, page=p))
        if data:
            results.extend(data["results"])
    return results


def fetch_details(movie_id):
    # one call gets details + keywords + release dates (for age certification)
    return get(f"/movie/{movie_id}", append_to_response="keywords,release_dates")


def us_certification(d):
    try:
        for entry in d["release_dates"]["results"]:
            if entry["iso_3166_1"] == "US":
                certs = [x["certification"] for x in entry["release_dates"] if x["certification"]]
                return certs[0] if certs else ""
    except (KeyError, TypeError):
        pass
    return ""


def flatten(d):
    """Raw values only. Budget/revenue of 0 are left as 0 (TMDB's own value) - decide how to treat later."""
    rd = d.get("release_date") or ""
    year = int(rd[:4]) if rd[:4].isdigit() else ""
    countries = d.get("production_countries") or []
    return {
        "id": d["id"],
        "imdb_id": d.get("imdb_id") or "",
        "title": d.get("title"),
        "original_title": d.get("original_title"),
        "release_date": rd,
        "year": year,
        "decade": f"{year // 10 * 10}s" if year != "" else "",
        "original_language": d.get("original_language"),
        "spoken_languages": "|".join(l["iso_639_1"] for l in d.get("spoken_languages") or []),
        "origin_country": "|".join(d.get("origin_country") or []),
        "production_countries": "|".join(c["iso_3166_1"] for c in countries),
        "production_country_names": "|".join(c["name"] for c in countries),
        "vote_average": d.get("vote_average"),
        "vote_count": d.get("vote_count"),
        "popularity": d.get("popularity"),
        "runtime": d.get("runtime"),
        "budget": d.get("budget"),
        "revenue": d.get("revenue"),
        "genres": "|".join(g["name"] for g in d.get("genres") or []),
        "is_horror_only": len(d.get("genres") or []) == 1,
        "companies": "|".join(c["name"] for c in d.get("production_companies") or []),
        "keywords": "|".join(k["name"] for k in (d.get("keywords") or {}).get("keywords", [])),
        "us_certification": us_certification(d),
        "status": d.get("status"),
        "adult": d.get("adult"),
    }


def load_cache():
    cache = {}
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                    cache[row["id"]] = row
                except (json.JSONDecodeError, KeyError):
                    pass
    return cache


def main():
    # 1. Discover horror film ids per year + true counts
    horror_ids, baseline = set(), []
    for year in range(START_YEAR, END_YEAR + 1):
        start, end = date(year, 1, 1), date(year, 12, 31)
        found = {r["id"] for r in fetch_range(start, end, HORROR)}
        horror_ids.update(found)
        horror_total = count_range(start, end, HORROR)
        all_total = count_range(start, end)
        baseline.append({"year": year, "horror_films": horror_total, "all_films": all_total})
        note = "" if len(found) == horror_total else f"  (fetched {len(found)}, check)"
        print(f"{year}: {horror_total} horror / {all_total} total{note}", flush=True)

    with open("baseline_by_year.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["year", "horror_films", "all_films"])
        w.writeheader()
        w.writerows(baseline)

    # 2. Fetch details (resumable)
    cache = load_cache()
    todo = [i for i in horror_ids if i not in cache]
    print(f"\n{len(horror_ids)} horror films; {len(cache)} cached; fetching {len(todo)} details...", flush=True)

    with open(CACHE, "a", encoding="utf-8") as cf, ThreadPoolExecutor(WORKERS) as pool:
        futures = {pool.submit(fetch_details, i): i for i in todo}
        for n, fut in enumerate(as_completed(futures), 1):
            d = fut.result()
            if d:
                row = flatten(d)
                cache[row["id"]] = row
                cf.write(json.dumps(row, ensure_ascii=False) + "\n")
            if n % 200 == 0:
                cf.flush()
                print(f"  {n}/{len(todo)}", flush=True)

    # 3. Write final CSV - every horror film found, nothing dropped
    rows = [cache[i] for i in horror_ids if i in cache]
    rows.sort(key=lambda r: (str(r.get("release_date") or ""), r["id"]))
    with open("horror_movies.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore", restval="")
        w.writeheader()
        w.writerows(rows)
    missing = len(horror_ids) - len(rows)
    print(f"\nDone: {len(rows)} films -> horror_movies.csv, baseline_by_year.csv"
          + (f" ({missing} detail lookups failed - rerun to retry them)" if missing else ""))


if __name__ == "__main__":
    main()