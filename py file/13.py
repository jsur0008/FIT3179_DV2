import pandas as pd

df = pd.read_csv("data/horror_movies_au.csv")
df["year"] = pd.to_datetime(df["release_date"], errors="coerce").dt.year

rc = df[df["au_certification"].astype(str).str.strip() == "RC"]
print(rc[["title", "year", "release_date"]].sort_values("year").to_string(index=False))
print(len(rc), "RC films,", rc.year.notna().sum(), "with a release date")