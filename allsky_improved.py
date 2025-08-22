#!/usr/bin/env python3
"""
AllSky 星空相机系统 - 改进版
集成了配置管理、日志系统、错误处理等功能
"""

import cv2
import datetime
import numpy as np
import os
import time
from flask import Flask, request, jsonify, send_file
from astral import LocationInfo
from astral.sun import sun
from cv2 import FONT_HERSHEY_SIMPLEX
from threading import Lock
from functools import lru_cache

# 导入自定义模块
from config_manager import config_manager
from logger_manager import init_logger, get_logger, log_execution_time
from exceptions import (
    safe_execute, retry_on_failure, validate_input,
    CameraError, ImageProcessingError, ConfigurationError,
    global_error_handler, set_global_error_handler, ErrorHandler
)

# 初始化日志系统
logger_manager = init_logger(config_manager)
logger = get_logger('main')

# 初始化错误处理器
error_handler = ErrorHandler(logger)
set_global_error_handler(error_handler)

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
            # 只在设置有变化时才更新
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
            "China",  # 可以从配置中读取
            station['timezone'],
            station['latitude'],
            station['longitude']
        )
        logger.debug(f"位置信息更新: {station}")
    
    @lru_cache(maxsize=1440)  # 缓存一天的计算结果
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
            # 使用默认夜晚设置
            settings = config_manager.get('camera.default_settings.night')
            return settings['exposure'], settings['gain']
        
        # 根据时间段选择设置
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
        
        # 默认返回夜晚设置
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
        
        # 获取观测站信息
        station = config_manager.get('station')
        
        # 构建信息行
        lines = [
            (station['name'], (0, 140, 255), 1.1),
            (f"Sunrise: {sun_data['sunrise'].strftime('%Y-%m-%d %H:%M:%S')}", (0, 255, 255), 0.7),
            (f"Sunset : {sun_data['sunset'].strftime('%Y-%m-%d %H:%M:%S')}", (0, 255, 255), 0.7),
            (f"Time   : {current_time.strftime('%Y-%m-%d %H:%M:%S')}", (255, 255, 255), 0.7),
            (f"Lat: {station['latitude']:.4f}", (100, 255, 255), 0.7),
            (f"Long: {station['longitude']:.4f}", (100, 255, 255), 0.7),
            (f"Exp: {exposure_time:.0f} [s]", (100, 255, 255), 0.7)
        ]
        
        # 绘制
        x0, y0, dy = w - 370, 38, 34
        bg_w, bg_h = 360, len(lines) * dy + 18
        
        try:
            # 背景
            bg = overlay[y0-30:y0-30+bg_h, x0-18:x0-18+bg_w].copy()
            bg = cv2.rectangle(bg, (0, 0), (bg_w-1, bg_h-1), (0, 0, 0), -1)
            overlay[y0-30:y0-30+bg_h, x0-18:x0-18+bg_w] = cv2.addWeighted(
                overlay[y0-30:y0-30+bg_h, x0-18:x0-18+bg_w], 0.3, bg, 0.7, 0)
            
            # 文字
            for i, (text, color, scale) in enumerate(lines):
                y = y0 + i * dy
                cv2.putText(overlay, text, (x0, y), FONT_HERSHEY_SIMPLEX, scale, color, 2, cv2.LINE_AA)
            
            alpha = self.overlay_config.get('info_panel', {}).get('alpha', 0.7)
            frame = cv2.addWeighted(overlay, alpha, frame, 1-alpha, 0)
        except Exception as e:
            logger.warning(f"绘制信息面板时出错: {e}")
        
        return frame
    
    @safe_execute("绘制罗盘")
    def draw_compass_overlay(self, frame, direction=0):
        """绘制罗盘"""
        if not self.overlay_config.get('compass', {}).get('enabled', True):
            return frame
        
        overlay = frame.copy()
        compass_config = self.overlay_config.get('compass', {})
        
        center = (compass_config.get('size', 90), compass_config.get('size', 90))
        radius = compass_config.get('size', 90) - 22
        
        try:
            # 画圆环
            cv2.circle(overlay, center, radius, (255, 255, 255), 2)
            
            # 画方向标记
            directions = ['N', 'E', 'S', 'W']
            angles = [0, 90, 180, 270]
            
            for d, a in zip(directions, angles):
                angle_rad = np.deg2rad(a - direction)
                x = int(center[0] + (radius + 20) * np.sin(angle_rad) - 13)
                y = int(center[1] - (radius + 20) * np.cos(angle_rad) + 13)
                color = (0, 140, 255) if d == 'N' else (255, 255, 255)
                cv2.putText(overlay, d, (x, y), FONT_HERSHEY_SIMPLEX, 0.8, color, 2, cv2.LINE_AA)
            
            # 指北箭头
            arrow_angle = np.deg2rad(0 - direction)
            arrow_tip = (
                int(center[0] + (radius - 12) * np.sin(arrow_angle)),
                int(center[1] - (radius - 12) * np.cos(arrow_angle))
            )
            cv2.arrowedLine(overlay, center, arrow_tip, (0, 0, 255), 4, tipLength=0.32)
            
            alpha = compass_config.get('alpha', 0.6)
            frame = cv2.addWeighted(overlay, alpha, frame, 1-alpha, 0)
        except Exception as e:
            logger.warning(f"绘制罗盘时出错: {e}")
        
        return frame
    
    @safe_execute("处理图像叠加")
    def process_image_overlays(self, frame, current_time, exposure_time, sun_data, weather_data=None):
        """处理所有图像叠加"""
        try:
            # 信息面板
            frame = self.draw_info_overlay(frame, current_time, exposure_time, sun_data)
            
            # 罗盘
            frame = self.draw_compass_overlay(frame, direction=0)
            
            # 这里可以添加更多叠加功能...
            
            return frame
        except Exception as e:
            raise ImageProcessingError(f"图像叠加处理失败: {str(e)}", "overlay_processing")


