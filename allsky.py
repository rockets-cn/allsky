import cv2
import datetime
import numpy as np
import os
from flask import Flask, request, jsonify, send_file
from astral import LocationInfo
from astral.sun import sun
# 新增字体支持
from cv2 import FONT_HERSHEY_SIMPLEX

# 初始化 Flask 应用程序
app = Flask(__name__)

# USB 摄像头的设备索引
CAMERA_INDEX = 0
# 输出图像的存储路径
OUTPUT_PATH = "./all_sky_images"

# 创建输出目录
if not os.path.exists(OUTPUT_PATH):
    os.makedirs(OUTPUT_PATH)

# 全局设置
settings = {
    'day': {'exposure': -5, 'gain': 10},
    'civil': {'exposure': -2, 'gain': 15},
    'nautical': {'exposure': 0, 'gain': 20},
    'astronomical': {'exposure': 3, 'gain': 30},
    'night': {'exposure': 5, 'gain': 40}
}

# 定位信息，用于计算日出和日落时间（使用上海为例）
city = LocationInfo("Shanghai", "China", "Asia/Shanghai", 31.2304, 121.4737)

# 全局观测站参数，支持动态配置
station_info = {
    'name': 'Jiamuerdeng Tianwentai',
    'latitude': 31.2304,
    'longitude': 121.4737
}

def calculate_exposure_settings(current_time):
    """
    根据当前时间来计算摄像头的曝光设置，包括曝光时间和增益。
    参数:
        current_time (datetime): 当前的时间。
    返回:
        (float, int): 曝光时间和增益值。
    """
    s = sun(city.observer, date=current_time.date(), tzinfo=current_time.tzinfo)
    sunrise = s['sunrise']
    sunset = s['sunset']
    civil_dawn = s['civil_dawn']
    civil_dusk = s['civil_dusk']
    nautical_dawn = s['nautical_dawn']
    nautical_dusk = s['nautical_dusk']
    astronomical_dawn = s['astronomical_dawn']
    astronomical_dusk = s['astronomical_dusk']

    if sunrise <= current_time < sunset:
        return settings['day']['exposure'], settings['day']['gain']
    elif civil_dawn <= current_time < sunrise or sunset <= current_time < civil_dusk:
        return settings['civil']['exposure'], settings['civil']['gain']
    elif nautical_dawn <= current_time < civil_dawn or civil_dusk <= current_time < nautical_dusk:
        return settings['nautical']['exposure'], settings['nautical']['gain']
    elif astronomical_dawn <= current_time < nautical_dawn or nautical_dusk <= current_time < astronomical_dusk:
        return settings['astronomical']['exposure'], settings['astronomical']['gain']
    else:
        return settings['night']['exposure'], settings['night']['gain']

def configure_camera_settings(cap, exposure_time, gain):
    """
    设置摄像头的曝光时间和增益。
    参数:
        cap (cv2.VideoCapture): 摄像头对象。
        exposure_time (float): 曝光时间。
        gain (int): 增益值。
    """
    cap.set(cv2.CAP_PROP_EXPOSURE, float(exposure_time))
    cap.set(cv2.CAP_PROP_GAIN, float(gain))

def draw_info_overlay(frame, current_time, exposure_time, city, s):
    """
    在图片右上角叠加观测站信息、日出日落、时间、经纬度、曝光等。
    """
    overlay = frame.copy()
    h, w = frame.shape[:2]
    # 优先用 station_info
    name = station_info.get('name', 'Jiamuerdeng Tianwentai')
    lat = station_info.get('latitude', city.latitude)
    lon = station_info.get('longitude', city.longitude)
    # 信息内容
    lines = [
        (name, (0, 140, 255), 1.1),  # 观测站名，橙色
        (f"Sunrise: {s['sunrise'].strftime('%Y-%m-%d %H:%M:%S')}", (0, 255, 255), 0.7),
        (f"Sunset : {s['sunset'].strftime('%Y-%m-%d %H:%M:%S')}", (0, 255, 255), 0.7),
        (f"Time   : {current_time.strftime('%Y-%m-%d %H:%M:%S')}", (255, 255, 255), 0.7),
        (f"Lat: {lat:.4f}", (100, 255, 255), 0.7),
        (f"Long: {lon:.4f}", (100, 255, 255), 0.7),
        (f"Exp: {exposure_time:.0f} [s]", (100, 255, 255), 0.7)
    ]
    # 右上角起始坐标
    x0 = w - 370
    y0 = 38
    dy = 34
    # 右上角黑色半透明圆角背景
    bg_w = 360
    bg_h = len(lines)*dy + 18
    bg = overlay[y0-30:y0-30+bg_h, x0-18:x0-18+bg_w].copy()
    bg = cv2.rectangle(bg, (0,0), (bg_w-1,bg_h-1), (0,0,0), -1)
    overlay[y0-30:y0-30+bg_h, x0-18:x0-18+bg_w] = cv2.addWeighted(overlay[y0-30:y0-30+bg_h, x0-18:x0-18+bg_w], 0.3, bg, 0.7, 0)
    for i, (text, color, scale) in enumerate(lines):
        y = y0 + i * dy
        cv2.putText(overlay, text, (x0, y), FONT_HERSHEY_SIMPLEX, scale, color, 2, cv2.LINE_AA)
    # 融合
    alpha = 0.7
    frame = cv2.addWeighted(overlay, alpha, frame, 1-alpha, 0)
    return frame

