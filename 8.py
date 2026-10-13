"""
Turn TMDB keywords into horror SUBGENRES and count them per 5-year block.

Usage (from your project folder):
    python3 prep_subgenres.py                         # reads horror_movies.csv, writes data/subgenre_by_period.csv
    python3 prep_subgenres.py path/to/horror_movies.csv --out data

Needs the 'keywords' and 'year' columns of horror_movies.csv.

How it counts:
  - TMDB has no subgenre field, so a film is put in a subgenre when one of its keywords contains a
    phrase from the list below (edit RULES to change it).
  - One film can belong to several subgenres (a zombie film can also be 'Apocalypse and outbreak').
    The counts therefore add up to MORE than the number of films.
  - Films with no keywords, or none that match, are in no subgenre. The script prints how many.
    This is large for obscure films, so say on the page "films with keywords on TMDB".
  - Years are grouped in 5-year blocks (1980 = 1980-84) so the shapes are smooth.
"""
import argparse
import csv
import os
from collections import Counter

RULES = {
    "Slasher":               ["slasher", "serial killer", "masked killer", "killer on the loose"],
    "Zombies":               ["zombie", "undead", "living dead"],
    "Vampires":              ["vampire", "dracula"],
    "Ghosts and hauntings":  ["ghost", "haunted", "haunting", "poltergeist"],
    "Demons and the occult": ["demon", "possession", "exorcis", "satan", "occult", "witch", "cult", "curse"],
    "Monsters and creatures":["monster", "creature", "werewolf", "giant animal", "killer animal", "shark", "killer insect"],
    "Psychological":         ["psychological", "paranoia", "madness", "insanity", "mental"],
    "Body horror":           ["body horror", "mutation", "parasite", "transformation", "gore", "splatter"],
    "Found footage":         ["found footage", "mockumentary", "pov"],
    "Folk horror":           ["folk horror", "pagan", "folklore", "ritual"],
    "Apocalypse and outbreak":["post-apocalyptic", "apocalypse", "virus", "outbreak", "pandemic", "epidemic"],
    "Cannibals":             ["cannibal"],
}

ap = argparse.ArgumentParser()
ap.add_argument("src", nargs="?", default="data/horror_movies.csv")
ap.add_argument("--out", default=".")
args = ap.parse_args()

rows = list(csv.DictReader(open(args.src, newline="", encoding="utf-8")))
sep = "|" if any("|" in (r.get("keywords") or "") for r in rows) else ","

counts, total, no_kw, no_match, no_year = Counter(), 0, 0, 0, 0
for r in rows:
    year = (r.get("year") or "").strip()
    if not year.isdigit():
        no_year += 1
        continue
    total += 1
    kws = [k.strip().lower() for k in (r.get("keywords") or "").split(sep) if k.strip()]
    if not kws:
        no_kw += 1
        continue
    block = int(year) // 5 * 5
    hit = [name for name, phrases in RULES.items() if any(p in k for k in kws for p in phrases)]
    if not hit:
        no_match += 1
    for name in hit:
        counts[(block, name)] += 1

os.makedirs(args.out, exist_ok=True)
path = os.path.join(args.out, "subgenre_by_period.csv")
with open(path, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["period_start", "subgenre", "films"])
    for (block, name), n in sorted(counts.items()):
        w.writerow([block, name, n])

print(f"{total:,} films with a year. {no_kw:,} have no keywords and {no_match:,} have keywords but match no subgenre "
      f"-> {total - no_kw - no_match:,} films ({(total - no_kw - no_match) / max(total, 1):.0%}) are in at least one subgenre.")
by_sub = Counter()
for (b, n), c in counts.items():
    by_sub[n] += c
for n, c in by_sub.most_common():
    print(f"   {n}: {c:,}")
print("Wrote", path)