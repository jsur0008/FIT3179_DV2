"""
Count films per GENRE per DECADE using TMDB, and chart how horror has grown.

TMDB's discover endpoint caps total_results at 20,001, so any decade/genre with
more films than that is split into smaller date ranges and the pieces are added up.
That gives true counts instead of "20001".

Setup:
    pip install requests matplotlib
    export TMDB_API_KEY=yourkey      (Windows: set TMDB_API_KEY=yourkey)
    python genre_counts_by_decade.py

Outputs:
    genre_counts_by_decade.csv   one row per decade, one column per genre
    horror_growth.png            horror count + horror share of all films

Notes:
  - A film with several genres is counted in each of them, so genre columns add up
    to more than "all_films".
  - Release dates in the future (unreleased/announced films) are included in the 2020s.
    Set END_DATE below to cut off at today if you want released films only.
  - Raise MIN_VOTES (e.g. 5) to count only films with some audience.
"""
import csv
import os
import time
from datetime import date, timedelta

import matplotlib.pyplot as plt
import requests

API_KEY = os.environ.get("TMDB_API_KEY", "f2afbf32d115ea62a7d9be9bcdfabb92")
BASE = "https://api.themoviedb.org/3"
DECADES = list(range(1890, 2030, 10))
MIN_VOTES = 0
END_DATE = date(2026, 12, 31)   # e.g. date.today() to exclude unreleased films
COUNT_CAP = 20000               # TMDB reports 20001 once the true count is above this

CALLS = 0


def api(path, **params):
    global CALLS
    params["api_key"] = API_KEY
    for attempt in range(6):
        r = requests.get(BASE + path, params=params, timeout=30)
        if r.status_code == 429:
            time.sleep(2 * (attempt + 1))
            continue
        if r.status_code == 401:
            raise SystemExit("TMDB rejected the API key. Check TMDB_API_KEY.")
        r.raise_for_status()
        CALLS += 1
        return r.json()
    raise RuntimeError(f"Too many retries for {path}")


def count_range(start, end, genre_id=None):
    """True number of films released start..end (inclusive), splitting when TMDB's cap is hit."""
    if start > end:
        return 0
    params = {
        "primary_release_date.gte": start.isoformat(),
        "primary_release_date.lte": end.isoformat(),
        "include_adult": "false",
        "page": 1,
    }
    if MIN_VOTES > 0:
        params["vote_count.gte"] = MIN_VOTES
    if genre_id:
        params["with_genres"] = genre_id
    time.sleep(0.03)
    total = api("/discover/movie", **params)["total_results"]
    if total < COUNT_CAP or start >= end:
        if total >= COUNT_CAP:
            print(f"  WARNING: {start} alone is over the cap; count is a minimum")
        return total
    mid = start + (end - start) // 2
    return count_range(start, mid, genre_id) + count_range(mid + timedelta(days=1), end, genre_id)


def main():
    genres = api("/genre/movie/list")["genres"]
    names = [g["name"] for g in genres]
    rows = []

    for decade in DECADES:
        start, end = date(decade, 1, 1), min(date(decade + 9, 12, 31), END_DATE)
        if start > END_DATE:
            continue
        row = {"decade": f"{decade}s", "all_films": count_range(start, end)}
        for g in genres:
            row[g["name"]] = count_range(start, end, g["id"])
        total = row["all_films"]
        row["horror_share_pct"] = round(100 * row["Horror"] / total, 2) if total else 0
        rows.append(row)
        print(f"{row['decade']}: {total:>7} films, {row['Horror']:>6} horror "
              f"({row['horror_share_pct']}%)   [{CALLS} API calls so far]", flush=True)

    fields = ["decade", "all_films"] + names + ["horror_share_pct"]
    with open("genre_counts_by_decade.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print("Saved genre_counts_by_decade.csv")

    rows = [r for r in rows if r["all_films"] > 0]
    labels = [r["decade"] for r in rows]
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 8), sharex=True)
    ax1.bar(labels, [r["Horror"] for r in rows], color="#8b1a1a")
    ax1.set_ylabel("Horror films")
    ax1.set_title("Horror films per decade (TMDB)")
    ax2.plot(labels, [r["horror_share_pct"] for r in rows], marker="o", color="#8b1a1a")
    ax2.set_ylabel("% of all films")
    ax2.set_title("Horror as a share of all films")
    plt.setp(ax2.get_xticklabels(), rotation=45)
    fig.tight_layout()
    fig.savefig("horror_growth.png", dpi=150)
    print("Saved horror_growth.png")


if __name__ == "__main__":
    main()