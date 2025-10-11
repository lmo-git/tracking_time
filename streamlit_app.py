import streamlit as st
import pandas as pd
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
from PIL import Image
from pyzbar.pyzbar import decode
import io
import pytz  # ✅ เพิ่ม timezone support

# ============================================
# 🔐 Google Sheets Connection
# ============================================
SHEET_KEY = "1jRUsA6AxPVlPLeVgFexPYTRZycFCq72oevYQsISuMUs"
SHEET_NAME = "scan"

scopes = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

json_key = st.secrets["gcp"]
creds = Credentials.from_service_account_info(json_key, scopes=scopes)
gc = gspread.authorize(creds)
sheet = gc.open_by_key(SHEET_KEY).worksheet(SHEET_NAME)

# ============================================
# 🧾 Ensure Header Exists
# ============================================
expected_headers = [
    "ทะเบียนรถ", "Barcode", "Barcode2", "Barcode3", "Barcode4",
    "Station", "Station2", "Station3", "Station4",
    "Time", "Time2", "Time3", "Time4", "สาเหตุ", "ScanDateTime"
]
headers = sheet.row_values(1)
if headers != expected_headers:
    sheet.insert_row(expected_headers, 1)

# ============================================
# 📍 Mock Stations
# ============================================
colStations = pd.DataFrame({
    "Code": ["S1", "S2", "S3", "S4"],
    "Name": ["ขึ้นสินค้า", "ขึ้นสินค้าเสร็จ", "ส่งเอกสาร", "ออกเอกสารเสร็จ"]
})

# ============================================
# 🧍 Streamlit UI
# ============================================
st.title("🚛 ระบบ Tracking Time - TCRY")

plate = st.text_input("ทะเบียนรถ (Plate Number):")

reason_options = [
    "",
    "เก็บป้ายมอบมาไม่ครบ",
    "ขึ้นงานไม่ครบตามแผน",
    "รวมยอดสินค้าผิด",
    "ใส่จำนวน/ประเภทพาเลทผิด",
    "อื่นๆ (ระบุ)"
]
reason = st.selectbox("สาเหตุ (เลือกถ้ามี):", reason_options)

# ============================================
# 📷 Camera QR Scanner
# ============================================
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
        st.warning("⚠️ ไม่พบ QR Code ในภาพ กรุณาสแกนใหม่")

# ============================================
# 🔧 Helper Functions
# ============================================
def lookup_station(code):
    match = colStations[colStations["Code"] == code]
    return match["Name"].iloc[0] if not match.empty else "Unknown Station"

def get_all_scans():
    data = sheet.get_all_records()
    return pd.DataFrame(data) if data else pd.DataFrame(columns=expected_headers)

def append_to_sheet(row_dict):
    sheet.append_row(list(row_dict.values()))

def update_last_row(index, row_dict):
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
# 🧠 Main Logic: Trigger on QR Scan
# ============================================
if barcode_input:
    code = barcode_input
    if code not in ["S1", "S2", "S3", "S4"]:
        st.error("⚠️ QR Code ไม่ถูกต้อง (ต้องเป็น S1, S2, S3 หรือ S4 เท่านั้น)")
    else:
        try:
            # ✅ ใช้เวลาประเทศไทย
            tz = pytz.timezone("Asia/Bangkok")
            ts = datetime.now(tz)

            df = get_all_scans()
            staName = lookup_station(code)
            lastScan = df[df["ทะเบียนรถ"] == plate].sort_values("ScanDateTime", ascending=False).head(1)
            lastScan = lastScan.iloc[0] if not lastScan.empty else None

            # 1️⃣ Duplicate scan check
            if lastScan is not None:
                last_code = lastScan["Barcode4"] or lastScan["Barcode3"] or lastScan["Barcode2"] or lastScan["Barcode"]
                if code == last_code and not (
                    (code == "S3" and reason.strip() != "") or
                    (code == "S4" and pd.notna(lastScan["สาเหตุ"]))
                ):
                    notify(f"ไม่สามารถสแกน {code} ซ้ำได้", "warning")
                    st.stop()

            # 2️⃣ Skip-step validation
            if code == "S2" and (lastScan is None or pd.isna(lastScan["Barcode"])):
                notify("ไม่พบ S1 ล่าสุด ไม่สามารถข้ามไป S2 ได้", "error")
                st.stop()
            elif code == "S3" and (lastScan is None or pd.isna(lastScan["Barcode2"])):
                notify("ไม่พบ S2 ล่าสุด ไม่สามารถข้ามไป S3 ได้", "error")
                st.stop()
            elif code == "S4" and (lastScan is None or pd.isna(lastScan["Barcode3"])):
                notify("ไม่พบ S3 ล่าสุด ไม่สามารถข้ามไป S4 ได้", "error")
                st.stop()

            # 3️⃣ Save to Google Sheet
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

            st.success(f"✅ สแกน {code} สำเร็จ และบันทึกข้อมูลเรียบร้อย @ {ts.strftime('%H:%M:%S')}")

        except Exception as e:
            st.error(f"❌ เกิดข้อผิดพลาดในการบันทึก: {e}")

# ============================================
# 📊 Display Google Sheet Data
# ============================================
st.divider()
st.subheader("📋 ข้อมูลทั้งหมดใน Google Sheet")

try:
    df = get_all_scans()
    st.dataframe(df)
except Exception as e:
    st.error(f"Cannot fetch Google Sheet: {e}")

