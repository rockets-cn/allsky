#!/usr/bin/env python3
"""
AllSky 星空相机系统 - 完整版
集成所有功能模块：配置管理、日志系统、错误处理、天气API、天文数据、图像管理等
"""

import cv2
import datetime
import numpy as np
import os
import time
from flask import Flask, request, jsonify, send_file, render_template_string
from astral import LocationInfo
from astral.sun import sun
from cv2 import FONT_HERSHEY_SIMPLEX
from threading import Lock
from functools import lru_cache
import atexit

# 导入自定义模块
from config_manager import config_manager
from logger_manager import init_logger, get_logger, log_execution_time
from exceptions import (
    safe_execute, retry_on_failure,
    CameraError, ImageProcessingError, ConfigurationError,
    global_error_handler, set_global_error_handler, ErrorHandler
)
from weather_manager import init_weather_manager, get_weather_manager
from astronomy_manager import init_astronomy_manager, get_astronomy_manager
from image_manager import init_image_manager, get_image_manager

# 初始化所有管理器
logger_manager = init_logger(config_manager)
logger = get_logger('main')

error_handler = ErrorHandler(logger)
set_global_error_handler(error_handler)

weather_manager = init_weather_manager(config_manager)
astronomy_manager = init_astronomy_manager(config_manager)
image_manager = init_image_manager(config_manager)

# 初始化 Flask 应用程序
app = Flask(__name__)

# 全局变量和锁
camera_lock = Lock()
sun_data_cache = {}
cache_lock = Lock()

# 验证配置
if not config_manager.validate_config():
    logger.error("配置验证失败，程序可能无法正常运行")

# 创建必要的目录
output_path = config_manager.get('paths.output_path')
if not os.path.exists(output_path):
    os.makedirs(output_path, exist_ok=True)
    logger.info(f"创建输出目录: {output_path}")


class CameraManager:
    """相机管理器，负责相机的初始化、配置和图像捕获"""
    
    def __init__(self):
        self.camera_index = config_manager.get('camera.index', 0)
        self.current_camera = None
        self.last_settings = {}
    
    @safe_execute("初始化相机", reraise=True)
    def initialize_camera(self):
        """初始化相机"""
        try:
            self.current_camera = cv2.VideoCapture(self.camera_index)
            if not self.current_camera.isOpened():
                raise CameraError(f"无法打开相机 {self.camera_index}", self.camera_index)
            
            logger.info(f"相机 {self.camera_index} 初始化成功")
            return True
        except Exception as e:
            raise CameraError(f"相机初始化失败: {str(e)}", self.camera_index)
    
    @safe_execute("配置相机设置")
    def configure_settings(self, exposure_time: float, gain: float):
        """配置相机设置"""
        if not self.current_camera or not self.current_camera.isOpened():
            raise CameraError("相机未初始化或已断开连接", self.camera_index)
        
        try:
            new_settings = {'exposure': exposure_time, 'gain': gain}
            if new_settings != self.last_settings:
                self.current_camera.set(cv2.CAP_PROP_EXPOSURE, float(exposure_time))
                self.current_camera.set(cv2.CAP_PROP_GAIN, float(gain))
                self.last_settings = new_settings
                logger.debug(f"相机设置更新: {new_settings}")
        except Exception as e:
            raise CameraError(f"配置相机设置失败: {str(e)}", self.camera_index)
    
    @retry_on_failure(max_retries=3, delay=0.5)
    @safe_execute("捕获图像", reraise=True)
    def capture_image(self):
        """捕获图像"""
        if not self.current_camera or not self.current_camera.isOpened():
            self.initialize_camera()
        
        ret, frame = self.current_camera.read()
        if not ret or frame is None:
            raise CameraError("无法从相机读取图像", self.camera_index)
        
        return frame
    
    def release(self):
        """释放相机资源"""
        if self.current_camera:
            self.current_camera.release()
            self.current_camera = None
            logger.info("相机资源已释放")


