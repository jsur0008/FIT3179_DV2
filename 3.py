"""
Prepare the Oscars chart data: horror's share of films vs its share of Oscar nominations, per decade.

Two ways to decide which nominated films are horror (both use TMDB's "Horror" genre tag):

  --lookup   (no big pull needed)  Asks TMDB about ONLY the ~5,000 nominated films, using their IMDb
             ids from the Oscars file. Needs TMDB_API_KEY. Takes a few minutes; resumable.
  default    Uses your finished horror CSV (matched on its imdb_id column).

Inputs (defaults in brackets):
    --oscars   Academy Awards 'full_data.csv' (tab-separated)   [full_data.csv]
    --films    decade totals from genre_counts_by_decade.py     [genre_counts_by_decade.csv]
               (needs columns: decade, all_films, Horror)
    --horror   TMDB horror CSV with imdb_id (CSV mode only)     [horror_movies.csv]

Outputs:
    oscars_horror_by_decade.csv    one row per decade -> the dumbbell chart
    oscars_horror_milestones.csv   one row per nominated horror film -> the milestone chart
    oscar_genres_cache.jsonl       (lookup mode) saved TMDB answers; rerun to resume

Technical (SciTech) and honorary (Special) awards are skipped, because they are not competitions
between films. A nomination is counted once per credited film (a handful of 1920s-30s nominations
credit several films).

Usage:
    export TMDB_API_KEY="your key"
    python prep_oscars.py --lookup
    python prep_oscars.py --horror horror_movies_au.csv        # CSV mode
"""
import argparse
import csv
import json
import os
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed

ap = argparse.ArgumentParser()
ap.add_argument("--lookup", action="store_true", help="look up genres on TMDB for the nominated films only")
ap.add_argument("--horror", default="data/horror_movies.csv")
ap.add_argument("--oscars", default="data/full_data.csv")
ap.add_argument("--films", default="data/genre_counts_by_decade.csv")
args = ap.parse_args()

SKIP_CLASSES = {"SciTech", "Special"}
HORROR_GENRE_ID = 27
CACHE = "oscar_genres_cache.jsonl"

# --- Oscar nominations (one entry per nomination per credited film) -----------------------------
nominations = []          # (film_id, film_year, won)
film_title = {}
with open(args.oscars, newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f, delimiter="\t"):
        if r["Class"] in SKIP_CLASSES or not r["FilmId"]:
            continue
        year = int(r["Year"][:4])               # "1927/28" -> 1927 (the film year)
        ids, names = r["FilmId"].split("|"), r["Film"].split("|")
        for film_id, name in zip(ids, names):
            film_title.setdefault(film_id, name)
            nominations.append((film_id, year, r["Winner"] == "True"))
nominated_ids = sorted({n[0] for n in nominations})
print(f"{len(nominations)} nominations across {len(nominated_ids)} films")