# 全局实例
camera_manager = CameraManager()
astronomy_calculator = AstronomyCalculator()
image_processor = ImageProcessor()


@app.route('/capture_image', methods=['GET'])
@log_execution_time("图像捕获")
def capture_image():
    """捕获图像API端点"""
    try:
        with camera_lock:
            # 获取当前时间
            current_time = datetime.datetime.now()
            
            # 计算曝光设置
            exposure_time, gain = astronomy_calculator.calculate_exposure_settings(current_time)
            
            # 配置相机
            camera_manager.configure_settings(exposure_time, gain)
            
            # 捕获图像
            frame = camera_manager.capture_image()
            
            # 获取太阳数据
            sun_data = astronomy_calculator.get_sun_data(current_time.isoformat())
            
            # 处理图像叠加
            if sun_data:
                frame = image_processor.process_image_overlays(
                    frame, current_time, exposure_time, sun_data)
            
            # 保存图像
            filename = f"{output_path}/{current_time.strftime('%Y%m%d_%H%M%S')}.jpg"
            quality = config_manager.get('image.image_quality', 95)
            cv2.imwrite(filename, frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
            
            logger.info(f"图像已保存: {filename}")
            
            return send_file(filename, mimetype='image/jpeg')
    
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
        
        # 更新天文计算器的位置信息
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
        # 检查相机状态
        camera_status = "正常" if camera_manager.current_camera and camera_manager.current_camera.isOpened() else "离线"
        
        # 获取错误统计
        error_stats = error_handler.get_error_statistics()
        
        return jsonify({
            "status": "运行中",
            "camera_status": camera_status,
            "error_statistics": error_stats,
            "timestamp": datetime.datetime.now().isoformat()
        })
    
    except Exception as e:
        error_info = error_handler.handle_error(e, "健康检查")
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
        logger.info("应用程序清理完成")
    except Exception as e:
        logger.error(f"清理资源时出错: {e}")


if __name__ == "__main__":
    try:
        # 初始化相机
        camera_manager.initialize_camera()
        
        # 启动服务器
        server_config = config_manager.get('server')
        logger.info(f"启动服务器 - {server_config['host']}:{server_config['port']}")
        
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