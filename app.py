import streamlit as st
import pandas as pd
import os

# --- 1. PAGE SETUP ---
st.set_page_config(page_title="NYC Taxi Monitor", page_icon="🚕", layout="wide")
st.title("🚕 NYC Taxi Demand Monitoring Dashboard")
st.markdown("""
Welcome to the interactive dashboard for the **Scalable NYC Taxi Demand Monitoring System**. 
Use the sidebar to navigate through the different Big Data experiments.
""")

# --- 2. HELPER FUNCTION TO LOAD DATA ---
@st.cache_data
def load_data(file_name):
    file_path = os.path.join("reports", file_name)
    if os.path.exists(file_path):
        return pd.read_csv(file_path)
    else:
        return None

# --- 3. SIDEBAR NAVIGATION ---
st.sidebar.header("Navigation")
page = st.sidebar.radio("Go to Experiment:", [
    "Overview & Hotspots", 
    "Parallel Processing (MapReduce)",
    "System Anomalies",
    "Project Health"
])

# --- 4. PAGE LOGIC ---

if page == "Overview & Hotspots":
    st.header("📍 Top Pickup Zones (Batch Hotspot)")
    st.write("This data shows the most popular pickup locations across the 9.37M cleaned trips.")
    
    df_hotspot = load_data("experiment_1_overall.csv")
    
    if df_hotspot is not None:
        # 1. Rename columns to be human-readable
        df_display = df_hotspot.rename(columns={
            "zone_id": "Zone ID",
            "zone_name": "Zone Name",
            "borough": "Borough",
            "trips": "Total Trips"
        })
        
        st.subheader("Raw Data")
        # 2. Use hide_index=True to remove the redundant left column
        st.dataframe(df_display, hide_index=True, width='stretch')
        
        st.subheader("Visual Breakdown")
        # 3. Sort, set the index, and plot using our new clean column names
        df_sorted = df_display.sort_values(by="Total Trips", ascending=False).set_index("Zone Name")
        st.bar_chart(df_sorted["Total Trips"])
        
    else:
        st.error("Could not find 'experiment_1_overall.csv' in the reports folder.")

elif page == "Parallel Processing (MapReduce)":
    st.header("⚙️ MapReduce Speedup")
    st.write("How does adding more CPU workers affect processing time? (Amdahl's Law in action)")
    
    df_parallel = load_data("experiment_5_parallel.csv")
    
    if df_parallel is not None:
        # Rename columns to be human-readable
        df_display = df_parallel.rename(columns={
            "workers": "Number of Workers",
            "wall_sec": "Wall Time (Seconds)",
            "speedup": "Speedup Factor"
        })
        
        # Hide index and display table
        st.dataframe(df_display, hide_index=True, width='stretch')
        
        # Plot using clean names
        st.line_chart(data=df_display, x="Number of Workers", y="Wall Time (Seconds)")
    else:
        st.error("Could not find 'experiment_5_parallel.csv' in the reports folder.")

elif page == "System Anomalies":
    st.header("🚨 Demand Anomalies")
    st.write("Detected demand surges against the weekly baseline.")
    
    df_anomalies = load_data("experiment_2_anomalies.csv")
    
    if df_anomalies is not None:
        # Rename columns to be human-readable
        df_display = df_anomalies.rename(columns={
            "pickup_hour": "Pickup Hour",
            "zone_id": "Zone ID",
            "trips": "Actual Trips",
            "hour_of_week": "Hour of Week",
            "mean": "Expected Mean",
            "std": "Standard Deviation",
            "z": "Z-Score (Severity)"
        })
        
        min_z = st.slider("Filter by Minimum Z-Score Severity:", min_value=3.0, max_value=250.0, value=3.0)
        
        # Filter on the newly named Z-Score column
        filtered_df = df_display[df_display["Z-Score (Severity)"] >= min_z]
        
        col1, col2 = st.columns([1, 3])
        with col1:
            st.metric(label="Anomalies Displayed", value=len(filtered_df))
        with col2:
            st.write("### Anomaly Severity over the Week")
            st.scatter_chart(data=filtered_df, x="Hour of Week", y="Z-Score (Severity)")
            
        # Hide index and display table
        st.dataframe(filtered_df, hide_index=True, width='stretch')
    else:
        st.error("Could not find 'experiment_2_anomalies.csv' in the reports folder.")
elif page == "Project Health":
    st.header("🏆 Project Health")
    st.write("A detailed look at testing infrastructure.")
    
    st.subheader("🧪 Test Coverage")
    st.metric(label="pytest-cov Branch Coverage", value="97.0%", delta="Target: > 80%")
    st.info("Continuous Integration (CI) is configured to automatically fail if coverage ever drops below 80%.")
    
    # --- THE BREAKDOWN SECTION ---
    st.write("### Coverage Breakdown by Module")
    
    # Snapshot of the core modules from your README
    coverage_data = pd.DataFrame({
        "Module": [
            "clean.py", "database.py", "hotspot.py", 
            "approximate.py", "parallel.py", "anomaly.py", "ingest.py"
        ],
        "Coverage %": [100, 98, 96, 100, 94, 95, 96]
    })
    
    # Display as a dataframe with built-in progress bars
    st.dataframe(
        coverage_data,
        hide_index=True,
        width='stretch',
        column_config={
            "Coverage %": st.column_config.ProgressColumn(
                "Coverage %",
                help="Line and branch coverage per module",
                format="%d%%",
                min_value=0,
                max_value=100,
            ),
        }
    )
        
    st.divider()
    st.caption("Environment: Python 3.9+ | Data Engine: DuckDB | UI: Streamlit")