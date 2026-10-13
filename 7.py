import duckdb

RELEASE = "2026-09-23.1"
path = f"s3://overturemaps-us-west-2/release/{RELEASE}/theme=places/type=place/*"

con = duckdb.connect()
con.execute("INSTALL spatial; INSTALL httpfs; LOAD spatial; LOAD httpfs;")
con.execute("SET s3_region='us-west-2';")

# 1. Print the columns so we can see the real schema
for row in con.execute(
    f"DESCRIBE SELECT * FROM read_parquet('{path}', hive_partitioning=1)"
).fetchall():
    print(row[0], "|", row[1])

# 2. Export cinemas, matching on the taxonomy field
con.execute(f"""
COPY (
  SELECT
    names.primary             AS name,
    CAST(taxonomy AS VARCHAR) AS taxonomy,
    addresses[1].region       AS state,
    confidence,
    ST_Y(geometry)            AS lat,
    ST_X(geometry)            AS lon
  FROM read_parquet('{path}', hive_partitioning=1)
  WHERE bbox.xmin BETWEEN 112 AND 154
    AND bbox.ymin BETWEEN -44 AND -10
    AND addresses[1].country = 'AU'
    AND (CAST(taxonomy AS VARCHAR) ILIKE '%movie_theat%'
         OR CAST(taxonomy AS VARCHAR) ILIKE '%cinema%')
) TO 'cinemas.csv' (HEADER, DELIMITER ',');
""")
print("done")