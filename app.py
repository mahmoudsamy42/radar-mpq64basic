import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
import requests
import math
import pandas as pd
from datetime import datetime
import os

# --- إعدادات صفحة الويب ---
st.set_page_config(
    page_title="تحليل التضاريس والرادار المتقدم - الدفاع الجوي",
    page_icon="📡",
    layout="centered"
)

# --- ترويسة التطبيق ---
st.markdown("<h1 style='text-align: center; color: #f1f2f6;'>قـوات الـدفاع الـجوي</h1>", unsafe_allow_html=True)
st.markdown("<h3 style='text-align: center; color: #ffa502; font-style: italic;'>إهداء النقيب محمود سامي للشابرال</h3>", unsafe_allow_html=True)
st.markdown("---")

LOG_FILE = "radar_locations_log.csv"

# --- لوحة التحكم وإدخال البيانات ---
st.sidebar.header("⚙️ إعدادات الموقع والرادار")

saved_options = ["موقع جديد (يدوي)"]
if os.path.exists(LOG_FILE):
    try:
        df_log = pd.read_csv(LOG_FILE)
        if not df_log.empty:
            for idx, row in df_log.iterrows():
                saved_options.append(f"{row['التوقيت']} | Lat: {row['خط العرض (Lat)']} , Lon: {row['خط الطول (Lon)']}")
    except Exception:
        pass

selected_saved = st.sidebar.selectbox("📂 استرجاع موقع محفوظ:", saved_options)

default_lat, default_lon, default_radar_alt, default_target_alt = 29.9668, 32.5498, 10.0, 100.0

if selected_saved != "موقع جديد (يدوي)":
    try:
        parts = selected_saved.split("|")
        default_lat = float(parts[1].split(":")[1].strip())
        default_lon = float(parts[2].split(":")[1].strip())
        matched_row = df_log[(df_log['خط العرض (Lat)'] == default_lat) & (df_log['خط الطول (Lon)'] == default_lon)]
        if not matched_row.empty:
            default_radar_alt = float(matched_row.iloc[0]['ارتفاع الرادار (م)'])
            default_target_alt = float(matched_row.iloc[0]['ارتفاع الهدف (م)'])
    except Exception:
        pass

lat = st.sidebar.number_input("خط العرض (Lat)", value=default_lat, format="%.4f")
lon = st.sidebar.number_input("خط الطول (Lon)", value=default_lon, format="%.4f")
radar_alt = st.sidebar.number_input("ارتفاع الرادار (م)", value=default_radar_alt, format="%.1f")
target_alt = st.sidebar.number_input("ارتفاع الهدف (م)", value=default_target_alt, format="%.1f")

if st.sidebar.button("💾 حفظ الموقع بالسجل"):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    file_exists = os.path.exists(LOG_FILE)
    new_data = pd.DataFrame([[timestamp, lat, lon, radar_alt, target_alt]], 
                            columns=["التوقيت", "خط العرض (Lat)", "خط الطول (Lon)", "ارتفاع الرادار (م)", "ارتفاع الهدف (م)"])
    if file_exists:
        new_data.to_csv(LOG_FILE, mode='a', header=False, index=False, encoding='utf-8-sig')
    else:
        new_data.to_csv(LOG_FILE, index=False, encoding='utf-8-sig')
    st.sidebar.success("تم حفظ الموقع بنجاح!")

def get_destination_coordinate(lat, lon, distance_km, azimuth_deg):
    R = 6371.0 
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    az_rad = math.radians(azimuth_deg)

    dest_lat_rad = math.asin(math.sin(lat_rad) * math.cos(distance_km / R) +
                             math.cos(lat_rad) * math.sin(distance_km / R) * math.cos(az_rad))
    dest_lon_rad = lon_rad + math.atan2(math.sin(az_rad) * math.sin(distance_km / R) * math.cos(lat_rad),
                                        math.cos(distance_km / R) - math.sin(lat_rad) * math.sin(dest_lat_rad))
    return math.degrees(dest_lat_rad), math.degrees(dest_lon_rad)

# --- دالة جلب المسح الجغرافي الشامل وزوايا الحجب ---
def fetch_comprehensive_terrain_scan(center_lat, center_lon, current_radar_alt):
    azimuths = np.linspace(0, 359, 360)
    max_ranges = np.ones(360) * 40.0  # المدى الأقصى للرادار 40 كم
    masked_sectors = np.zeros(360, dtype=bool)
    elevations_profile = np.zeros(360)

    with st.spinner('⏳ جاري المسح الشامل للتضاريس الجغرافية واستعلام الارتفاعات الحية...'):
        try:
            for az in range(0, 360, 5): # فحص كل 5 درجات لتغطية كاملة
                detected_mask = False
                peak_el = current_radar_alt
                for dist in [5, 10, 15, 20, 25, 30, 35, 40]:
                    d_lat, d_lon = get_destination_coordinate(center_lat, center_lon, dist, az)
                    url = f"https://api.open-elevation.com/api/v1/lookup?locations={d_lat},{d_lon}"
                    response = requests.get(url, timeout=1.5)
                    
                    if response.status_code == 200:
                        data = response.json()
                        elevation = data['results'][0]['elevation']
                        peak_el = max(peak_el, elevation)
                        
                        # حساب زاوية الحجب التضاريسي
                        if elevation > current_radar_alt:
                            tan_mask = (elevation - current_radar_alt) / (dist * 1000)
                            if tan_mask > 0.015: # معامل الحجب التكتيكي
                                for sub_az in range(az, az + 5):
                                    if sub_az < 360:
                                        max_ranges[sub_az] = dist
                                        masked_sectors[sub_az] = True
                                        elevations_profile[sub_az] = elevation
                                detected_k = True
                                break
                if not detected_mask:
                    for sub_az in range(az, az + 5):
                        if sub_az < 360:
                            elevations_profile[sub_az] = peak_el
        except Exception:
            pass

    return azimuths, max_ranges, masked_sectors, elevations_profile

