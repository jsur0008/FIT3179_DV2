"""
Add Australian classification (au_certification) and cinema release dates (au_release_date,
us_release_date) to a horror_movies.csv you already pulled.

One small TMDB call per film (/movie/{id}/release_dates). Your original CSV is not modified.

    pip install requests
    export TMDB_API_KEY="your key"
    python add_au_certification.py data/horror_movies.csv

Output: horror_movies_au.csv next to the input, plus au_cache.jsonl (resume cache; rerun to continue).
Attribution: "This product uses the TMDB API but is not endorsed or certified by TMDB."
"""
import csv
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

BASE = "https://api.themoviedb.org/3"
RAW_KEY = os.environ.get("TMDB_API_KEY", "f2afbf32d115ea62a7d9be9bcdfabb92").strip()
if not RAW_KEY:
    sys.exit("Set TMDB_API_KEY first (export TMDB_API_KEY=...)")

SRC = sys.argv[1] if len(sys.argv) > 1 else "data/horror_movies.csv"
DST = os.path.splitext(SRC)[0] + "_au.csv"
CACHE = "au_cache.jsonl"
WORKERS = int(os.environ.get("WORKERS", 8))

session = requests.Session()
if RAW_KEY.startswith("eyJ"):  # v4 bearer token
    session.headers["Authorization"] = f"Bearer {RAW_KEY}"
    AUTH = {}
else:  # v3 api key
    AUTH = {"api_key": RAW_KEY}


def fetch_release_dates(movie_id):
    """The JSON, {} if TMDB has no such film (404), or None if the request kept failing."""
    for attempt in range(6):
        try:
            r = session.get(f"{BASE}/movie/{movie_id}/release_dates", params=AUTH, timeout=30)
            if r.status_code == 429:
                time.sleep(int(r.headers.get("Retry-After", 2)) + attempt)
                continue
            if r.status_code == 404:
                return {}
            r.raise_for_status()
            return r.json()
        except requests.RequestException:
            time.sleep(1.5 * (attempt + 1))
    return None


def au_certification(data):
    """First non-empty Australian classification, or '' if there isn't one."""
    for entry in data.get("results", []):
        if entry.get("iso_3166_1") == "AU":
            certs = [x["certification"] for x in entry.get("release_dates", []) if x.get("certification")]
            return certs[0] if certs else ""
    return ""


def cinema_date(data, country):
    """Earliest theatrical release date (TMDB types 2 and 3) for a country, as YYYY-MM-DD, or ''."""
    dates = []
    for entry in data.get("results", []):
        if entry.get("iso_3166_1") == country:
            for x in entry.get("release_dates", []):
                if x.get("type") in (2, 3) and x.get("release_date"):
                    dates.append(x["release_date"][:10])
    return min(dates) if dates else ""


def load_cache():
    """Rows from an older run (no dates stored) are ignored, so those films are looked up again."""
    cache = {}
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                    if "au_date" in row:
                        cache[str(row["id"])] = row
                except (json.JSONDecodeError, KeyError):
                    pass
    return cache


def main():
    with open(SRC, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        rows = list(reader)
    if "id" not in fieldnames:
        sys.exit(f"{SRC} has no 'id' column")

    cache = load_cache()
    todo = [r["id"] for r in rows if r["id"] not in cache]
    print(f"{len(rows)} films; {len(cache)} already done; looking up {len(todo)}...", flush=True)

    with open(CACHE, "a", encoding="utf-8") as cf, ThreadPoolExecutor(WORKERS) as pool:
        futures = {pool.submit(fetch_release_dates, i): i for i in todo}
        for n, fut in enumerate(as_completed(futures), 1):
            movie_id, data = futures[fut], fut.result()
            if data is not None:  # failed lookups are not cached, so a rerun retries them
                cache[movie_id] = {"id": movie_id, "au": au_certification(data),
                                   "au_date": cinema_date(data, "AU"), "us_date": cinema_date(data, "US")}
                cf.write(json.dumps(cache[movie_id]) + "\n")
            if n % 500 == 0:
                cf.flush()
                print(f"  {n}/{len(todo)}", flush=True)

    for col in ("au_certification", "au_release_date", "us_release_date"):
        if col not in fieldnames:
            fieldnames.append(col)
    with open(DST, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            c = cache.get(r["id"], {})
            r["au_certification"] = c.get("au", "")
            r["au_release_date"] = c.get("au_date", "")
            r["us_release_date"] = c.get("us_date", "")
            w.writerow(r)

    missing = sum(1 for r in rows if r["id"] not in cache)
    with_cert = sum(1 for r in rows if cache.get(r["id"], {}).get("au"))
    with_au_date = sum(1 for r in rows if cache.get(r["id"], {}).get("au_date"))
    with_us_date = sum(1 for r in rows if cache.get(r["id"], {}).get("us_date"))
    print(f"\nDone: {DST}")
    print(f"{with_cert} of {len(rows)} films have an Australian classification "
          f"(the rest have none listed on TMDB).")
    print(f"{with_au_date} have an Australian cinema release date, {with_us_date} a US one.")
    if missing:
        print(f"{missing} lookups failed - rerun the script to retry just those.")


if __name__ == "__main__":
    main()