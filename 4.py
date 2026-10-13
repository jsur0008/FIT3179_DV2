"""
Prepare the 'votes vs rating' chart data from your TMDB horror CSV.

Reads horror_movies.csv (needs columns vote_count and vote_average) and writes a tiny file,
votes_vs_rating.csv, with one row per (vote group, rating band) and how many films fall in it.
The big CSV stays on your computer; only this small file goes on the page.

Vote groups (how many people rated the film):
    No votes | 1-4 votes | 5-19 votes | 20-99 votes | 100-999 votes | 1,000+ votes
Rating bands: 0-1, 1-2, ... 9-10 (films with no votes have no rating, so they get a blank band).

Usage:
    python prep_votes.py                          # reads horror_movies.csv
    python prep_votes.py path/to/horror_movies.csv
"""
import csv
import sys
from collections import Counter

SRC = sys.argv[1] if len(sys.argv) > 1 else "data/horror_movies.csv"
GROUPS = ["No votes", "1-4 votes", "5-19 votes", "20-99 votes", "100-999 votes", "1,000+ votes"]


def group(votes):
    if votes <= 0:
        return GROUPS[0]
    if votes < 5:
        return GROUPS[1]
    if votes < 20:
        return GROUPS[2]
    if votes < 100:
        return GROUPS[3]
    if votes < 1000:
        return GROUPS[4]
    return GROUPS[5]


counts, total, skipped = Counter(), 0, 0
with open(SRC, newline="", encoding="utf-8") as f:
    for r in csv.DictReader(f):
        try:
            votes = int(float(r["vote_count"] or 0))
            avg = float(r["vote_average"] or 0)
        except (ValueError, KeyError):
            skipped += 1
            continue
        g = group(votes)
        band = "" if votes <= 0 else min(int(avg), 9)      # 10.0 goes into the 9-10 band
        counts[(g, band)] += 1
        total += 1

with open("votes_vs_rating.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["vote_group", "rating_band", "films"])
    for g in GROUPS:
        for band in [""] + list(range(10)):
            if counts[(g, band)]:
                w.writerow([g, band, counts[(g, band)]])

by_group = Counter()
for (g, _), n in counts.items():
    by_group[g] += n
print(f"{total:,} films read" + (f" ({skipped} rows skipped: missing vote columns)" if skipped else ""))
for g in GROUPS:
    print(f"  {g:<15}{by_group[g]:>8,}  {100 * by_group[g] / total:5.1f}%")
few = by_group[GROUPS[0]] + by_group[GROUPS[1]] + by_group[GROUPS[2]]
print(f"\n{100 * few / total:.0f}% of horror films have fewer than 20 votes.")
print("Wrote votes_vs_rating.csv")