# --- زر التشغيل الرئيسي ---
if st.button("🚀 بدء المسح الجغرافي ورسم دائرة الكشف الراداري", use_container_width=True):
    azimuths, max_ranges, masked_sectors, elevations_profile = fetch_comprehensive_terrain_scan(lat, lon, radar_alt)
    
    # حفظ النتائج في الذاكرة المؤقتة لجلسة الاستخدام لتفعيل المؤشر اليدوي بسلاسة
    st.session_state['azimuths'] = azimuths
    st.session_state['max_ranges'] = max_ranges
    st.session_state['masked_sectors'] = masked_sectors
    st.session_state['elevations_profile'] = elevations_profile

# --- التحقق من وجود البيانات لعرض المخطط والمؤشر اليدوي ---
if 'azimuths' in st.session_state:
    azimuths = st.session_state['azimuths']
    max_ranges = st.session_state['max_ranges']
    masked_sectors = st.session_state['masked_sectors']
    elevations_profile = st.session_state['elevations_profile']

    st.markdown("### 🎛️ المؤشر التكتيكي اليدوي على دائرة الكشف (Radar Cursor)")
    cursor_azimuth = st.slider("حدد اتجاه المؤشر (الازيموث بالدرجات):", 0, 359, 0)
    
    # استخراج بيانات النقطة الحالية للمؤشر
    cur_range = max_ranges[cursor_azimuth]
    cur_elevation = elevations_profile[cursor_azimuth]
    is_masked = masked_sectors[cursor_azimuth]

    # عرض لوحة معلومات النقطة المحددة بالمؤشر
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("الازيموث (الزاوية)", f"{cursor_azimuth}°")
    col2.metric("المدى الفعّال", f"{cur_range} كم")
    col3.metric("ارتفاع التضاريس", f"{cur_elevation:.1f} م")
    col4.metric("حالة القطاع", "حجب (مظلل)" if is_masked else "كشف مكشوف", 
                delta_color="inverse" if is_masked else "normal")

    # --- رسم دائرة الكشف الراداري (Polar PPI Scope) ---
    fig, ax = plt.subplots(subplot_kw={'projection': 'polar'}, figsize=(6, 6))
    fig.patch.set_facecolor('#1e272e')
    ax.set_facecolor('#0f171e')

    rad_azimuths = np.radians(azimuths)
    ax.plot(rad_azimuths, max_ranges, color='#00d2d3', linewidth=2, label='Radar Coverage')
    ax.fill(rad_azimuths, max_ranges, color='#00d2d3', alpha=0.2)

    shadow_indices = np.where(masked_sectors)[0]
    if len(shadow_indices) > 0:
        ax.fill_between(rad_azimuths, 0, np.where(masked_sectors, max_ranges, 0), color='#ff4757', alpha=0.4, label='Terrain Masking')

    # رسم خط مؤشر الموجه اليدوي بلون مميز (أصفر ساطع)
    cursor_rad = math.radians(cursor_azimuth)
    ax.plot([cursor_rad, cursor_rad], [0, cur_range], color='#ffa502', linewidth=3, linestyle='-', label=f'Cursor ({cursor_azimuth}°)')
    ax.scatter([cursor_rad], [cur_range], color='#ffa502', s=100, zorder=5)

    ax.set_theta_zero_location('N')
    ax.set_theta_direction(-1)
    ax.set_rticks([10, 20, 30, 40])
    ax.set_rlabel_position(45)
    ax.tick_params(colors='white', labelsize=8)
    ax.grid(color='#718093', linestyle='--', linewidth=0.5)
    
    ax.set_title(f"Sentinel Radar Coverage Plot | Lat: {lat}, Lon: {lon}", color='white', va='bottom', fontsize=9, fontweight='bold', pad=15)
    ax.legend(loc='upper right', bbox_to_anchor=(1.35, 1.1), facecolor='#2f3640', edgecolor='none', labelcolor='white', fontsize=7)

    st.pyplot(fig)
    st.success("تم إتمام المسح الجغرافي ودائرة الكشف وتفعيل المؤشر اليدوي بنجاح.")

if os.path.exists(LOG_FILE):
    with st.expander("📋 عرض سجل المواقع المحفوظة سابقاً"):
        df_view = pd.read_csv(LOG_FILE)
        st.dataframe(df_view, use_container_width=True)
