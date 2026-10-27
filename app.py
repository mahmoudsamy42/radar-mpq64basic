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
    page_title="تحليل التضاريس والرادار - الدفاع الجوي",
    page_icon="📡",
    layout="centered"
)

# --- ترويسة التطبيق ---
st.markdown("<h1 style='text-align: center; color: #f1f2f6;'>قـوات الـدفاع الـجوي</h1>", unsafe_allow_html=True)
st.markdown("<h3 style='text-align: center; color: #ffa502; font-style: italic;'>إعداد نقيب/محمود سامي للشابرال</h3>", unsafe_allow_html=True)
st.markdown("---")

# --- ملف السجل الخارجي ---
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

def fetch_elevation_profile(center_lat, center_lon, current_radar_alt):
    azimuths = np.linspace(0, 359, 360)
    max_ranges = np.ones(360) * 40.0
    masked_sectors = np.zeros(360, dtype=bool)

    with st.spinner('⏳ جاري استعلام التضاريس وتحليل زوايا الحجب عبر الـ API...'):
        try:
            for az in range(0, 360, 5):
                for dist in [10, 20, 30]:
                    d_lat, d_lon = get_destination_coordinate(center_lat, center_lon, dist, az)
                    url = f"https://api.open-elevation.com/api/v1/lookup?locations={d_lat},{d_lon}"
                    response = requests.get(url, timeout=2)
                    
                    if response.status_code == 200:
                        data = response.json()
                        peak_elevation = data['results'][0]['elevation']
                        
                        if peak_elevation > current_radar_alt:
                            tan_mask = (peak_elevation - current_radar_alt) / (dist * 1000)
                            if tan_mask > 0.02: 
                                for sub_az in range(az, az + 5):
                                    if sub_az < 360:
                                        max_ranges[sub_az] = dist
                                        masked_sectors[sub_az] = True
                        break
        except Exception:
            pass

    return np.radians(azimuths), max_ranges, masked_sectors

if st.button("🚀 بدء تحليل تضاريس الموقع ورسم غلاف الكشف", use_container_width=True):
    azimuths, max_ranges, masked_sectors = fetch_elevation_profile(lat, lon, radar_alt)

    fig, ax = plt.subplots(subplot_kw={'projection': 'polar'}, figsize=(6, 6))
    fig.patch.set_facecolor('#1e272e')
    ax.set_facecolor('#0f171e')

    ax.plot(azimuths, max_ranges, color='#00d2d3', linewidth=2.5, label='Radar Coverage')
    ax.fill(azimuths, max_ranges, color='#00d2d3', alpha=0.25)

    shadow_indices = np.where(masked_sectors)[0]
    if len(shadow_indices) > 0:
        ax.fill_between(azimuths, 0, np.where(masked_sectors, max_ranges, 0), color='#ff4757', alpha=0.4, label='Terrain Masking')

    ax.set_theta_zero_location('N')
    ax.set_theta_direction(-1)
    ax.set_rticks([10, 20, 30, 40])
    ax.set_rlabel_position(45)
    ax.tick_params(colors='white', labelsize=8)
    ax.grid(color='#718093', linestyle='--', linewidth=0.5)
    
    ax.set_title(f"Sentinel Radar | Lat: {lat}, Lon: {lon}\nTarget Alt: {target_alt}m", color='white', va='bottom', fontsize=10, fontweight='bold', pad=15)
    ax.legend(loc='upper right', bbox_to_anchor=(1.35, 1.1), facecolor='#2f3640', edgecolor='none', labelcolor='white', fontsize=8)

    st.pyplot(fig)
    st.success("تم الانتهاء من التحليل الجغرافي للقطاعات السمتية بنجاح.")

if os.path.exists(LOG_FILE):
    with st.expander("📋 عرض سجل المواقع المحفوظة سابقاً"):
        df_view = pd.read_csv(LOG_FILE)
        st.dataframe(df_view, use_container_width=True)
