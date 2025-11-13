import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from PIL import Image
from pyzbar.pyzbar import decode
import io
import pytz

# ============================================
# 🔐 Google Sheets Connection
# ============================================
SHEET_KEY = "1jRUsA6AxPVlPLeVgFexPYTRZycFCq72oevYQsISuMUs"
SCAN_SHEET = "scan"
BILLING_SHEET = "billing"

scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

json_key = st.secrets["gcp"]
creds = Credentials.from_service_account_info(json_key, scopes=scopes)
gc = gspread.authorize(creds)

scan_sheet = gc.open_by_key(SHEET_KEY).worksheet(SCAN_SHEET)
billing_sheet = gc.open_by_key(SHEET_KEY).worksheet(BILLING_SHEET)

# ============================================
# 📍 Helper Functions
# ============================================
def get_all_scans():
    data = scan_sheet.get_all_values()
    if len(data) > 1:
        headers = data[0]
        df = pd.DataFrame(data[1:], columns=headers)
        return df
    return pd.DataFrame(columns=[
        "ทะเบียนรถ","Barcode","Barcode2","Barcode3","Barcode4",
        "Station","Station2","Station3","Station4",
        "Time","Time2","Time3","Time4",
        "สาเหตุ","ScanDateTime"
    ])

def lookup_station(code):
    return {
        "S1": "ขึ้นสินค้า",
        "S2": "ขึ้นสินค้าเสร็จ",
        "S3": "ส่งเอกสาร",
        "S4": "ออกเอกสารเสร็จ"
    }.get(code, "Unknown")

def update_last_row(sheet_index, row_dict, sheet):
    row_dict = {k: ("" if pd.isna(v) else v) for k, v in row_dict.items()}
    for col_idx, (k, v) in enumerate(row_dict.items(), start=1):
        sheet.update_cell(sheet_index + 2, col_idx, v)

def append_to_sheet(row_dict):
    scan_sheet.append_row(list(row_dict.values()))

def append_to_billing(row_dict):
    billing_sheet.append_row(list(row_dict.values()))

# ============================================
# 🕹️ Sidebar Navigation
# ============================================
st.sidebar.title("🔖 Navigation")
page = st.sidebar.radio("เลือกหน้า", ["📷 Scan Page", "📋 Billing Page"])