# --- which nominated films are horror -----------------------------------------------------------
def horror_from_csv():
    ids, no_imdb = set(), 0
    with open(args.horror, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r.get("imdb_id"):
                ids.add(r["imdb_id"])
            else:
                no_imdb += 1
    print(f"{len(ids)} horror films with an IMDb id in the CSV ({no_imdb} without one can't be matched)")
    return ids


def tmdb_find(imdb_id, session, auth):
    """Genre ids TMDB gives this IMDb id, [] if it has none, None if the request kept failing."""
    for attempt in range(6):
        try:
            r = session.get(f"https://api.themoviedb.org/3/find/{imdb_id}",
                            params={**auth, "external_source": "imdb_id"}, timeout=30)
            if r.status_code == 429:
                time.sleep(int(r.headers.get("Retry-After", 2)) + attempt)
                continue
            r.raise_for_status()
            movies = r.json().get("movie_results", [])
            return movies[0].get("genre_ids", []) if movies else []
        except Exception:
            time.sleep(1.5 * (attempt + 1))
    return None


def horror_from_tmdb(film_ids):
    import requests
    key = os.environ.get("TMDB_API_KEY", "").strip()
    if not key:
        sys.exit("Set TMDB_API_KEY first (export TMDB_API_KEY=...) or run without --lookup")
    session, auth = requests.Session(), {}
    if key.startswith("eyJ"):
        session.headers["Authorization"] = f"Bearer {key}"
    else:
        auth = {"api_key": key}

    genres = {}
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            for line in f:
                try:
                    row = json.loads(line)
                    genres[row["id"]] = row["genres"]
                except (json.JSONDecodeError, KeyError):
                    pass
    todo = [i for i in film_ids if i not in genres]
    print(f"{len(genres)} films already looked up; asking TMDB about {len(todo)}...", flush=True)

    with open(CACHE, "a", encoding="utf-8") as cf, ThreadPoolExecutor(8) as pool:
        futures = {pool.submit(tmdb_find, i, session, auth): i for i in todo}
        for n, fut in enumerate(as_completed(futures), 1):
            film_id, result = futures[fut], fut.result()
            if result is not None:               # failures aren't cached, so a rerun retries them
                genres[film_id] = result
                cf.write(json.dumps({"id": film_id, "genres": result}) + "\n")
            if n % 250 == 0:
                cf.flush()
                print(f"  {n}/{len(todo)}", flush=True)

    failed = [i for i in film_ids if i not in genres]
    if failed:
        print(f"WARNING: {len(failed)} lookups failed - rerun to retry them.")
    not_found = sum(1 for i in film_ids if genres.get(i) == [])
    print(f"{not_found} films have no genres on TMDB (counted as not horror).")
    return {i for i, g in genres.items() if HORROR_GENRE_ID in g}


horror_ids = horror_from_tmdb(nominated_ids) if args.lookup else horror_from_csv()
horror_nominated = {i for i in nominated_ids if i in horror_ids}
print(f"{len(horror_nominated)} nominated films are horror")

# --- aggregate per decade ------------------------------------------------------------------------
tot_noms, hor_noms, hor_wins = defaultdict(int), defaultdict(int), defaultdict(int)
film_stats = defaultdict(lambda: {"year": None, "noms": 0, "wins": 0})
for film_id, year, won in nominations:
    decade = f"{year // 10 * 10}s"
    tot_noms[decade] += 1
    if film_id in horror_ids:
        hor_noms[decade] += 1
        hor_wins[decade] += won
        s = film_stats[film_id]
        s["year"], s["noms"], s["wins"] = year, s["noms"] + 1, s["wins"] + won

# --- film totals per decade (from the TMDB counts) ----------------------------------------------
film_totals = {}
with open(args.films, newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        film_totals[r["decade"]] = (int(r["Horror"]), int(r["all_films"]))

rows = []
for decade in sorted(tot_noms):
    h_films, all_films = film_totals.get(decade, (None, None))
    rows.append({
        "decade": decade,
        "films_pct": round(100 * h_films / all_films, 2) if all_films else "",
        "noms_pct": round(100 * hor_noms[decade] / tot_noms[decade], 2),
        "horror_films": h_films if h_films is not None else "",
        "all_films": all_films if all_films is not None else "",
        "horror_noms": hor_noms[decade],
        "total_noms": tot_noms[decade],
        "horror_wins": hor_wins[decade],
    })

with open("oscars_horror_by_decade.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)

miles = sorted(
    ({"imdb_id": i, "title": film_title[i], "year": s["year"], "nominations": s["noms"], "wins": s["wins"]}
     for i, s in film_stats.items()),
    key=lambda m: (m["year"], m["title"]))
with open("oscars_horror_milestones.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["imdb_id", "title", "year", "nominations", "wins"])
    w.writeheader()
    w.writerows(miles)

print(f"\n{'decade':<7}{'films %':>9}{'noms %':>9}{'horror noms':>13}{'of':>6}")
for r in rows:
    print(f"{r['decade']:<7}{str(r['films_pct']):>9}{r['noms_pct']:>9}{r['horror_noms']:>13}{r['total_noms']:>6}")
print(f"\n{len(miles)} horror films have at least one nomination -> oscars_horror_milestones.csv")
missing = [r["decade"] for r in rows if r["films_pct"] == ""]
if missing:
    print("No film totals for:", ", ".join(missing), "(check your genre_counts file)")