"""Build data/companies_budget_revenue.csv: the typical (median) budget and revenue
of each production company's horror films, for the dumbbell chart.
Run from the project root:  python prep/companies_budget_revenue.py [data/horror_movies_au.csv]
"""
import sys

import pandas as pd

SRC = sys.argv[1] if len(sys.argv) > 1 else "data/horror_movies_au.csv"
OUT = "data/companies_budget_revenue.csv"
MIN_FILMS = 15          # a company needs this many films with BOTH budget and revenue recorded

df = pd.read_csv(SRC, low_memory=False)
df = df.dropna(subset=["companies"])
df = df[(df.budget > 0) & (df.revenue > 0)].copy()          # 0 means "not recorded"

df["company"] = df["companies"].str.split("|")
df = df.explode("company")
df["company"] = df["company"].str.replace(r"\s*\([A-Z]{2}\)\s*$", "", regex=True).str.strip()
df = df[df.company != ""].drop_duplicates(["id", "company"])  # a film counts once per company

g = df.groupby("company").agg(films=("id", "count"),
                              budget=("budget", "median"),
                              revenue=("revenue", "median"),
                              first_year=("year", "min"),
                              last_year=("year", "max")).reset_index()
g = g[g.films >= MIN_FILMS].copy()
g["budget_m"] = (g.budget / 1e6).round(2)
g["revenue_m"] = (g.revenue / 1e6).round(2)
g["multiple"] = (g.revenue / g.budget).round(1)
g["median_year"] = df.groupby("company").year.median().reindex(g.company).values
g = g.sort_values("multiple", ascending=False)
g[["company", "films", "budget_m", "revenue_m", "multiple", "median_year"]].to_csv(OUT, index=False)
print(f"Wrote {OUT}: {len(g)} companies with >= {MIN_FILMS} films that have both budget and revenue")
print(g[["company", "films", "budget_m", "revenue_m", "multiple"]].to_string(index=False))