# ============================================
# 🚛 PAGE 1: Scan Page
# ============================================
if page == "📷 Scan Page":
    st.title("🚛 ระบบ Tracking Time - TCRY (QR Code Version)")

    plate = st.text_input("ทะเบียนรถ (Plate Number):")

    reason_checked = st.checkbox("สาเหตุ: สแกนซ้ำ")
    reason = "สแกนซ้ำ" if reason_checked else ""

    st.markdown("### 📷 สแกน QR Code (S1 / S2 / S3 / S4)")
    img_file = st.camera_input("แตะเพื่อเปิดกล้องแล้วสแกน QR Code")

    barcode_input = None
    if img_file is not None:
        image = Image.open(io.BytesIO(img_file.getvalue()))
        decoded_objects = decode(image)
        if decoded_objects:
            barcode_input = decoded_objects[0].data.decode("utf-8").strip().upper()
            st.success(f"🎯 ตรวจพบ QR Code: {barcode_input}")
        else:
            st.warning("⚠️ ไม่พบ QR Code กรุณาสแกนใหม่")

    if not plate.strip():
        st.warning("⚠️ กรุณากรอกทะเบียนรถก่อนสแกน")
        st.stop()

    if barcode_input:

        code = barcode_input

        if code not in ["S1", "S2", "S3", "S4"]:
            st.error("⚠️ QR ต้องเป็น S1 / S2 / S3 / S4 เท่านั้น")
            st.stop()

        try:
            tz = pytz.timezone("Asia/Bangkok")
            ts = datetime.now(tz)

            df = get_all_scans()
            staName = lookup_station(code)

            # ============================================
            # Filter by Plate
            # ============================================
            df_filtered = df[df["ทะเบียนรถ"] == plate].copy()
            df_filtered["ScanDateTime"] = pd.to_datetime(
                df_filtered["ScanDateTime"], errors="coerce"
            )

            lastScan = df_filtered.sort_values("ScanDateTime", ascending=False).head(1)
            lastScan = lastScan.iloc[0] if not lastScan.empty else None

            station_order = {"S1": 1, "S2": 2, "S3": 3, "S4": 4}

            # ============================================
            # S1 → new row
            # ============================================
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
                st.success(f"✅ เริ่มแถวใหม่ด้วย S1 @ {ts.strftime('%H:%M:%S')}")
                st.stop()

            # ============================================
            # S2–S4 → Must have S1
            # ============================================
            if lastScan is None:
                st.error("❌ ต้องสแกน S1 ก่อน")
                st.stop()

            # ============================================
            # หาแถวจริงใน Google Sheet ด้วย Unique Key:
            # ทะเบียนรถ + Barcode(S1) + Time
            # ============================================
            match = df[
                (df["ทะเบียนรถ"] == lastScan["ทะเบียนรถ"]) &
                (df["Barcode"] == lastScan["Barcode"]) &
                (df["Time"] == lastScan["Time"])
            ]

            if match.empty:
                st.error("❌ ไม่พบแถวล่าสุดใน Google Sheet (Key mismatch)")
                st.stop()

            sheet_index = match.index[0]

            # ============================================
            # Check Sequence
            # ============================================
            last_code = None
            for c in ["Barcode4", "Barcode3", "Barcode2", "Barcode"]:
                val = str(lastScan.get(c, "")).strip()
                if val:
                    last_code = val
                    break

            if last_code:
                if station_order[code] < station_order[last_code]:
                    st.error(f"❌ ลำดับผิด (ล่าสุดคือ {last_code})")
                    st.stop()

                if station_order[code] > station_order[last_code] + 1:
                    need = [k for k, v in station_order.items()
                            if v == station_order[last_code] + 1][0]
                    st.error(f"⚠️ ต้องสแกน {need} ก่อน")
                    st.stop()

                if code == last_code:
                    if code == "S3":
                        if not reason_checked:
                            st.warning("❌ ต้องติ๊ก ✔ สแกนซ้ำ ก่อนสแกน S3 ซ้ำ")
                            st.stop()
                    else:
                        st.warning(f"❌ ไม่สามารถสแกน {code} ซ้ำได้")
                        st.stop()

            # ============================================
            # Update S2/S3/S4
            # ============================================
            update_dict = lastScan.to_dict()
            pos = code[-1]

            update_dict[f"Barcode{pos}"] = code
            update_dict[f"Station{pos}"] = staName
            update_dict[f"Time{pos}"] = ts.strftime("%H:%M:%S")

            if code == "S3":
                update_dict["สาเหตุ"] = reason

            update_dict["ScanDateTime"] = ts.strftime("%Y-%m-%d %H:%M:%S")

            update_last_row(sheet_index, update_dict, scan_sheet)
            st.success(f"✅ สแกน {code} สำเร็จ @ {ts.strftime('%H:%M:%S')}")

        except Exception as e:
            st.error(f"❌ Error: {e}")

    st.divider()
    st.subheader("📋 ข้อมูลทั้งหมดใน Google Sheet (scan)")
    try:
        df = get_all_scans()
        st.dataframe(df)
    except Exception as e:
        st.error(f"Cannot fetch Google Sheet: {e}")


# ============================================
# 💳 PAGE 2: Billing Page
# ============================================
elif page == "📋 Billing Page":
    st.title("📋 ระบบบันทึกข้อมูลใบแจ้งหนี้ (Billing)")

    with st.expander("🔒 Enter Password"):
        access_code = st.text_input("รหัสผ่าน:", type="password")
        if access_code != "TCRY2025":
            st.warning("❌ Incorrect password")
            st.stop()

    df_scan = get_all_scans()

    unique_plates = sorted(df_scan["ทะเบียนรถ"].unique()) if not df_scan.empty else []
    plate = st.selectbox("เลือกทะเบียนรถ:", unique_plates)

    reason_options = [
        "", "เก็บป้ายไม่ครบ", "ขึ้นงานไม่ครบ", "รวมยอดผิด",
        "ใส่จำนวน/ประเภทพาเลทผิด", "อื่นๆ"
    ]
    reason = st.selectbox("สาเหตุ:", reason_options)

    if st.button("💾 บันทึก Billing"):
        try:
            tz = pytz.timezone("Asia/Bangkok")
            ts = datetime.now(tz)

            df_filtered = df_scan[df_scan["ทะเบียนรถ"] == plate]
            last_time3 = df_filtered["Time3"].iloc[-1] if not df_filtered.empty else ""

            new_row = {
                "ทะเบียนรถ": plate,
                "สาเหตุ": reason,
                "Time3": last_time3,
                "วันที่เวลา": ts.strftime("%Y-%m-%d %H:%M:%S")
            }
            append_to_billing(new_row)

            st.success(f"✅ Billing Saved (Time3: {last_time3})")

        except Exception as e:
            st.error(f"Error: {e}")

    st.divider()
    st.subheader("📊 Billing Records")
    try:
        df_billing = pd.DataFrame(billing_sheet.get_all_records())
        st.dataframe(df_billing)
    except:
        st.error("Error loading billing sheet")