class AstronomyCalculator:
    """天文计算器，负责太阳位置、曙暮光等计算"""
    
    def __init__(self):
        self.update_location_info()
    
    def update_location_info(self):
        """更新位置信息"""
        station = config_manager.get('station')
        self.city = LocationInfo(
            station['name'],
            "China",
            station['timezone'],
            station['latitude'],
            station['longitude']
        )
        logger.debug(f"位置信息更新: {station}")
    
    @lru_cache(maxsize=1440)
    def get_sun_data(self, date_str: str):
        """获取太阳相关数据，使用缓存提高性能"""
        try:
            date = datetime.datetime.fromisoformat(date_str).date()
            s = sun(self.city.observer, date=date)
            return s
        except Exception as e:
            logger.error(f"计算太阳数据失败: {e}")
            return None
    
    @safe_execute("计算曝光设置")
    def calculate_exposure_settings(self, current_time: datetime.datetime):
        """根据当前时间计算曝光设置"""
        date_str = current_time.isoformat()
        s = self.get_sun_data(date_str)
        
        if not s:
            settings = config_manager.get('camera.default_settings.night')
            return settings['exposure'], settings['gain']
        
        time_periods = [
            ('night', lambda: current_time < s['astronomical_dawn'] or current_time >= s['astronomical_dusk']),
            ('astronomical', lambda: s['astronomical_dawn'] <= current_time < s['nautical_dawn'] or s['nautical_dusk'] <= current_time < s['astronomical_dusk']),
            ('nautical', lambda: s['nautical_dawn'] <= current_time < s['civil_dawn'] or s['civil_dusk'] <= current_time < s['nautical_dusk']),
            ('civil', lambda: s['civil_dawn'] <= current_time < s['sunrise'] or s['sunset'] <= current_time < s['civil_dusk']),
            ('day', lambda: s['sunrise'] <= current_time < s['sunset'])
        ]
        
        for period, condition in time_periods:
            try:
                if condition():
                    settings = config_manager.get(f'camera.default_settings.{period}')
                    return settings['exposure'], settings['gain']
            except Exception as e:
                logger.warning(f"检查时间段 {period} 时出错: {e}")
                continue
        
        settings = config_manager.get('camera.default_settings.night')
        return settings['exposure'], settings['gain']


class ImageProcessor:
    """图像处理器，负责在图像上添加各种信息叠加"""
    
    def __init__(self):
        self.overlay_config = config_manager.get('overlay', {})
    
    @safe_execute("绘制信息面板")
    def draw_info_overlay(self, frame, current_time, exposure_time, sun_data):
        """在图片上叠加观测站信息"""
        if not self.overlay_config.get('info_panel', {}).get('enabled', True):
            return frame
        
        overlay = frame.copy()
        h, w = frame.shape[:2]
        
        station = config_manager.get('station')
        
        lines = [
            (station['name'], (0, 140, 255), 1.1),
            (f"Sunrise: {sun_data['sunrise'].strftime('%Y-%m-%d %H:%M:%S')}", (0, 255, 255), 0.7),
            (f"Sunset : {sun_data['sunset'].strftime('%Y-%m-%d %H:%M:%S')}", (0, 255, 255), 0.7),
            (f"Time   : {current_time.strftime('%Y-%m-%d %H:%M:%S')}", (255, 255, 255), 0.7),
            (f"Lat: {station['latitude']:.4f}", (100, 255, 255), 0.7),
            (f"Long: {station['longitude']:.4f}", (100, 255, 255), 0.7),
            (f"Exp: {exposure_time:.0f} [s]", (100, 255, 255), 0.7)
        ]
        
        x0, y0, dy = w - 370, 38, 34
        bg_w, bg_h = 360, len(lines) * dy + 18
        
        try:
            bg = overlay[y0-30:y0-30+bg_h, x0-18:x0-18+bg_w].copy()
            bg = cv2.rectangle(bg, (0, 0), (bg_w-1, bg_h-1), (0, 0, 0), -1)
            overlay[y0-30:y0-30+bg_h, x0-18:x0-18+bg_w] = cv2.addWeighted(
                overlay[y0-30:y0-30+bg_h, x0-18:x0-18+bg_w], 0.3, bg, 0.7, 0)
            
            for i, (text, color, scale) in enumerate(lines):
                y = y0 + i * dy
                cv2.putText(overlay, text, (x0, y), FONT_HERSHEY_SIMPLEX, scale, color, 2, cv2.LINE_AA)
            
            alpha = self.overlay_config.get('info_panel', {}).get('alpha', 0.7)
            frame = cv2.addWeighted(overlay, alpha, frame, 1-alpha, 0)
        except Exception as e:
            logger.warning(f"绘制信息面板时出错: {e}")
        
        return frame
    
    @safe_execute("绘制天气信息")
    def draw_weather_overlay(self, frame, weather_data):
        """绘制天气信息叠加"""
        if not self.overlay_config.get('weather_panel', {}).get('enabled', True):
            return frame
        
        overlay = frame.copy()
        h, w = frame.shape[:2]
        
        items = [
            'Cloud Cover', 'Humidity', 'Dew Point', 'Pressure', 'Wind Speed',
            'Wind Gust', 'SkyTemperature', 'Temperature', 'Sky Quality', 'Rain Rate'
        ]
        
        x0, y0, dy = 28, h - 260, 26
        
        try:
            bg_w, bg_h = 260, len(items) * dy + 18
            bg = overlay[y0-22:y0-22+bg_h, x0-12:x0-12+bg_w].copy()
            bg = cv2.rectangle(bg, (0, 0), (bg_w-1, bg_h-1), (0, 0, 0), -1)
            overlay[y0-22:y0-22+bg_h, x0-12:x0-12+bg_w] = cv2.addWeighted(
                overlay[y0-22:y0-22+bg_h, x0-12:x0-12+bg_w], 0.3, bg, 0.7, 0)
            
            for i, key in enumerate(items):
                value = weather_data.get(key, 'N/A')
                text = f"{key}: {value}"
                y = y0 + i * dy
                cv2.putText(overlay, text, (x0, y), FONT_HERSHEY_SIMPLEX, 0.62, (255, 255, 200), 1, cv2.LINE_AA)
            
            alpha = self.overlay_config.get('weather_panel', {}).get('alpha', 0.7)
            frame = cv2.addWeighted(overlay, alpha, frame, 1-alpha, 0)
        except Exception as e:
            logger.warning(f"绘制天气信息时出错: {e}")
        
        return frame
    
    @safe_execute("绘制星体标注")
    def draw_star_labels(self, frame, star_positions):
        """绘制星体标注"""
        if not self.overlay_config.get('star_labels', {}).get('enabled', True):
            return frame
        
        overlay = frame.copy()
        
        try:
            for name, (x, y) in star_positions:
                cv2.putText(overlay, name, (x, y), FONT_HERSHEY_SIMPLEX, 0.52, (0, 255, 255), 1, cv2.LINE_AA)
            
            alpha = self.overlay_config.get('star_labels', {}).get('alpha', 0.85)
            frame = cv2.addWeighted(overlay, alpha, frame, 1-alpha, 0)
        except Exception as e:
            logger.warning(f"绘制星体标注时出错: {e}")
        
        return frame


