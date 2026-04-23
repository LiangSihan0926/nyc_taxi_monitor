from pathlib import Path

import duckdb
import pandas as pd

from taxi_monitor.aggregate import zone_hour_demand
from taxi_monitor.benchmarking import benchmark_forecast_and_anomaly


def main() -> None:
    db_path = Path("data/processed/taxi.duckdb")
    out_path = Path("reports/benchmark_results.csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(db_path))
    df = zone_hour_demand(con)

    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)

    results = benchmark_forecast_and_anomaly(
        df,
        time_col="pickup_hour",
        value_col="trip_count",
        group_col="pickup_location_id",
    )
    results.to_csv(out_path, index=False)
    print(f"Saved benchmark results to {out_path}")


if __name__ == "__main__":
    main()
