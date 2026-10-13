"""Build data/country_centroids.csv (iso2, country, lat, lon) from data/world-50m.json.

world-50m.json is a TopoJSON file (shapes shared as "arcs"), so it has no ISO_A2 names;
each country has a numeric id (ISO 3166-1 numeric). pycountry turns that id into the
two-letter code the film data uses.

Each country's point is the centre of its largest land polygon, so the United States
sits on the mainland and France on mainland France.

Setup:  pip install pycountry
Run from the project root:  python prep/country_centroids.py
"""
import csv
import json
import sys

try:
    import pycountry
except ImportError:
    sys.exit("This script needs pycountry:  pip install pycountry")

SRC = "data/world-110m.json"
OUT = "data/country_centroids.csv"
OBJECT = "countries"          # name of the countries layer inside the file


def decode_arcs(topo):
    """Turn TopoJSON arcs (delta-encoded, maybe quantised) into lists of (lon, lat)."""
    tr = topo.get("transform")
    decoded = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for p in arc:
            if tr:
                x += p[0]
                y += p[1]
                pts.append((x * tr["scale"][0] + tr["translate"][0],
                            y * tr["scale"][1] + tr["translate"][1]))
            else:
                pts.append((p[0], p[1]))
        decoded.append(pts)
    return decoded


def ring_points(ring, arcs):
    """Join the arcs of one ring (a negative index means the arc runs backwards)."""
    pts = []
    for i in ring:
        seg = arcs[i] if i >= 0 else arcs[~i][::-1]
        pts.extend(seg if not pts else seg[1:])
    return pts


def area_centroid(pts):
    """Signed area and centroid of a ring of (lon, lat) points."""
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    a *= 0.5
    if a == 0:
        return 0.0, pts[0][0], pts[0][1]
    return a, cx / (6 * a), cy / (6 * a)


def largest_polygon_centroid(geom, arcs):
    if geom["type"] == "Polygon":
        polys = [geom["arcs"]]
    elif geom["type"] == "MultiPolygon":
        polys = geom["arcs"]
    else:
        return None
    best = None
    for poly in polys:
        area, cx, cy = area_centroid(ring_points(poly[0], arcs))   # outer ring only
        if best is None or abs(area) > best[0]:
            best = (abs(area), cx, cy)
    return (best[1], best[2]) if best else None


if __name__ == "__main__":
    topo = json.load(open(SRC, encoding="utf-8"))
    arcs = decode_arcs(topo)
    rows, skipped = [], []
    for g in topo["objects"][OBJECT]["geometries"]:
        gid = g.get("id")
        c = None
        if gid is not None and str(gid).strip().lstrip("-").isdigit():
            c = pycountry.countries.get(numeric=f"{int(gid):03d}")
        centre = largest_polygon_centroid(g, arcs)
        if c is None or centre is None:
            skipped.append(g.get("properties", {}).get("name") or gid)
            continue
        lon, lat = centre
        rows.append({"iso2": c.alpha_2, "country": getattr(c, "common_name", c.name),
                     "lat": round(lat, 3), "lon": round(lon, 3)})
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["iso2", "country", "lat", "lon"])
        w.writeheader()
        w.writerows(rows)
    print(f"Wrote {OUT}: {len(rows)} countries")
    if skipped:
        print(f"Skipped {len(skipped)} shapes with no usable id:", skipped[:10])