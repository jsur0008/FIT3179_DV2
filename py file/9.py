"""
Count horror SUBGENRES per year, using the 23 subgenres on Blumhouse's page
(https://www.blumhouse.com/horror-subgenres) as the categories.

    python3 prep_subgenres.py --out data            # every year, 10 biggest subgenres, up to 2025
    python3 prep_subgenres.py --top 23 --step 5     # all 23, five-year blocks

Reads horror_movies.csv (year, keywords, genres). Writes subgenre_by_period.csv.
Categories are Blumhouse's; film assignments are ours (TMDB keyword matching), so they are approximate.
A film can be in several subgenres. Films with no keywords are in none.
"""
import argparse
import csv
import os
import re
from collections import Counter

# name: (phrases matched at the start of a word inside TMDB keywords, TMDB genres that also count)
RULES = {
    "Apocalyptic":        (["post-apocalyptic", "apocalypse", "end of the world", "dystopia", "pandemic", "epidemic", "outbreak"], []),
    "Backwoods":          (["backwoods", "cabin in the woods", "wilderness", "remote location", "hillbilly", "rural", "forest", "woods"], []),
    "Body horror":        (["body horror", "mutation", "parasite", "transformation", "disfigure", "mutilation"], []),
    "Cannibal":           (["cannibal"], []),
    "Cosmic":             (["cosmic horror", "lovecraft", "eldritch", "cthulhu", "interdimensional", "cosmic"], []),
    "Cult and experimental": (["cult film", "experimental", "surreal", "avant-garde", "campy"], []),
    "Folk horror":        (["folk horror", "folklore", "mythology", "legend", "pagan", "witchcraft", "urban legend", "ritual"], []),
    "Found footage":      (["found footage", "mockumentary", "handheld camera", "camcorder"], []),
    "Gore and splatter":  (["gore", "splatter", "extreme violence", "torture", "bloodbath", "slaughter"], []),
    "Gothic":             (["gothic", "castle", "mansion", "victorian", "dracula", "frankenstein"], []),
    "Holiday horror":     (["christmas", "halloween", "thanksgiving", "new year's eve", "valentine's day", "easter bunny", "holiday"], []),
    "Home invasion":      (["home invasion", "intruder", "stalker", "masked intruder", "break-in"], []),
    "Horror comedy":      (["horror comedy", "black comedy", "parody", "spoof", "satire"], ["Comedy"]),
    "Killer objects":     (["killer doll", "evil doll", "possessed doll", "ventriloquist dummy", "ouija", "killer car", "haunted object", "evil toy", "possessed object", "cursed object", "killer toy"], []),
    "Creature feature":   (["monster", "creature", "giant animal", "killer animal", "shark", "werewolf", "zombie", "vampire", "killer insect", "killer snake", "alligator", "giant spider"], []),
    "Psychological":      (["psychological", "paranoia", "madness", "insanity", "mental illness", "delusion", "hallucination", "unreliable narrator", "psychosis"], []),
    "Revenge":            (["revenge", "vengeance", "payback", "retribution"], []),
    "Sci-fi horror":      (["alien", "science fiction", "scientist", "experiment", "outer space", "spaceship", "space station", "genetic"], ["Science Fiction"]),
    "Slasher":            (["slasher", "serial killer", "masked killer", "killer on the loose", "final girl"], []),
    "Social horror":      (["social commentary", "racism", "social issues", "class differences", "class struggle", "gentrification", "feminism", "misogyny", "inequality", "social satire"], []),
    "Supernatural":       (["ghost", "haunted", "haunting", "poltergeist", "possession", "exorcis", "demon", "satan", "occult", "witch", "curse", "paranormal", "supernatural"], []),
    "Survival":           (["survival", "survival horror", "trapped", "stranded", "fight for survival", "last survivor"], []),
    "Tech horror":        (["artificial intelligence", "killer robot", "cyberspace", "social media", "internet", "computer", "technology", "virtual reality", "video game", "smartphone", "cyberbully"], []),
}

EXCLUDE = ["alienation"]          # keywords containing these are ignored (they contain "alien" but are not sci-fi)

# A phrase now matches only at the start of a word, so "cult" no longer matches inside "occult".
PATTERNS = {name: (re.compile("|".join(r"(?<![a-z0-9])" + re.escape(p) for p in phrases)), gen)
            for name, (phrases, gen) in RULES.items()}

ap = argparse.ArgumentParser()
ap.add_argument("src", nargs="?", default="data/horror_movies.csv")
ap.add_argument("--out", default=".")
ap.add_argument("--top", type=int, default=10, help="keep the N subgenres with the most films (default 10)")
ap.add_argument("--step", type=int, default=1, help="years per row: 1 = every year (default), 5 = five-year blocks")
ap.add_argument("--end", type=int, default=2025, help="last year to count (default 2025; the current year is incomplete)")
args = ap.parse_args()

rows = list(csv.DictReader(open(args.src, newline="", encoding="utf-8")))


def sep_for(col):
    return "|" if any("|" in (r.get(col) or "") for r in rows) else ","


KSEP, GSEP = sep_for("keywords"), sep_for("genres")
counts, total, no_kw, no_match = Counter(), 0, 0, 0
for r in rows:
    year = (r.get("year") or "").strip()
    if not year.isdigit():
        continue
    if int(year) > args.end:
        continue
    total += 1
    kws = [k.strip().lower() for k in (r.get("keywords") or "").split(KSEP) if k.strip()]
    genres = {g.strip() for g in (r.get("genres") or "").split(GSEP) if g.strip()}
    if not kws:
        no_kw += 1
        continue
    block = int(year) // args.step * args.step
    kws = [k for k in kws if not any(x in k for x in EXCLUDE)]
    hit = [name for name, (pattern, gen) in PATTERNS.items()
           if any(pattern.search(k) for k in kws) or any(g in genres for g in gen)]
    if not hit:
        no_match += 1
    for name in hit:
        counts[(block, name)] += 1

by_sub = Counter()
for (b, n), c in counts.items():
    by_sub[n] += c
keep = {n for n, _ in by_sub.most_common(args.top)}

os.makedirs(args.out, exist_ok=True)
path = os.path.join(args.out, "subgenre_by_period.csv")
first = min(b for b, _ in counts)
last = max(b for b, _ in counts)
with open(path, "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["period_start", "subgenre", "films"])
    for name in sorted(keep):
        for block in range(first, last + 1, args.step):   # zeros too, so gaps are not drawn as bridges
            w.writerow([block, name, counts.get((block, name), 0)])

used = total - no_kw - no_match
print(f"{total:,} films with a year. {no_kw:,} have no keywords/genres to use, {no_match:,} match no subgenre "
      f"-> {used:,} films ({used / max(total, 1):.0%}) are in at least one subgenre.")
print("Films per subgenre (all 23; * = written to the CSV):")
for n in RULES:
    print(f"  {'*' if n in keep else ' '} {n}: {by_sub.get(n, 0):,}")
print("Wrote", path)