from pathlib import Path

import duckdb

from taxi_monitor.analytics import (
    airport_vs_manhattan_summary,
    top_od_pairs,
    weekday_weekend_demand,
)


def main() -> None:
    db_path = Path("data/processed/taxi.duckdb")
    out_dir = Path("reports")
    out_dir.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect(str(db_path))

    weekday_weekend_demand(con).to_csv(out_dir / "weekday_weekend_demand.csv", index=False)
    top_od_pairs(con).to_csv(out_dir / "top_od_pairs.csv", index=False)
    airport_vs_manhattan_summary(con).to_csv(out_dir / "airport_vs_manhattan.csv", index=False)

    print(f"Saved analytics outputs to {out_dir}")


if __name__ == "__main__":
    main()