def draw_compass_overlay(frame, direction=0):
    """
    在图片左上角绘制罗盘（圆环+N/E/S/W+指北箭头）。
    direction: 方位角，0为正北，顺时针，单位度。
    """
    overlay = frame.copy()
    h, w = frame.shape[:2]
    # 罗盘参数
    center = (90, 90)
    radius = 68
    # 画圆环
    cv2.circle(overlay, center, radius, (255,255,255), 2)
    # 画N/E/S/W
    font = FONT_HERSHEY_SIMPLEX
    font_scale = 0.8
    thickness = 2
    directions = ['N', 'E', 'S', 'W']
    angles = [0, 90, 180, 270]
    for d, a in zip(directions, angles):
        angle_rad = np.deg2rad(a - direction)
        x = int(center[0] + (radius+20)*np.sin(angle_rad) - 13)
        y = int(center[1] - (radius+20)*np.cos(angle_rad) + 13)
        color = (0, 140, 255) if d=='N' else (255,255,255)
        cv2.putText(overlay, d, (x, y), font, font_scale, color, thickness, cv2.LINE_AA)
    # 指北箭头
    arrow_angle = np.deg2rad(0 - direction)
    arrow_tip = (
        int(center[0] + (radius-12)*np.sin(arrow_angle)),
        int(center[1] - (radius-12)*np.cos(arrow_angle))
    )
    cv2.arrowedLine(overlay, center, arrow_tip, (0,0,255), 4, tipLength=0.32)
    # 半透明融合
    alpha = 0.6
    frame = cv2.addWeighted(overlay, alpha, frame, 1-alpha, 0)
    return frame

def draw_weather_overlay(frame, weather_data):
    """
    在图片左下角叠加气象数据。
    weather_data: dict，键为气象项，值为字符串。
    """
    overlay = frame.copy()
    h, w = frame.shape[:2]
    # 气象项及顺序
    items = [
        'Cloud Cover', 'Humidity', 'Dew Point', 'Pressure', 'Wind Speed',
        'Wind Gust', 'SkyTemperature', 'Temperature', 'Sky Quality', 'Rain Rate'
    ]
    x0 = 28
    y0 = h - 260
    dy = 26
    font = FONT_HERSHEY_SIMPLEX
    font_scale = 0.62
    color = (255, 255, 200)
    thickness = 1
    # 半透明背景
    bg_w = 260
    bg_h = len(items)*dy + 18
    bg = overlay[y0-22:y0-22+bg_h, x0-12:x0-12+bg_w].copy()
    bg = cv2.rectangle(bg, (0,0), (bg_w-1,bg_h-1), (0,0,0), -1)
    overlay[y0-22:y0-22+bg_h, x0-12:x0-12+bg_w] = cv2.addWeighted(overlay[y0-22:y0-22+bg_h, x0-12:x0-12+bg_w], 0.3, bg, 0.7, 0)
    for i, key in enumerate(items):
        value = weather_data.get(key, 'N/A')
        text = f"{key}: {value}"
        y = y0 + i * dy
        cv2.putText(overlay, text, (x0, y), font, font_scale, color, thickness, cv2.LINE_AA)
    alpha = 0.7
    frame = cv2.addWeighted(overlay, alpha, frame, 1-alpha, 0)
    return frame

def draw_logo_overlay(frame, logo_path):
    """
    在图片右下角叠加LOGO图片，支持缩放和透明度。
    """
    if not os.path.exists(logo_path):
        return frame  # 无LOGO文件则跳过
    logo = cv2.imread(logo_path, cv2.IMREAD_UNCHANGED)
    if logo is None:
        return frame
    h, w = frame.shape[:2]
    # 缩放LOGO（宽度为主图1/7，高度等比例）
    logo_w = w // 7
    scale = logo_w / logo.shape[1]
    logo_h = int(logo.shape[0] * scale)
    logo_resized = cv2.resize(logo, (logo_w, logo_h), interpolation=cv2.INTER_AREA)
    # 右下角坐标
    x1 = w - logo_w - 20
    y1 = h - logo_h - 20
    x2 = x1 + logo_w
    y2 = y1 + logo_h
    # 处理透明度（如果LOGO有alpha通道）
    if logo_resized.shape[2] == 4:
        alpha_logo = logo_resized[:, :, 3] / 255.0 * 0.85  # 透明度可调
        for c in range(3):
            frame[y1:y2, x1:x2, c] = (
                alpha_logo * logo_resized[:, :, c] +
                (1 - alpha_logo) * frame[y1:y2, x1:x2, c]
            ).astype(np.uint8)
    else:
        # 无alpha通道，直接叠加
        overlay = frame.copy()
        overlay[y1:y2, x1:x2] = logo_resized
        frame = cv2.addWeighted(overlay, 0.7, frame, 0.3, 0)
    return frame

