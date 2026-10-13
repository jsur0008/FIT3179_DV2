"""
Prepare the 'horror films by country and year' map data from your TMDB horror CSV.

Reads horror_movies.csv (needs columns origin_country and year) and writes
horror_by_country_year.csv with one row per (country, year): how many horror films
that country was an origin of. The big CSV stays on your computer; only this small file
goes on the page.

Setup:
    pip install pycountry        # turns country codes (AU) into the numbers the map uses (36)

Usage:
    python3 prep_country_map.py                       # reads horror_movies.csv
    python3 prep_country_map.py path/to/horror_movies.csv
    python3 prep_country_map.py --no-fold             # keep old countries (USSR etc.) out of the map

How the counting works:
  - A film with several origin countries (for example "US|GB") counts once for EACH of them,
    so the country totals add up to more than the number of films.
  - Films with no origin country are left out (the script says how many).
  - Old countries that no longer exist are folded into their main successor by default
    (SU->Russia, DD/XG->Germany, YU/CS->Serbia, XC->Czechia). This is a simplification, so
    say so on the page, or use --no-fold to drop them instead.
  - The world map has no shape for some very small places (Hong Kong, Singapore, ...). Their
    films are in the CSV but cannot be drawn. Put world-110m.json in the same folder and the
    script will list which countries are affected.
"""
import csv
import json
import sys
from collections import Counter, defaultdict

try:
    import pycountry
except ImportError:
    sys.exit("This script needs pycountry:  pip install pycountry")

args = [a for a in sys.argv[1:] if not a.startswith("--")]
SRC = args[0] if args else "data/horror_movies.csv"
FOLD = "--no-fold" not in sys.argv

HISTORICAL = {"SU": "RU", "DD": "DE", "XG": "DE", "YU": "RS", "CS": "RS", "XC": "CZ"}
# Which countries the map can draw: read from world-110m.json if it is in this folder (you need
# that file for the page anyway). Without it the script just skips the "no shape" report.
DRAWABLE = None
try:
    topo = json.load(open("data/world-110m.json", encoding="utf-8"))
    DRAWABLE = {int(g["id"]) for g in topo["objects"]["countries"]["geometries"] if "id" in g}
except (OSError, ValueError, KeyError):
    pass

counts = Counter()
total = no_country = no_year = folded = dropped_old = 0
undrawable = Counter()
with open(SRC, newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        total += 1
        year = (r.get("year") or "").strip()
        if not year.isdigit():
            no_year += 1
            continue
        codes = [c for c in (r.get("origin_country") or "").split("|") if c]
        if not codes:
            no_country += 1
            continue
        yr = int(year)
        for code in set(codes):
            if code in HISTORICAL:
                if not FOLD:
                    dropped_old += 1
                    continue
                code = HISTORICAL[code]
                folded += 1
            counts[(code, yr)] += 1

rows, bad_codes = [], Counter()
for (code, yr), n in counts.items():
    c = pycountry.countries.get(alpha_2=code)
    if c is None:
        bad_codes[code] += n
        continue
    num = int(c.numeric)
    if DRAWABLE is not None and num not in DRAWABLE:
        undrawable[c.name] += n
    rows.append({"id": num, "code": code, "country": getattr(c, "common_name", c.name),
                 "year": yr, "films": n})

# Places with no shape in the 110m world file get hand-entered points (approximate).
EXTRA = {
    "HK": (22.32, 114.17), "SG": (1.35, 103.82), "MT": (35.90, 14.45),
    "KM": (-11.70, 43.30), "MV": (3.20, 73.20), "BH": (26.07, 50.55),
    "AD": (42.55, 1.58),   "FO": (62.00, -6.80),
}

cent = {}
with open("data/country_centroids.csv", newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        cent[r["iso2"]] = (float(r["lat"]), float(r["lon"]))
for code, (lat, lon) in EXTRA.items():
    cent.setdefault(code, (lat, lon))      # keep the file's value if it has one

lost = Counter()
for r in rows:
    r["lat"], r["lon"] = cent.get(r["code"], ("", ""))
    if r["lat"] == "":
        lost[r["country"]] += r["films"]
rows = [r for r in rows if r["lat"] != ""]
if lost:
    print(f"\nNo point for these countries, so no circle ({sum(lost.values()):,} entries):",
          dict(lost.most_common(8)))

rows.sort(key=lambda r: (r["year"], -r["films"]))
with open("horror_by_country_year.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["id", "code", "country", "year", "films", "lat", "lon"])
    w.writeheader()
    w.writerows(rows)

used = total - no_country - no_year
print(f"{total:,} films read: {used:,} have an origin country and a year "
      f"({no_country:,} without a country, {no_year:,} without a year were left out)")
if FOLD:
    print(f"{folded:,} film-country entries from old countries were folded into their successors")
else:
    print(f"{dropped_old:,} film-country entries from old countries were dropped (--no-fold)")
if bad_codes:
    print("Codes pycountry did not recognise (left out):", dict(bad_codes.most_common(10)))
if undrawable:
    print(f"\nIn the CSV but with no shape on the map ({sum(undrawable.values()):,} entries):")
    for name, n in undrawable.most_common(8):
        print(f"   {name}: {n:,}")
by_country = Counter()
for r in rows:
    by_country[r["country"]] += r["films"]
print("\nTop countries, all years:")
for name, n in by_country.most_common(8):
    print(f"   {name}: {n:,}")
print("\nWrote horror_by_country_year.csv")