from pathlib import Path

import duckdb
import pandas as pd
import matplotlib.pyplot as plt

from taxi_monitor.aggregate import zone_hour_demand
from taxi_monitor.dashboard import build_dashboard


from pathlib import Path

import duckdb
import pandas as pd
import matplotlib.pyplot as plt

from taxi_monitor.aggregate import zone_hour_demand
from taxi_monitor.dashboard import build_dashboard


def main() -> None:
    # 1. Setup paths
    db_path = Path("data/taxi_monitor.duckdb")
    out_path = Path("reports/dashboard.png")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 2. Connect to database and get data
    con = duckdb.connect(str(db_path))
    df = zone_hour_demand(con)

    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)

    # 3. Generate the dashboard figure
    # We call it with just 'df' as the library requires
    fig = build_dashboard(df)

    # 4. Save the figure
    # If build_dashboard doesn't explicitly return the fig, we use plt.gcf()
    if fig is None:
        fig = plt.gcf()
        
    fig.savefig(out_path, bbox_inches='tight', dpi=150)
    plt.close(fig) # Close to free up memory
    
    print(f"✅ Successfully saved static dashboard to {out_path}")


if __name__ == "__main__":
    main()
