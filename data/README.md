# Data directory

Raw and processed data are **not** committed to git (see `.gitignore`).

To populate this directory run:

```bash
python scripts/download_data.py
```

Default layout after download:

```
data/
├── raw/                          # downloaded from NYC TLC
│   ├── yellow_tripdata_2023-11.parquet
│   ├── yellow_tripdata_2023-12.parquet
│   ├── yellow_tripdata_2024-01.parquet
│   └── taxi_zone_lookup.csv
├── clean/                        # cleaned parquet files
└── taxi_monitor.duckdb           # DuckDB database file
```

Source: <https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page>
