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
    """โหลดข้อมูลจาก sheet scan (ดึงทุกแถวจาก Google Sheets)"""
    data = scan_sheet.get_all_values()  # ดึงค่าทั้งหมด (รวม header)
    
    # ถ้ามีข้อมูลใน sheet
    if len(data) > 1:
        headers = data[0]                       # แถวแรกเป็นชื่อคอลัมน์
        rows = data[1:]                         # ข้อมูลจริงตั้งแต่แถวที่สอง
        df = pd.DataFrame(rows, columns=headers)
    elif len(data) == 1:
        # มีแต่ header แถวเดียว
        df = pd.DataFrame(columns=data[0])
    else:
        # ไม่มีข้อมูลเลย
        df = pd.DataFrame(columns=["ColumnA"])
    
    return df

def lookup_station(code):
    match = colStations[colStations["Code"] == code]
    return match["Name"].iloc[0] if not match.empty else "Unknown Station"

def update_last_row(index, row_dict, sheet):
    for i, (k, v) in enumerate(row_dict.items(), start=1):
        sheet.update_cell(index + 2, i, v)

def notify(message, type="info"):
    if type == "warning":
        st.warning(message)
    elif type == "error":
        st.error(message)
    else:
        st.info(message)

def append_to_sheet(row_dict):
    scan_sheet.append_row(list(row_dict.values()))

def append_to_billing(row_dict):
    """บันทึกข้อมูลลง sheet billing"""
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

    colStations = pd.DataFrame({
        "Code": ["S1", "S2", "S3", "S4"],
        "Name": ["ขึ้นสินค้า", "ขึ้นสินค้าเสร็จ", "ส่งเอกสาร", "ออกเอกสารเสร็จ"]
    })

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
        st.warning("⚠️ ไม่พบ QR Code ในภาพ กรุณาสแกนใหม่")

# ============================================
# 🧠 Main Logic
# ============================================
if not plate.strip():
    st.warning("⚠️ กรุณากรอกทะเบียนรถก่อนสแกน QR Code")
    st.stop()

if barcode_input:
    code = barcode_input
    if code not in ["S1", "S2", "S3", "S4"]:
        st.error("⚠️ QR Code ไม่ถูกต้อง (ต้องเป็น S1, S2, S3 หรือ S4 เท่านั้น)")
    else:
        try:
            tz = pytz.timezone("Asia/Bangkok")
            ts = datetime.now(tz)
            df = get_all_scans()
            staName = lookup_station(code)
            lastScan = df[df["ทะเบียนรถ"] == plate].sort_values("ScanDateTime", ascending=False).head(1)
            lastScan = lastScan.iloc[0] if not lastScan.empty else None

            # ✅ Define Station Order
            station_order = {"S1": 1, "S2": 2, "S3": 3, "S4": 4}

            if lastScan is not None:
                # หา station ล่าสุดที่ไม่ว่าง
                last_code = None
                for c in ["Barcode4", "Barcode3", "Barcode2", "Barcode"]:
                    if pd.notna(lastScan.get(c)) and lastScan[c] != "":
                        last_code = lastScan[c]
                        break

                # ✅ ห้ามสแกนสลับลำดับย้อนหลัง
                if last_code and station_order[code] < station_order[last_code]:
                    st.error(f"❌ ลำดับการสแกนไม่ถูกต้อง (ล่าสุดคือ {last_code} แต่พยายามสแกน {code})")
                    st.stop()

                # ✅ ห้ามข้ามสถานี
                if last_code and station_order[code] > station_order[last_code] + 1:
                    expected_next = [k for k, v in station_order.items() if v == station_order[last_code] + 1][0]
                    st.error(f"⚠️ ไม่สามารถข้ามจาก {last_code} ไป {code} ได้ ต้องสแกน {expected_next} ก่อน")
                    st.stop()

                # ✅ ห้ามสแกนซ้ำโดยไม่มีเหตุผล
                if code == last_code and not (
                    (code == "S3" and reason.strip() != "") or
                    (code == "S4" and pd.notna(lastScan["สาเหตุ"]))
                ):
                    notify(f"ไม่สามารถสแกน {code} ซ้ำได้", "warning")
                    st.stop()

            # ✅ ต้องเริ่มจาก S1 เสมอ
            if code != "S1" and lastScan is None:
                st.error("❌ ต้องเริ่มจากการสแกน S1 ก่อนเท่านั้น")
                st.stop()

            # ✅ Save to Google Sheet
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
                update_last_row(idx, update_dict, scan_sheet)

            st.success(f"✅ สแกน {code} สำเร็จ และบันทึกข้อมูลเรียบร้อย @ {ts.strftime('%H:%M:%S')}")

        except Exception as e:
            st.error(f"❌ เกิดข้อผิดพลาดในการบันทึก: {e}")

