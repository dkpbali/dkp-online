import os
import sys
import json
import datetime
import time
import numpy as np
import gspread
from google.oauth2.service_account import Credentials
import copernicusmarine
import xarray as xr
import traceback

# Configuration
SPREADSHEET_ID = "1UGKcuRhG0TCgy9IED7FBNPHNEibVW3tpglDZXLezrd8" # EWS Sentimen Perikanan
SHEET_MONITORING = "RT_MONITORING"
SHEET_BASELINE = "RT_BASELINE"
BASELINE_START_ROW = 5
MONITORING_START_ROW = 5

# Bounding box for Bali region
BALI_BOUNDS = {
    "min_lon": 114.3,
    "max_lon": 115.8,
    "min_lat": -9.0,
    "max_lat": -8.0
}

# Monitoring Stations
STATIONS = [
    {"name": "Nusa Penida", "lat": -8.729, "lon": 115.542, "code": "NPE"},
    {"name": "Amed", "lat": -8.336, "lon": 115.654, "code": "AMD"},
    {"name": "Pemuteran", "lat": -8.146, "lon": 114.629, "code": "PMT"},
    {"name": "Selat Bali (sisi timur)", "lat": -8.223, "lon": 114.437, "code": "SBE"}
]

def main():
    print("=== Start Red Tide Anomaly Check ===")
    
    # 1. Authenticate with Google Sheets API
    sa_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not sa_json:
        print("Error: GOOGLE_SERVICE_ACCOUNT_JSON env var not set.")
        sys.exit(1)
        
    try:
        creds_info = json.loads(sa_json)
        scopes = [
            "https://spreadsheets.google.com/feeds",
            "https://www.googleapis.com/auth/drive"
        ]
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        gc = gspread.authorize(creds)
        sh = gc.open_by_key(SPREADSHEET_ID)
        print("Google Sheets API authenticated successfully.")
    except Exception as e:
        print(f"Error authenticating with Google Sheets: {e}")
        traceback.print_exc()
        sys.exit(1)

    # 2. Read Baselines from RT_BASELINE sheet
    try:
        ws_base = sh.worksheet(SHEET_BASELINE)
        # Get all records starting from header at row 3 (data starts at row 5)
        # We can read all rows and skip rows 1, 2 and 4.
        all_rows = ws_base.get_all_values()
        
        # Parse baseline data
        baselines = {}
        # row index 4 is Row 5 (1-based row 5 = 0-based index 4)
        for idx in range(4, len(all_rows)):
            row = all_rows[idx]
            if len(row) < 4 or not row[0]:
                continue
            lokasi = row[0].strip()
            bulan = int(float(row[1]))
            chl_mean = float(row[2])
            chl_std = float(row[3])
            baselines[(lokasi, bulan)] = (chl_mean, chl_std)
            
        print(f"Loaded {len(baselines)} baseline monthly records.")
    except Exception as e:
        print(f"Error loading baselines from sheet: {e}")
        traceback.print_exc()
        sys.exit(1)

    # 3. Read active incidents from RT_MONITORING to prevent duplicates
    try:
        ws_mon = sh.worksheet(SHEET_MONITORING)
        mon_rows = ws_mon.get_all_values()
        active_locations = set()
        
        # Row 5 starts at index 4
        for idx in range(4, len(mon_rows)):
            row = mon_rows[idx]
            if len(row) < 14 or not row[0]:
                continue
            lokasi = row[1].strip()
            status_final = row[13].strip()
            # If status_final is empty, it means this incident is still active/unresolved
            if not status_final:
                active_locations.add(lokasi)
                
        print(f"Active incidents currently monitored: {list(active_locations)}")
    except Exception as e:
        print(f"Error reading active incidents: {e}")
        traceback.print_exc()
        sys.exit(1)

    # 4. Fetch daily Chlorophyll data from Copernicus Marine
    # Get last 3 days to account for satellite processing delays
    today = datetime.date.today()
    start_date = today - datetime.timedelta(days=3)
    
    print(f"Querying Copernicus for dates: {start_date} to {today}")
    
    # Authenticate explicitly using env vars if available
    username = os.environ.get("COPERNICUSMARINE_SERVICE_USERNAME")
    password = os.environ.get("COPERNICUSMARINE_SERVICE_PASSWORD")
    if username and password:
        try:
            print(f"Explicitly logging in to Copernicus with username: {username}")
            copernicusmarine.login(username=username, password=password, force_overwrite=True)
            print("Successfully authenticated and stored Copernicus credentials.")
        except Exception as e:
            print(f"Warning: Explicit login failed: {e}")

    nc_filename = "copernicus_temp.nc"
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            print(f"Attempting to download data from Copernicus (Attempt {attempt}/{max_retries})...")
            # Download subset NetCDF file
            copernicusmarine.subset(
                dataset_id="cmems_obs-oc_glo_bgc-plankton_nrt_l4-gapfree-multi-4km_P1D",
                variables=["CHL"],
                start_datetime=f"{start_date}T00:00:00",
                end_datetime=f"{today}T23:59:59",
                minimum_longitude=BALI_BOUNDS["min_lon"],
                maximum_longitude=BALI_BOUNDS["max_lon"],
                minimum_latitude=BALI_BOUNDS["min_lat"],
                maximum_latitude=BALI_BOUNDS["max_lat"],
                output_filename=nc_filename,
                overwrite=True
            )
            print(f"Successfully downloaded satellite data to {nc_filename}")
            break
        except Exception as e:
            print(f"Error fetching data from Copernicus on attempt {attempt}: {e}")
            if attempt == max_retries:
                traceback.print_exc()
                # Clean up if file exists
                if os.path.exists(nc_filename):
                    os.remove(nc_filename)
                sys.exit(1)
            print("Waiting 15 seconds before retrying...")
            time.sleep(15)

    # 5. Process NetCDF and calculate anomaly scores
    current_month = today.month
    new_alerts = []
    
    try:
        with xr.open_dataset(nc_filename) as ds:
            # Extract variables
            # Note: Copernicus variables names are case-sensitive. It's usually 'CHL' or 'chl'
            chl_var = 'CHL' if 'CHL' in ds.variables else 'chl'
            
            # Open dataset coordinate arrays
            lats = ds.latitude.values
            lons = ds.longitude.values
            times = ds.time.values
            
            print(f"Copernicus coordinates: Lats [{lats.min():.4f} to {lats.max():.4f}], Lons [{lons.min():.4f} to {lons.max():.4f}], Times count: {len(times)}")
            
            for station in STATIONS:
                name = station["name"]
                st_lat = station["lat"]
                st_lon = station["lon"]
                code = station["code"]
                
                if name in active_locations:
                    print(f"Station '{name}' has an active unresolved incident. Skipping anomaly check to avoid duplicates.")
                    continue
                    
                # Find nearest grid index
                lat_idx = np.abs(lats - st_lat).argmin()
                lon_idx = np.abs(lons - st_lon).argmin()
                
                # Get time series of CHL at this point
                # Copernicus time coords are typically: (time, latitude, longitude)
                chl_ts = ds[chl_var].values[:, lat_idx, lon_idx]
                
                # Find latest non-NaN value
                measured_chl = None
                measured_time = None
                
                # Traverse backward in time (latest first)
                for t_idx in range(len(times) - 1, -1, -1):
                    val = float(chl_ts[t_idx])
                    if not np.isnan(val):
                        measured_chl = val
                        # convert times[t_idx] (numpy.datetime64) to python datetime
                        dt64 = times[t_idx]
                        unix_epoch = np.datetime64('1970-01-01T00:00:00')
                        one_second = np.timedelta64(1, 's')
                        seconds = int((dt64 - unix_epoch) / one_second)
                        measured_time = datetime.datetime.utcfromtimestamp(seconds).date()
                        break
                
                if measured_chl is None:
                    print(f"Station '{name}': No satellite data available (likely cloud-covered for all 3 days).")
                    continue
                    
                # Retrieve baseline values
                base_key = (name, current_month)
                if base_key not in baselines:
                    print(f"Station '{name}': Baseline values not found for month {current_month}.")
                    continue
                    
                base_mean, base_std = baselines[base_key]
                
                # Guard against zero or near-zero standard deviation to avoid ZeroDivisionError
                if base_std <= 0:
                    print(f"Station '{name}': Baseline std is {base_std} — cannot compute anomaly score. Skipping.")
                    continue
                
                # Calculate anomaly score (Z-score)
                anomaly_score = (measured_chl - base_mean) / base_std
                print(f"Station '{name}': Measured CHL = {measured_chl:.4f} mg/m3 | Baseline Mean = {base_mean:.4f} | Anomaly Score = {anomaly_score:.2f}")
                
                # Check threshold (anomaly_score > 2.0)
                if anomaly_score > 2.0:
                    print(f"🚨 ANOMALY DETECTED AT {name.upper()}! Score: {anomaly_score:.2f} > 2.0")
                    new_alerts.append({
                        "lokasi": name,
                        "lat": st_lat,
                        "lng": st_lon,
                        "code": code,
                        "tgl_alert": str(measured_time),
                        "chl_value": round(measured_chl, 4),
                        "chl_baseline": round(base_mean, 4),
                        "anomaly_score": round(anomaly_score, 2)
                    })
    except Exception as e:
        print(f"Error processing NetCDF file: {e}")
        traceback.print_exc()
    finally:
        # Clean up NetCDF file
        if os.path.exists(nc_filename):
            os.remove(nc_filename)

    # 6. Write alerts to Google Sheets
    if new_alerts:
        print(f"Writing {len(new_alerts)} new alerts to Google Sheet...")
        try:
            # Generate Event IDs
            # Format: RT-YYYYMMDD-XXX
            date_prefix = today.strftime("%Y%m%d")
            
            for alert in new_alerts:
                event_id = f"RT-{date_prefix}-{alert['code']}"
                
                # Append row
                new_row = [
                    event_id,
                    alert["lokasi"],
                    alert["lat"],
                    alert["lng"],
                    alert["tgl_alert"],
                    alert["chl_value"],
                    alert["chl_baseline"],
                    alert["anomaly_score"],
                    0,  # hari_ke = 0
                    "", # foto_url
                    "", # catatan_lapangan
                    "", # ai_description
                    "Menunggu Verifikasi", # status_sementara
                    "", # status_final (empty)
                    "", # petugas
                    "", # admin_verifikasi
                    "", # tgl_status_final
                    "FALSE" # alert_sent = FALSE (Apps Script will catch this)
                ]
                
                ws_mon.append_row(new_row, value_input_option="USER_ENTERED")
                print(f"Created incident {event_id} for {alert['lokasi']} in RT_MONITORING sheet.")
                
        except Exception as e:
            print(f"Error writing to Google Sheets: {e}")
            traceback.print_exc()
    else:
        print("No new anomalies detected today.")
        
    print("=== End Red Tide Anomaly Check ===")

if __name__ == "__main__":
    main()
