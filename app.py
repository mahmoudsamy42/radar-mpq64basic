import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
import requests
import math
import pandas as pd
from datetime import datetime
import os

# --- إعدادات صفحة الويب العسكرية ---
st.set_page_config(
    page_title="AN/MPQ-64 Radar Plotter & Tactical Simulator",
    page_icon="📡",
    layout="centered"
)

# --- ترويسة التطبيق الاحترافية ---
st.markdown("<h2 style='text-align: center; color: #f1f2f6; margin-bottom: 0px;'>AN/MPQ-64 Radar Plotter</h2>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: #718093; font-size: 13px;'>1cm = 2km Scale | Envelope & Tactical Terrain Simulator</p>", unsafe_allow_html=True)
st.markdown("<h4 style='text-align: center; color: #ffa502; font-style: italic; margin-top: 5px;'>قوات الدفاع الجوي - إهداء النقيب محمود سامي</h4>", unsafe_allow_html=True)
st.markdown("---")

LOG_FILE = "radar_locations_log.csv"

# --- لوحة التحكم الجانبية ---
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

default_lat, default_lon, default_radar_alt = 30.1789, 32.4485, 10.0

if selected_saved != "موقع جديد (يدوي)":
    try:
        parts = selected_saved.split("|")
        default_lat = float(parts[1].split(":")[1].strip())
        default_lon = float(parts[2].split(":")[1].strip())
        matched_row = df_log[(df_log['خط العرض (Lat)'] == default_lat) & (df_log['خط الطول (Lon)'] == default_lon)]
        if not matched_row.empty:
            default_radar_alt = float(matched_row.iloc[0]['ارتفاع الرادار (م)'])
    except Exception:
        pass

lat = st.sidebar.number_input("خط العرض (Lat)", value=default_lat, format="%.4f")
lon = st.sidebar.number_input("خط الطول (Lon)", value=default_lon, format="%.4f")
radar_alt = st.sidebar.number_input("ارتفاع الرادار (م)", value=default_radar_alt, format="%.1f")

# --- غلاف ارتفاع الهدف ($H_t$) ---
st.markdown("##### Target Altitude Envelope ($H_t$):")
target_alt_col1, target_alt_col2, target_alt_col3, target_alt_col4 = st.columns(4)
with target_alt_col1:
    b50 = st.button("50m")
with target_alt_col2:
    b100 = st.button("100m", type="primary")
with target_alt_col3:
    b300 = st.button("300m")
with target_alt_col4:
    b500 = st.button("500m")

if 'target_alt' not in st.session_state:
    st.session_state.target_alt = 100.0

if b50: st.session_state.target_alt = 50.0
if b100: st.session_state.target_alt = 100.0
if b300: st.session_state.target_alt = 300.0
if b500: st.session_state.target_alt = 500.0

target_alt = st.session_state.target_alt

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

# --- زر بدء المسح الجغرافي الفعلي ---
run_scan = st.button("🚀 بدء المسح الجغرافي الفعلي ورسم دائرة الكشف", use_container_width=True)

def perform_terrain_scan(center_lat, center_lon, current_radar_alt, current_target_alt):
    azimuths = np.linspace(0, 359, 360)
    max_ranges = np.ones(360) * 40.0  
    masked_sectors = np.zeros(360, dtype=bool)
    elevations_profile = np.zeros(360)
    barrier_names = {}

    progress_bar = st.progress(0)
    status_text = st.empty()

    for i, az in enumerate(range(0, 360, 5)):
        progress_bar.progress((i + 1) / 72)
        status_text.text(f"جاري مسح الاتجاه السمتي: {az}° ...")
        
        peak_el = current_radar_alt
        is_masked = False
        
        for dist in [5, 10, 15, 20, 25, 30, 35, 40]:
            try:
                d_lat, d_lon = get_destination_coordinate(center_lat, center_lon, dist, az)
                url = f"https://api.open-elevation.com/api/v1/lookup?locations={d_lat},{d_lon}"
                res = requests.get(url, timeout=1.0)
                if res.status_code == 200:
                    elevation = res.json()['results'][0]['elevation']
                else:
                    elevation = current_radar_alt
            except:
                elevation = current_radar_alt
                
            peak_el = max(peak_el, elevation)
            
            # تأثير ارتفاع الهدف الحقيقي على زاوية الحجب
            effective_obstacle = elevation - current_target_alt
            if effective_obstacle > current_radar_alt:
                tan_mask = (effective_obstacle - current_radar_alt) / (dist * 1000)
                if tan_mask > 0.003: 
                    for sub_az in range(az, az + 5):
                        if sub_az < 360:
                            max_ranges[sub_az] = dist
                            masked_sectors[sub_az] = True
                            elevations_profile[sub_az] = elevation
                            if 180 <= sub_az <= 260:
                                barrier_names[sub_az] = "Gebel Attaka / Galala Ridge"
                            elif 280 <= sub_az <= 340:
                                barrier_names[sub_az] = "Western Desert Escarpment"
                            else:
                                barrier_names[sub_az] = "Local Terrain Obstacle"
                    is_masked = True
                    break
        
        if not is_masked:
            for sub_az in range(az, az + 5):
                if sub_az < 360:
                    elevations_profile[sub_az] = peak_el
                    barrier_names[sub_az] = "Clear Horizon"

    progress_bar.empty()
    status_text.empty()
    return azimuths, max_ranges, masked_sectors, elevations_profile, barrier_names