# ============================================
# 📋 แสดงข้อมูลทั้งหมดใน Sheet
# ============================================
st.divider()
st.subheader("📋 ข้อมูลทั้งหมดใน Google Sheet (scan)")
try:
    df = get_all_scans()
    st.dataframe(df)
except Exception as e:
    st.error(f"Cannot fetch Google Sheet: {e}")

# ============================================
# 💳 PAGE 2: Billing Page (Protected)
# ============================================
elif page == "📋 Billing Page":
    st.title("📋 ระบบบันทึกข้อมูลใบแจ้งหนี้ (Billing)")

    # 🔐 Require Access Code
    with st.expander("🔒 ใส่รหัสเพื่อเข้าหน้า Billing"):
        access_code = st.text_input("กรอกรหัสผ่านเพื่อเข้าหน้า Billing:", type="password")
        if access_code != "TCRY2025":
            st.warning("❌ กรุณากรอกรหัสผ่านที่ถูกต้อง")
            st.stop()

    # ✅ โหลดข้อมูลจาก sheet
    df_scan = get_all_scans()

    # ✅ ตรวจว่ามีข้อมูลและมีคอลัมน์อย่างน้อย 1 คอลัมน์
    if not df_scan.empty and df_scan.shape[1] > 0:
        # ใช้คอลัมน์แรก (Column A)
        unique_plates = (
            df_scan.iloc[:, 0]                # เลือกคอลัมน์แรก
            .astype(str)
            .str.strip()
            .replace("", pd.NA)
            .dropna()
            .unique()
            .tolist()
        )
        unique_plates = sorted(unique_plates)
    else:
        unique_plates = []
        st.warning("⚠️ ไม่มีข้อมูลใน sheet scan หรือไม่มีคอลัมน์")

    # ✅ UI ส่วนเลือกข้อมูล
    plate = st.selectbox("เลือกทะเบียนรถจากฐานข้อมูล:", unique_plates)

    reason_options = [
        "",
        "เก็บป้ายมอบมาไม่ครบ",
        "ขึ้นงานไม่ครบตามแผน",
        "รวมยอดสินค้าผิด",
        "ใส่จำนวน/ประเภทพาเลทผิด",
        "อื่นๆ (ระบุ)"
    ]
    reason = st.selectbox("สาเหตุ (เลือกถ้ามี):", reason_options)

    # ✅ ปุ่มบันทึกข้อมูล Billing
    if st.button("💾 บันทึกข้อมูล Billing"):
        if not plate:
            st.warning("⚠️ กรุณาเลือกทะเบียนรถก่อนบันทึก")
        else:
            try:
                tz = pytz.timezone("Asia/Bangkok")
                ts = datetime.now(tz)

                # ✅ ดึงค่า Time3 (คอลัมน์ K = index 10) ของทะเบียนล่าสุด
                df_filtered = df_scan[df_scan.iloc[:, 0].astype(str).str.strip() == plate]
                if not df_filtered.empty and df_filtered.shape[1] > 10:
                    last_time3 = df_filtered.iloc[-1, 11]  # คอลัมน์ที่ 11 (K)
                else:
                    last_time3 = ""

                # ✅ เตรียมข้อมูลสำหรับบันทึก
                new_row = {
                    "ทะเบียนรถ": plate,
                    "สาเหตุ": reason,
                    "Time3": last_time3,
                    "วันที่เวลา": ts.strftime("%Y-%m-%d %H:%M:%S")
                }

                append_to_billing(new_row)
                st.success(f"✅ บันทึกข้อมูลเรียบร้อย @ {ts.strftime('%H:%M:%S')} (Time3: {last_time3})")

            except Exception as e:
                st.error(f"❌ เกิดข้อผิดพลาดในการบันทึก: {e}")

    st.divider()
    st.subheader("📊 ข้อมูลใน Google Sheet (billing)")
    try:
        data_billing = billing_sheet.get_all_records()
        df_billing = pd.DataFrame(data_billing)
        st.dataframe(df_billing)
    except Exception as e:
        st.error(f"Cannot fetch billing sheet: {e}")
