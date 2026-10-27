"""
Prepare the 'where horror is filmed' bin map from your Wikidata filming-location exports.

Usage (from your project folder):
    python3 py/prep_filming_bins.py --filming "data/*Filming*.json" --out data
    python3 py/prep_filming_bins.py --filming "data/*Filming*.json" --out data --bin 3 --keep-countries

Output (in --out):
    horror_filming_bins.json       one row per (square, decade): lon0, lat0, lon1, lat1, decade_start,
                                   films (different films with a filming place in that square),
                                   top_place (the most common place name in the square)
    horror_filming_hotspots.csv    the busiest squares over all decades, with a label, for the map labels
    horror_filming_films.csv       one row per film per square (title, year, place) for click-to-list
"""
import argparse
import csv
import glob
import json
import math
import os
import re
import sys
from collections import Counter, defaultdict

ap = argparse.ArgumentParser()
ap.add_argument("--filming", default="*Filming*.json")
ap.add_argument("--out", default=".")
ap.add_argument("--bin", type=float, default=5.0, help="square size in degrees (default 5)")
ap.add_argument("--keep-countries", action="store_true")
ap.add_argument("--hotspots", type=int, default=8, help="how many busy squares to label (default 8)")
args = ap.parse_args()

POINT = re.compile(r"Point\(\s*(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)\s*\)")
files = sorted(glob.glob(args.filming))
if not files:
    sys.exit(f"No files found for '{args.filming}'")
rows = []
for p in files:
    with open(p, encoding="utf-8") as f:
        rows.extend(json.load(f))
print(f"{len(rows):,} rows from {len(files)} file(s)")

keys = {k for r in rows for k in r}
coord_k = next((k for k in keys if "coord" in k.lower()), None)
country_k = next((k for k in keys if "country" in k.lower()), None)
place_k = next((k for k in ("locLabel", "placeLabel") if k in keys), None) or next(
    (k for k in sorted(keys) if k.endswith("Label") and k not in ("filmLabel", country_k)), None)
if not (coord_k and place_k and "film" in keys):
    sys.exit(f"Need fields 'film', a place label and a coordinate; found {sorted(keys)}")

films_in = defaultdict(set)                   # (decade, lon0, lat0) -> film ids
names = defaultdict(Counter)                  # (decade, lon0, lat0) -> place name counts
all_names = defaultdict(Counter)              # (lon0, lat0) -> place name counts
all_films = defaultdict(set)                  # (lon0, lat0) -> film ids
film_rows = {}                                # (film, lon0, lat0) -> row for the click-to-list table
no_coord = country_level = no_year = 0
for r in rows:
    m = POINT.match(r.get(coord_k) or "")
    if not m:
        no_coord += 1
        continue
    lon, lat = float(m.group(1)), float(m.group(2))
    label = (r.get(place_k) or "").strip()
    country = ((r.get(country_k) if country_k else "") or "").strip()
    if not args.keep_countries and country and label.lower() == country.lower():
        country_level += 1
        continue
    year = str(r.get("year") or "")
    if not year[:4].isdigit():
        no_year += 1
        continue
    decade = int(year[:4]) // 10 * 10
    lon0 = math.floor(lon / args.bin) * args.bin
    lat0 = math.floor(lat / args.bin) * args.bin
    films_in[(decade, lon0, lat0)].add(r["film"])
    names[(decade, lon0, lat0)][label] += 1
    all_films[(lon0, lat0)].add(r["film"])
    all_names[(lon0, lat0)][label] += 1
    film_rows.setdefault((r["film"], lon0, lat0), {
        "lon0": lon0, "lat0": lat0, "decade_start": decade,
        "title": r.get("filmLabel") or "(untitled)", "year": year[:4], "place": label})

out = []
for (decade, lon0, lat0), fids in films_in.items():
    out.append({"decade_start": decade, "lon0": lon0, "lat0": lat0,
                "lon1": lon0 + args.bin, "lat1": lat0 + args.bin,
                "films": len(fids), "top_place": names[(decade, lon0, lat0)].most_common(1)[0][0]})
out.sort(key=lambda d: (d["decade_start"], -d["films"]))
os.makedirs(args.out, exist_ok=True)
p1 = os.path.join(args.out, "horror_filming_bins.json")
with open(p1, "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, separators=(",", ":"))

top = sorted(all_films.items(), key=lambda kv: -len(kv[1]))[: args.hotspots]
p2 = os.path.join(args.out, "horror_filming_hotspots.csv")
with open(p2, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["place", "lon", "lat", "films"])
    for (lon0, lat0), fids in top:
        w.writerow([all_names[(lon0, lat0)].most_common(1)[0][0], lon0 + args.bin / 2, lat0 + args.bin / 2, len(fids)])

p3 = os.path.join(args.out, "horror_filming_films.csv")
with open(p3, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["lon0", "lat0", "decade_start", "title", "year", "place"])
    w.writeheader()
    w.writerows(sorted(film_rows.values(), key=lambda d: (d["lon0"], d["lat0"], -int(d["year"]))))

kept = len({fid for s in all_films.values() for fid in s})
print(f"{no_coord:,} rows without coordinates and {no_year:,} without a year were skipped; "
      f"{country_level:,} whole-country rows {'kept' if args.keep_countries else 'dropped'}")
print(f"{kept:,} films are in {len(all_films):,} squares of {args.bin:g} degrees. Busiest squares:")
for (lon0, lat0), fids in top:
    print(f"   {all_names[(lon0, lat0)].most_common(1)[0][0]}: {len(fids)} films")
print(f"Wrote {p1} ({os.path.getsize(p1) / 1024:.0f} KB), {p2} and {p3} ({len(film_rows):,} film/square rows)")