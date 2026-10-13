"""
Prepare the 'set here, shot there' connection map from your two Wikidata exports:
    Filming_Loc_<decade>.json     where each horror film was FILMED
    Narrative_Loc_<decade>.json   where each horror film's story is SET

Both are JSON lists of rows like
    {"film": ".../entity/Q19405", "filmLabel": "The Ninth Gate", "year": "2000",
     "locLabel": "Spain", "countryLabel": "Spain", "coord": "Point(-3.5 40.2)"}
The two files are joined on the film's Wikidata id (the "film" field).

Usage (any number of decades is fine; run it from your project folder):
    python3 prep_connections.py --filming "data/*Filming*.json" --narrative "data/*Narrative*.json" --out data
    python3 prep_connections.py                      # if the JSON files are in the current folder
    python3 prep_connections.py --keep-domestic     # also keep films set and shot in the same country

Output:
    horror_connections.json   one row per (set-in place, filmed-in place, decade): number of films,
                              an example film, both end points and the arc between them

How it counts:
  - Rows are de-duplicated first (the exports repeat each row several times).
  - A film with several story settings or several filming places is paired every way, and each
    pair counts that film once. So a film with 2 settings and 3 locations adds 6 arcs.
  - Pairs inside one country (set in the US, shot in the US) are dropped by default, because
    the map is about films that travelled. The share dropped is printed so you can quote it.
  - Some places are whole countries, so their point sits at the middle of the country.
"""
import argparse
import glob
import json
import os
import re
import sys
from collections import defaultdict

ap = argparse.ArgumentParser()
ap.add_argument("--filming", default="*Filming*.json")
ap.add_argument("--narrative", default="*Narrative*.json")
ap.add_argument("--keep-domestic", action="store_true")
ap.add_argument("--out", default=".", help="folder to write horror_connections.json into")
args = ap.parse_args()

POINT = re.compile(r"Point\(\s*(-?[\d.eE+-]+)\s+(-?[\d.eE+-]+)\s*\)")


def load(pattern, what):
    files = sorted(glob.glob(pattern))
    if not files:
        sys.exit(f"No {what} files found for '{pattern}' (use --{what} to point at them)")
    rows = []
    for p in files:
        with open(p, encoding="utf-8") as f:
            rows.extend(json.load(f))
    print(f"{what}: {len(rows):,} rows from {len(files)} file(s)")
    return rows


def keys_for(rows, what):
    """Work out which fields hold the place name, country and coordinates."""
    keys = {k for r in rows for k in r}
    coord = next((k for k in keys if "coord" in k.lower()), None)
    country = next((k for k in keys if "country" in k.lower()), None)
    place = next((k for k in ("locLabel", "narLocLabel", "placeLabel") if k in keys), None) or next(
        (k for k in sorted(keys) if k.endswith("Label") and k not in ("filmLabel", country)), None)
    if not (coord and place and "film" in keys):
        sys.exit(f"The {what} file needs fields 'film', a place label and a coordinate; found {sorted(keys)}")
    return place, country, coord


def places_by_film(rows, what):
    place_k, country_k, coord_k = keys_for(rows, what)
    films, no_coord = {}, 0
    for r in rows:
        m = POINT.match(r.get(coord_k) or "")
        if not m:
            no_coord += 1
            continue
        lon, lat = float(m.group(1)), float(m.group(2))
        label = r.get(place_k) or ""
        country = (r.get(country_k) if country_k else "") or label
        info = films.setdefault(r["film"], {"title": r.get("filmLabel", ""), "year": r.get("year"), "places": {}})
        if not info["year"] and r.get("year"):
            info["year"] = r["year"]
        info["places"][(round(lon, 3), round(lat, 3), label)] = (label, country, lon, lat)
    if no_coord:
        print(f"  {what}: {no_coord:,} rows without usable coordinates were skipped")
    return films


filming = places_by_film(load(args.filming, "filming"), "filming")
narrative = places_by_film(load(args.narrative, "narrative"), "narrative")
both = set(filming) & set(narrative)
print(f"{len(filming):,} films with filming places, {len(narrative):,} with story settings, "
      f"{len(both):,} with both")

pairs = defaultdict(set)            # (set-in place, filmed-in place, decade) -> film ids
domestic = same_spot = total_pairs = 0
for fid in both:
    year = filming[fid]["year"] or narrative[fid]["year"]
    if not (year and str(year).isdigit()):
        continue
    decade = int(year) // 10 * 10
    for n in narrative[fid]["places"].values():
        for s in filming[fid]["places"].values():
            total_pairs += 1
            if (n[2], n[3]) == (s[2], s[3]):
                same_spot += 1
                continue
            if n[1] == s[1] and not args.keep_domestic:
                domestic += 1
                continue
            pairs[(n, s, decade)].add(fid)

rows_out = []
for (n, s, decade), fids in pairs.items():
    rows_out.append({
        "set_in": n[0], "set_in_country": n[1], "filmed_in": s[0], "filmed_in_country": s[1],
        "decade_start": decade, "films": len(fids),
        "example": sorted(filming[f]["title"] for f in fids)[0],
        "set_lon": n[2], "set_lat": n[3], "shot_lon": s[2], "shot_lat": s[3],
        "geo": {"type": "LineString", "coordinates": [[n[2], n[3]], [s[2], s[3]]]},
    })
rows_out.sort(key=lambda r: (r["decade_start"], -r["films"]))
os.makedirs(args.out, exist_ok=True)
OUT = os.path.join(args.out, "horror_connections.json")
with open(OUT, "w", encoding="utf-8") as f:
    json.dump(rows_out, f, ensure_ascii=False, separators=(",", ":"))

route_films = defaultdict(set)
for (n, s, _), fids in pairs.items():
    route_films[(n[1], s[1])] |= fids
kept = set().union(*pairs.values()) if pairs else set()
print(f"\n{total_pairs:,} set-in/filmed-in pairs: {same_spot:,} at the same spot, {domestic:,} inside one country "
      f"({'kept' if args.keep_domestic else 'dropped'}); {len(rows_out):,} arcs written")
print(f"{len(kept):,} films have at least one arc. Most common routes (set in -> filmed in):")
for (a, b), fids in sorted(route_films.items(), key=lambda kv: -len(kv[1]))[:10]:
    print(f"   {a} -> {b}: {len(fids)} films")
print(f"\nWrote {OUT} ({os.path.getsize(OUT) / 1024:.0f} KB)")