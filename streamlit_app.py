import streamlit as st
import pandas as pd
from datetime import datetime
import gspread
from google.oauth2.service_account import Credentials

# ============================================
# 🔐 Google Sheet connection (using Streamlit secrets)
# ============================================
SHEET_KEY = "1jRUsA6AxPVlPLeVgFexPYTRZycFCq72oevYQsISuMUs"
SHEET_NAME = "sheet1"

scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds = Credentials.from_service_account_info(
    st.secrets["google_service_account"],
    scopes=scope
)

client = gspread.authorize(creds)

try:
    sheet = client.open_by_key(SHEET_KEY).worksheet(SHEET_NAME)
except Exception as e:
    st.error(f"❌ Cannot open Google Sheet: {e}")
    st.stop()

# ============================================
# Mock stations (colStations)
# ============================================
colStations = pd.DataFrame({
    "Code": ["S1", "S2", "S3", "S4"],
    "Name": ["รับรถเข้า", "ชั่งเข้า", "โหลดสินค้า", "ชั่งออก"]
})

# ============================================
# Streamlit UI
# ============================================
st.title("🚛 Time Stamp System - TCRY")
plate = st.text_input("ทะเบียนรถ (Plate Number):")
barcode_input = st.text_input("Barcode code (S1 / S2 / S3 / S4):")
reason = st.text_input("เหตุผล (ถ้ามี):")
save_status = ""

# ============================================
# Helper Functions
# ============================================
def lookup_station(code):
    match = colStations[colStations["Code"] == code]
    return match["Name"].iloc[0] if not match.empty else "Unknown Station"

def get_all_scans():
    data = sheet.get_all_records()
    return pd.DataFrame(data) if data else pd.DataFrame(columns=[
        "ทะเบียนรถ", "Barcode", "Barcode2", "Barcode3", "Barcode4",
        "Station", "Station2", "Station3", "Station4",
        "Time", "Time2", "Time3", "Time4", "สาเหตุ", "ScanDateTime"
    ])

def append_to_sheet(row_dict):
    sheet.append_row(list(row_dict.values()))

def update_last_row(index, row_dict):
    # gspread index starts at 1 (header row = 1)
    for i, (k, v) in enumerate(row_dict.items(), start=1):
        sheet.update_cell(index + 2, i, v)

def notify(message, type="info"):
    if type == "warning":
        st.warning(message)
    elif type == "error":
        st.error(message)
    else:
        st.info(message)

# ============================================
# Main Logic
# ============================================
if st.button("📷 Scan Now"):
    try:
        ts = datetime.now()
        if not plate.strip():
            notify("กรุณากรอกทะเบียนรถก่อนสแกน", "warning")
        elif not barcode_input.strip():
            notify("กรุณากรอก Barcode (S1/S2/S3/S4)", "warning")
        else:
            df = get_all_scans()
            code = barcode_input.strip().upper()
            staName = lookup_station(code)
            lastScan = df[df["ทะเบียนรถ"] == plate].sort_values("ScanDateTime", ascending=False).head(1)
            lastScan = lastScan.iloc[0] if not lastScan.empty else None

            # Duplicate scan check
            if lastScan is not None:
                last_code = lastScan["Barcode4"] or lastScan["Barcode3"] or lastScan["Barcode2"] or lastScan["Barcode"]
                if code == last_code and not (
                    (code == "S3" and reason.strip() != "") or
                    (code == "S4" and pd.notna(lastScan["สาเหตุ"]))
                ):
                    notify(f"ไม่สามารถสแกน {code} ซ้ำได้", "warning")
                    st.stop()

            # Skip-step validation
            if code == "S2" and (lastScan is None or pd.isna(lastScan["Barcode"])):
                notify("ไม่พบ S1 ล่าสุด ไม่สามารถข้ามไป S2 ได้", "error")
                st.stop()
            elif code == "S3" and (lastScan is None or pd.isna(lastScan["Barcode2"])):
                notify("ไม่พบ S2 ล่าสุด ไม่สามารถข้ามไป S3 ได้", "error")
                st.stop()
            elif code == "S4" and (lastScan is None or pd.isna(lastScan["Barcode3"])):
                notify("ไม่พบ S3 ล่าสุด ไม่สามารถข้ามไป S4 ได้", "error")
                st.stop()

            # Patch-like behavior
            if code == "S1":
                new_row = {
                    "ทะเบียนรถ": plate,
                    "Barcode": "S1",
                    "Barcode2": "",
                    "Barcode3": "",
                    "Barcode4": "",
                    "Station": staName,
                    "Station2": "",
                    "Station3": "",
                    "Station4": "",
                    "Time": ts.strftime("%H:%M:%S"),
                    "Time2": "",
                    "Time3": "",
                    "Time4": "",
                    "สาเหตุ": "",
                    "ScanDateTime": ts.strftime("%Y-%m-%d %H:%M:%S")
                }
                append_to_sheet(new_row)

            elif code in ["S2", "S3", "S4"] and lastScan is not None:
                idx = lastScan.name
                update_dict = lastScan.to_dict()
                update_dict[f"Barcode{code[-1]}"] = code
                update_dict[f"Station{code[-1]}"] = staName
                update_dict[f"Time{code[-1]}"] = ts.strftime("%H:%M:%S")
                if code == "S3":
                    update_dict["สาเหตุ"] = reason.strip()
                update_dict["ScanDateTime"] = ts.strftime("%Y-%m-%d %H:%M:%S")
                update_last_row(idx, update_dict)

            else:
                notify(f"Unknown scan code: {code}", "warning")

            st.success(f"✅ บันทึกสำเร็จ @ {ts.strftime('%d/%m/%Y %H:%M')}")

    except Exception as e:
        st.error(f"❌ บันทึกข้อมูลไม่สำเร็จ: {e}")

# ============================================
# Display data
# ============================================
st.divider()
st.subheader("📋 ข้อมูลทั้งหมดใน Google Sheet")
try:
    df = get_all_scans()
    st.dataframe(df)
except Exception as e:
    st.error(f"Cannot fetch Google Sheet: {e}")