# تخزين واستدعاء البيانات عبر الجلسة
if run_scan or 'scanned_data' not in st.session_state:
    with st.spinner("📡 جاري استعلام التضاريس الجغرافية الفعلية للإحداثي..."):
        azimuths, max_ranges, masked_sectors, elevations_profile, barrier_names = perform_terrain_scan(lat, lon, radar_alt, target_alt)
        st.session_state['scanned_data'] = {
            'azimuths': azimuths, 'max_ranges': max_ranges, 'masked_sectors': masked_sectors,
            'elevations_profile': elevations_profile, 'barrier_names': barrier_names,
            'lat': lat, 'lon': lon, 'radar_alt': radar_alt, 'target_alt': target_alt
        }
else:
    d = st.session_state['scanned_data']
    if d['lat'] != lat or d['lon'] != lon or d['radar_alt'] != radar_alt or d['target_alt'] != target_alt:
        azimuths, max_ranges, masked_sectors, elevations_profile, barrier_names = perform_terrain_scan(lat, lon, radar_alt, target_alt)
        st.session_state['scanned_data'] = {
            'azimuths': azimuths, 'max_ranges': max_ranges, 'masked_sectors': masked_sectors,
            'elevations_profile': elevations_profile, 'barrier_names': barrier_names,
            'lat': lat, 'lon': lon, 'radar_alt': radar_alt, 'target_alt': target_alt
        }

d = st.session_state['scanned_data']
azimuths = d['azimuths']
max_ranges = d['max_ranges']
masked_sectors = d['masked_sectors']
elevations_profile = d['elevations_profile']
barrier_names = d['barrier_names']

# --- مؤشر توجيه الشعاع (Beam Steering Azimuth) ---
st.markdown("##### Beam Steering (Azimuth):")
beam_azimuth = st.slider("الازيموث بالدرجات:", 0, 359, 211, label_visibility="collapsed")
beam_mils = int(beam_azimuth * (6400 / 360))

cur_range = max_ranges[beam_azimuth]
cur_elevation = elevations_profile[beam_azimuth]
is_masked = masked_sectors[beam_azimuth]
paper_dist_cm = cur_range / 2.0  # مقياس 1سم = 2كم
paper_dist_mm = paper_dist_cm * 10.0
max_scope_pct = int((cur_range / 40.0) * 100)
mask_angle = round(math.degrees(math.atan((cur_elevation - radar_alt) / (cur_range * 1000))) if cur_range > 0 and cur_elevation > radar_alt else 0.0, 1)
facing_barrier = barrier_names.get(beam_azimuth, "Clear Horizon")

# --- لوحة المعلومات التكتيكية الاحترافية ---
col_m1, col_m2 = st.columns(2)
with col_m1:
    st.markdown(f"""
    <div style="background-color: #1e272e; padding: 12px; border-radius: 8px; border: 1px solid #3d3d3d;">
        <span style="color: #a4b0be; font-size: 12px;">Beam Azimuth</span><br>
        <span style="color: #ffffff; font-size: 24px; font-weight: bold;">{beam_azimuth}°</span><br>
        <span style="color: #00d2d3; font-size: 14px;">{beam_mils} MILS</span>
    </div>
    """, unsafe_allow_html=True)

with col_m2:
    st.markdown(f"""
    <div style="background-color: #1e272e; padding: 12px; border-radius: 8px; border: 1px solid #3d3d3d;">
        <span style="color: #a4b0be; font-size: 12px;">Paper Plot Distance</span><br>
        <span style="color: #ffffff; font-size: 24px; font-weight: bold;">{paper_dist_cm:.1f} cm</span><br>
        <span style="color: #00d2d3; font-size: 14px;">{int(paper_dist_mm)} mm on ruler</span>
    </div>
    """, unsafe_allow_html=True)

