from pathlib import Path

import duckdb
import pandas as pd

from taxi_monitor.aggregate import zone_hour_demand
from taxi_monitor.dashboard import save_dashboard_figure


def main() -> None:
    db_path = Path("data/processed/taxi.duckdb")
    out_path = Path("reports/dashboard.png")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(db_path))
    df = zone_hour_demand(con)

    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)

    save_dashboard_figure(
        df,
        output_path=out_path,
        time_col="pickup_hour",
        value_col="trip_count",
        group_col="pickup_location_id",
    )
    print(f"Saved dashboard to {out_path}")


if __name__ == "__main__":
    main()