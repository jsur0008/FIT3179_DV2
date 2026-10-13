import pandas as pd
df = pd.read_csv("data/horror_movies_au.csv")
df["month"] = pd.to_datetime(df["au_release_date"], errors="coerce").dt.month
m = df.dropna(subset=["month"]).groupby("month").size().reset_index(name="films")
m["share"] = (m.films / m.films.sum() * 100).round(1)
m["month_name"] = pd.to_datetime(m.month, format="%m").dt.strftime("%b")
m["slice"] = 1
m.to_csv("data/release_months.csv", index=False)