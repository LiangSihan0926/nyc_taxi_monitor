from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt


fig_dir = Path("reports/figures")
fig_dir.mkdir(parents=True, exist_ok=True)

# =========================
# P1：Forecast MAE
# =========================
df = pd.read_csv("reports/experiment_6_forecast.csv")

plt.figure()
plt.bar(df["method"], df["mae"])
plt.xticks(rotation=30)
plt.xlabel("Method")
plt.ylabel("MAE")
plt.title("Forecasting Performance (MAE)")
plt.tight_layout()

plt.savefig(fig_dir / "forecast_mae.png")
plt.close()

# =========================
# P2：Anomaly Severity
# =========================
df = pd.read_csv("reports/experiment_7_advanced_anomaly.csv")

top = df.sort_values("severity", ascending=False).head(20)

plt.figure()
plt.bar(range(len(top)), top["severity"])
plt.xlabel("Top anomalies")
plt.ylabel("Severity")
plt.title("Top Anomaly Severity")
plt.tight_layout()

plt.savefig(fig_dir / "anomaly_severity.png")
plt.close()

print("Figures saved to reports/figures/")