st.write("")
col_m3, col_m4 = st.columns(2)
with col_m3:
    st.markdown(f"""
    <div style="background-color: #1e272e; padding: 12px; border-radius: 8px; border: 1px solid #3d3d3d;">
        <span style="color: #a4b0be; font-size: 12px;">Max Tactical Range</span><br>
        <span style="color: #ffffff; font-size: 22px; font-weight: bold;">{cur_range:.1f} km</span><br>
        <span style="color: #ffa502; font-size: 13px;">{max_scope_pct}% of max scope</span>
    </div>
    """, unsafe_allow_html=True)

with col_m4:
    st.markdown(f"""
    <div style="background-color: #1e272e; padding: 12px; border-radius: 8px; border: 1px solid #3d3d3d;">
        <span style="color: #a4b0be; font-size: 12px;">Min Detect Altitude ($H_t$: {int(target_alt)}m)</span><br>
        <span style="color: #ffffff; font-size: 22px; font-weight: bold;">{int(cur_elevation + target_alt)} m</span><br>
        <span style="color: #ffa502; font-size: 13px;">Mask: {mask_angle}°</span>
    </div>
    """, unsafe_allow_html=True)

st.markdown(f"""
<div style="background-color: #1e272e; padding: 10px; border-radius: 8px; border: 1px solid #3d3d3d; margin-top: 10px;">
    <span style="color: #a4b0be; font-size: 12px;">Facing Barrier:</span> <span style="color: #00d2d3; font-weight: bold;">{facing_barrier}</span><br>
    <span style="color: #a4b0be; font-size: 12px;">Peak Elevation:</span> <span style="color: #ffffff; font-weight: bold;">{int(cur_elevation)} m</span> &nbsp;&nbsp;&nbsp; 
    <span style="color: #a4b0be; font-size: 12px;">Distance:</span> <span style="color: #ffffff; font-weight: bold;">{cur_range:.1f} km</span>
</div>
""", unsafe_allow_html=True)

# --- الخريطة الجغرافية الفعلية للموقع ---
st.markdown("##### 🗺️ الخريطة الجغرافية الميدانية للموقع:")
try:
    import folium
    from streamlit_folium import st_folium
    m = folium.Map(location=[lat, lon], zoom_start=11, tiles="CartoDB dark_matter")
    folium.Marker(
        [lat, lon],
        popup=f"Sentinel Radar Position<br>Lat: {lat}, Lon: {lon}",
        icon=folium.Icon(color="red", icon="radar", prefix="fa")
    ).add_to(m)
    st_folium(m, height=250, width=700)
except Exception:
    st.info(f"إحداثيات الموقع الحالي: Lat: {lat} , Lon: {lon}")

# --- رسم دائرة الكشف الراداري (PPI Scope) ---
fig, ax = plt.subplots(subplot_kw={'projection': 'polar'}, figsize=(6, 6))
fig.patch.set_facecolor('#0f171e')
ax.set_facecolor('#0f171e')

rad_azimuths = np.radians(azimuths)
ax.plot(rad_azimuths, max_ranges, color='#00d2d3', linewidth=2)
ax.fill(rad_azimuths, max_ranges, color='#00d2d3', alpha=0.2)

shadow_indices = np.where(masked_sectors)[0]
if len(shadow_indices) > 0:
    ax.fill_between(rad_azimuths, 0, np.where(masked_sectors, max_ranges, 0), color='#ff4757', alpha=0.5)

cursor_rad = math.radians(beam_azimuth)
ax.plot([cursor_rad, cursor_rad], [0, cur_range], color='#ffa502', linewidth=2.5, linestyle='-')
ax.scatter([cursor_rad], [cur_range], color='#ffffff', s=80, zorder=5)

ax.set_theta_zero_location('N')
ax.set_theta_direction(-1)
ax.set_rticks([10, 20, 30, 40])
ax.set_rlabel_position(45)
ax.tick_params(colors='white', labelsize=8)
ax.grid(color='#718093', linestyle='--', linewidth=0.5)

st.pyplot(fig)

if os.path.exists(LOG_FILE):
    with st.expander("📋 عرض سجل المواقع المحفوظة سابقاً"):
        df_view = pd.read_csv(LOG_FILE)
        st.dataframe(df_view, use_container_width=True)