# 全局实例
camera_manager = CameraManager()
astronomy_calculator = AstronomyCalculator()
image_processor = ImageProcessor()

# 设置图像管理器的拍摄回调
def capture_callback():
    """定时拍摄回调函数"""
    try:
        with camera_lock:
            current_time = datetime.datetime.now()
            exposure_time, gain = astronomy_calculator.calculate_exposure_settings(current_time)
            camera_manager.configure_settings(exposure_time, gain)
            frame = camera_manager.capture_image()
            
            # 获取附加数据
            sun_data = astronomy_calculator.get_sun_data(current_time.isoformat())
            weather_data = weather_manager.get_weather_data()
            astronomy_data = astronomy_manager.get_astronomy_summary()
            
            # 处理图像叠加
            if sun_data:
                frame = image_processor.draw_info_overlay(frame, current_time, exposure_time, sun_data)
            
            frame = image_processor.draw_weather_overlay(frame, weather_data)
            
            # 获取星体位置并绘制
            star_positions = astronomy_manager.get_bright_stars_for_image(
                image_width=frame.shape[1], 
                image_height=frame.shape[0]
            )
            frame = image_processor.draw_star_labels(frame, star_positions)
            
            # 保存图像
            image_manager.save_image(
                frame, 
                current_time,
                {'exposure': exposure_time, 'gain': gain},
                weather_data,
                astronomy_data
            )
            
    except Exception as e:
        logger.error(f"定时拍摄失败: {e}")

image_manager.set_capture_callback(capture_callback)


# Flask 路由定义
@app.route('/')
def index():
    """主页"""
    with open('dashboard.html', 'r', encoding='utf-8') as f:
        return f.read()

@app.route('/capture_image', methods=['GET'])
@log_execution_time("图像捕获")
def capture_image():
    """捕获图像API端点"""
    try:
        capture_callback()
        
        # 获取最新图像
        latest_images = image_manager.get_latest_images(1)
        if latest_images:
            latest_image_path = latest_images[0]['image_path']
            return send_file(latest_image_path, mimetype='image/jpeg')
        else:
            return jsonify({"error": "无法获取图像"}), 500
    
    except Exception as e:
        error_info = error_handler.handle_error(e, "图像捕获")
        return jsonify(error_info), 500


@app.route('/apply_settings', methods=['POST'])
@log_execution_time("应用设置")
def apply_settings():
    """应用用户设置的曝光值"""
    try:
        data = request.get_json()
        if not data:
            raise ConfigurationError("未提供设置数据")
        
        config_manager.update_camera_settings(data)
        logger.info(f"相机设置已更新: {data}")
        
        return jsonify({
            "success": True,
            "message": "设置已应用",
            "settings": config_manager.get('camera.default_settings')
        })
    
    except Exception as e:
        error_info = error_handler.handle_error(e, "应用设置")
        return jsonify(error_info), 400


