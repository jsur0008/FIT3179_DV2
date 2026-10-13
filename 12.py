import pandas as pd

df = pd.read_csv("data/horror_movies_au.csv")
df["year"] = pd.to_datetime(df["release_date"], errors="coerce").dt.year

tidy = {"G": "G", "PG": "PG", "M": "M",
        "MA15+": "MA15+", "MA 15+": "MA15+",
        "R18+": "R18+", "R 18+": "R18+",
        "RC": "RC (refused)"}
df["rating"] = df["au_certification"].astype(str).str.strip().map(tidy)

known = df.dropna(subset=["year", "rating"]).copy()
known["period"] = (known["year"] // 5 * 5).astype(int)

# See where the rated films actually sit before charting anything
print(known.groupby("period").size())

out = known.groupby(["period", "rating"]).size().reset_index(name="films")
order = ["G", "PG", "M", "MA15+", "R18+", "RC (refused)"]
periods = list(range(1975, 2025, 5))          # 1975 ... 2020

out = out[out.period.isin(periods)]
full = pd.MultiIndex.from_product([periods, order], names=["period", "rating"])
out = (out.set_index(["period", "rating"])
          .reindex(full, fill_value=0)        # missing combos become 0 films
          .reset_index())
out["period_date"] = pd.to_datetime(out.period.astype(str) + "-01-01").dt.strftime("%Y-%m-%d")

out.to_csv("data/horror_ratings.csv", index=False)
print(out.films.sum(), "films charted")
print("\nFilms per classification (1975-2020):")
print(out.groupby("rating").films.sum().reindex(order).to_string())

# Optional: also see the share of each
totals = out.groupby("rating").films.sum().reindex(order)
print((totals / totals.sum() * 100).round(1).astype(str).add("%").to_string())