def draw_star_labels_overlay(frame, star_labels):
    """
    在图片上叠加星体名称标注。
    star_labels: [(name, (x, y)), ...]
    """
    overlay = frame.copy()
    font = FONT_HERSHEY_SIMPLEX
    font_scale = 0.52
    color = (0, 255, 255)  # 黄色
    thickness = 1
    for name, (x, y) in star_labels:
        cv2.putText(overlay, name, (x, y), font, font_scale, color, thickness, cv2.LINE_AA)
    alpha = 0.85
    frame = cv2.addWeighted(overlay, alpha, frame, 1-alpha, 0)
    return frame

@app.route('/apply_settings', methods=['POST'])
def apply_settings():
    """
    应用用户设置的曝光值。
    """
    global settings
    data = request.get_json()
    for key in data:
        if key in settings:
            settings[key]['exposure'] = float(data[key]['exposure'])
            settings[key]['gain'] = float(data[key]['gain'])
    return jsonify({"message": "设置已应用", "settings": settings})

@app.route('/capture_image', methods=['GET'])
def capture_image():
    """
    捕获图像并保存到指定路径，然后返回图像文件。
    """
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        return "无法打开摄像头", 500

    current_time = datetime.datetime.now()
    exposure_time, gain = calculate_exposure_settings(current_time)

    configure_camera_settings(cap, exposure_time, gain)

    ret, frame = cap.read()
    if not ret:
        return "无法读取摄像头图像", 500

    # 计算日出日落等
    s = sun(city.observer, date=current_time.date(), tzinfo=current_time.tzinfo)
    # 叠加右上角信息栏
    frame = draw_info_overlay(frame, current_time, exposure_time, city, s)
    # 叠加左上角罗盘
    direction = 0
    frame = draw_compass_overlay(frame, direction)
    # 叠加左下角气象数据
    weather_data = {  # 初期全部N/A
        'Cloud Cover': 'N/A', 'Humidity': 'N/A', 'Dew Point': 'N/A', 'Pressure': 'N/A',
        'Wind Speed': 'N/A', 'Wind Gust': 'N/A', 'SkyTemperature': 'N/A',
        'Temperature': 'N/A', 'Sky Quality': 'N/A', 'Rain Rate': 'N/A'
    }
    frame = draw_weather_overlay(frame, weather_data)
    # 叠加右下角LOGO
    logo_path = "WechatIMG38126.jpg"  # 可替换为专用LOGO
    frame = draw_logo_overlay(frame, logo_path)
    # 叠加星体标注（模拟数据）
    # 模拟10个星体名称及随机坐标
    h, w = frame.shape[:2]
    mock_star_labels = [
        ("Polaris", (int(w*0.5), int(h*0.2))),
        ("Mars", (int(w*0.7), int(h*0.3))),
        ("Vega", (int(w*0.3), int(h*0.4))),
        ("Altair", (int(w*0.6), int(h*0.6))),
        ("Deneb", (int(w*0.4), int(h*0.7))),
        ("Jupiter", (int(w*0.8), int(h*0.5))),
        ("Saturn", (int(w*0.2), int(h*0.8))),
        ("Betelgeuse", (int(w*0.55), int(h*0.35))),
        ("Rigel", (int(w*0.65), int(h*0.75))),
        ("Sirius", (int(w*0.25), int(h*0.6)))
    ]
    frame = draw_star_labels_overlay(frame, mock_star_labels)

    # 保存图像
    filename = f"{OUTPUT_PATH}/{current_time.strftime('%Y%m%d_%H%M%S')}.jpg"
    cv2.imwrite(filename, frame)
    cap.release()
    
    return send_file(filename, mimetype='image/jpeg')

@app.route('/set_station_info', methods=['POST'])
def set_station_info():
    """
    设置观测站名和经纬度。
    POST JSON: {"name":..., "latitude":..., "longitude":...}
    """
    global station_info
    data = request.get_json()
    if 'name' in data:
        station_info['name'] = str(data['name'])
    if 'latitude' in data:
        station_info['latitude'] = float(data['latitude'])
    if 'longitude' in data:
        station_info['longitude'] = float(data['longitude'])
    return jsonify({"message": "观测站信息已更新", "station_info": station_info})

@app.route('/get_station_info', methods=['GET'])
def get_station_info():
    """
    查询当前观测站参数。
    """
    return jsonify(station_info)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)