@app.route('/set_station_info', methods=['POST'])
@log_execution_time("设置观测站信息")
def set_station_info():
    """设置观测站信息"""
    try:
        data = request.get_json()
        if not data:
            raise ConfigurationError("未提供观测站数据")
        
        config_manager.update_station_info(data)
        astronomy_calculator.update_location_info()
        
        logger.info(f"观测站信息已更新: {data}")
        
        return jsonify({
            "success": True,
            "message": "观测站信息已更新",
            "station_info": config_manager.get('station')
        })
    
    except Exception as e:
        error_info = error_handler.handle_error(e, "设置观测站信息")
        return jsonify(error_info), 400


@app.route('/get_station_info', methods=['GET'])
def get_station_info():
    """获取观测站信息"""
    return jsonify(config_manager.get('station'))


@app.route('/health', methods=['GET'])
def health_check():
    """健康检查端点"""
    try:
        camera_status = "正常" if camera_manager.current_camera and camera_manager.current_camera.isOpened() else "离线"
        error_stats = error_handler.get_error_statistics()
        
        return jsonify({
            "status": "运行中",
            "camera_status": camera_status,
            "error_statistics": error_stats,
            "timestamp": datetime.datetime.now().isoformat(),
            "modules": {
                "weather": weather_manager is not None,
                "astronomy": astronomy_manager is not None,
                "image_manager": image_manager is not None
            }
        })
    
    except Exception as e:
        error_info = error_handler.handle_error(e, "健康检查")
        return jsonify(error_info), 500


@app.route('/api/statistics', methods=['GET'])
def get_statistics():
    """获取系统统计信息"""
    try:
        stats = {
            "weather": weather_manager.get_weather_data(),
            "astronomy": astronomy_manager.get_astronomy_summary(),
            "images": image_manager.get_statistics(),
            "timestamp": datetime.datetime.now().isoformat()
        }
        return jsonify(stats)
    
    except Exception as e:
        error_info = error_handler.handle_error(e, "获取统计信息")
        return jsonify(error_info), 500


@app.route('/api/images', methods=['GET'])
def get_images():
    """获取图像列表"""
    try:
        limit = int(request.args.get('limit', 20))
        images = image_manager.get_latest_images(limit)
        return jsonify(images)
    
    except Exception as e:
        error_info = error_handler.handle_error(e, "获取图像列表")
        return jsonify(error_info), 500


@app.route('/api/scheduled_capture/start', methods=['POST'])
def start_scheduled_capture():
    """启动定时拍摄"""
    try:
        success = image_manager.start_scheduled_capture()
        if success:
            return jsonify({"success": True, "message": "定时拍摄已启动"})
        else:
            return jsonify({"success": False, "message": "启动定时拍摄失败"}), 400
    
    except Exception as e:
        error_info = error_handler.handle_error(e, "启动定时拍摄")
        return jsonify(error_info), 500


@app.route('/api/scheduled_capture/stop', methods=['POST'])
def stop_scheduled_capture():
    """停止定时拍摄"""
    try:
        image_manager.stop_scheduled_capture()
        return jsonify({"success": True, "message": "定时拍摄已停止"})
    
    except Exception as e:
        error_info = error_handler.handle_error(e, "停止定时拍摄")
        return jsonify(error_info), 500


@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": True, "message": "端点不存在"}), 404


@app.errorhandler(500)
def internal_error(error):
    error_info = error_handler.handle_error(error, "服务器内部错误")
    return jsonify(error_info), 500


def cleanup():
    """清理资源"""
    try:
        camera_manager.release()
        image_manager.cleanup()
        logger.info("应用程序清理完成")
    except Exception as e:
        logger.error(f"清理资源时出错: {e}")


def main():
    """主函数"""
    try:
        # 注册清理函数
        atexit.register(cleanup)
        
        # 初始化相机
        camera_manager.initialize_camera()
        
        # 启动服务器
        server_config = config_manager.get('server')
        logger.info(f"启动完整版AllSky服务器 - {server_config['host']}:{server_config['port']}")
        logger.info("可用功能:")
        logger.info("- 实时图像捕获和处理")
        logger.info("- 天气数据集成")
        logger.info("- 真实天文数据计算")
        logger.info("- 图像历史管理和定时拍摄")
        logger.info("- 现代化Web控制面板")
        
        app.run(
            host=server_config['host'],
            port=server_config['port'],
            debug=server_config.get('debug', False)
        )
    
    except KeyboardInterrupt:
        logger.info("接收到中断信号，正在关闭...")
    except Exception as e:
        logger.error(f"启动失败: {e}")
    finally:
        cleanup()


if __name__ == "__main__":
    main()