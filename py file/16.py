"""Build data/companies_by_year.csv: horror films per production company per year,
for the biggest horror producers. Run from the project root:
    python prep/companies_by_year.py [data/horror_movies_au.csv]
"""
import re
import sys

import pandas as pd

SRC = sys.argv[1] if len(sys.argv) > 1 else "data/horror_movies_au.csv"
OUT = "data/companies_by_year.csv"
TOP_N = 15                      # how many companies get a ridge
FIRST_YEAR = 1920               # earlier years have too few films to read

df = pd.read_csv(SRC, low_memory=False)
df = df.dropna(subset=["year", "companies"]).copy()
df["year"] = df["year"].astype(int)
df = df[df.year >= FIRST_YEAR]

# One row per film per company ("A|B" lists). Drop a trailing country tag like " (FR)".
df["company"] = df["companies"].str.split("|")
df = df.explode("company")
df["company"] = df["company"].str.replace(r"\s*\([A-Z]{2}\)\s*$", "", regex=True).str.strip()
df = df[df.company != ""].drop_duplicates(["id", "company"])   # a film counts once per company

totals = df.company.value_counts()
top = totals.head(TOP_N).index
sub = df[df.company.isin(top)]

# films per company per year, with zeros filled in so each ridge is continuous
years = range(FIRST_YEAR, int(df.year.max()) + 1)
grid = pd.MultiIndex.from_product([top, years], names=["company", "year"])
out = (sub.groupby(["company", "year"]).size()
          .reindex(grid, fill_value=0).rename("films").reset_index())

# 5-year centred average, so each ridge is smooth enough to read
out = out.sort_values(["company", "year"])
out["films_smooth"] = (out.groupby("company").films
                          .transform(lambda s: s.rolling(5, center=True, min_periods=1).mean())
                          .round(2))

# order the ridges by the year when each company made most of its films (median)
med = sub.groupby("company").year.median().sort_values()
out["median_year"] = out.company.map(med)
out["total_films"] = out.company.map(totals)
out.to_csv(OUT, index=False)

print(f"Wrote {OUT}: {len(out)} rows")
print(pd.DataFrame({"films": totals[top], "median_year": med[top]}).sort_values("median_year").to_string())