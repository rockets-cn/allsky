import json
import os
import logging
import time
from typing import Dict, Any, Optional
import shutil


class ConfigManager:
    """配置管理器，负责加载、验证和更新配置"""
    
    def __init__(self, config_path: str = "config.json"):
        self.config_path = config_path
        self.config: Dict[str, Any] = {}
        self.default_config = self._get_default_config()
        self.load_config()
    
    def _get_default_config(self) -> Dict[str, Any]:
        """获取默认配置"""
        return {
            "camera": {
                "index": 0,
                "default_settings": {
                    "day": {"exposure": -5, "gain": 10},
                    "civil": {"exposure": -2, "gain": 15},
                    "nautical": {"exposure": 0, "gain": 20},
                    "astronomical": {"exposure": 3, "gain": 30},
                    "night": {"exposure": 5, "gain": 40}
                }
            },
            "server": {
                "host": "0.0.0.0",
                "port": 5000,
                "debug": False
            },
            "paths": {
                "output_path": "./all_sky_images",
                "logo_path": "WechatIMG38126.jpg",
                "config_backup_path": "./config_backup"
            },
            "station": {
                "name": "Jiamuerdeng Tianwentai",
                "latitude": 31.2304,
                "longitude": 121.4737,
                "timezone": "Asia/Shanghai"
            },
            "weather": {
                "api_enabled": False,
                "api_key": "",
                "api_url": "",
                "update_interval": 300
            },
            "astronomy": {
                "use_real_star_data": False,
                "star_catalog_path": "",
                "magnitude_limit": 4.0
            },
            "image": {
                "auto_capture": False,
                "capture_interval": 60,
                "max_stored_images": 100,
                "image_format": "jpg",
                "image_quality": 95
            },
            "overlay": {
                "compass": {
                    "enabled": True,
                    "position": "top_left",
                    "size": 90,
                    "alpha": 0.6
                },
                "info_panel": {
                    "enabled": True,
                    "position": "top_right",
                    "alpha": 0.7
                },
                "weather_panel": {
                    "enabled": True,
                    "position": "bottom_left",
                    "alpha": 0.7
                },
                "logo": {
                    "enabled": True,
                    "position": "bottom_right",
                    "alpha": 0.85,
                    "scale": 0.14
                },
                "star_labels": {
                    "enabled": True,
                    "alpha": 0.85,
                    "font_scale": 0.52
                }
            },
            "logging": {
                "level": "INFO",
                "file_path": "./logs/allsky.log",
                "max_file_size": "10MB",
                "backup_count": 5
            }
        }
    
    def load_config(self) -> None:
        """加载配置文件"""
        try:
            if os.path.exists(self.config_path):
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    self.config = json.load(f)
                self._merge_with_defaults()
                logging.info(f"配置文件已加载: {self.config_path}")
            else:
                logging.warning(f"配置文件不存在，使用默认配置: {self.config_path}")
                self.config = self.default_config.copy()
                self.save_config()
        except Exception as e:
            logging.error(f"加载配置文件失败: {e}")
            self.config = self.default_config.copy()
    
    def _merge_with_defaults(self) -> None:
        """将加载的配置与默认配置合并，确保所有必需的键都存在"""
        def merge_dict(base: dict, overlay: dict) -> dict:
            for key, value in base.items():
                if key not in overlay:
                    overlay[key] = value
                elif isinstance(value, dict) and isinstance(overlay[key], dict):
                    merge_dict(value, overlay[key])
            return overlay
        
        self.config = merge_dict(self.default_config, self.config)
    
    def save_config(self) -> None:
        """保存配置到文件"""
        try:
            # 创建备份
            if os.path.exists(self.config_path):
                backup_dir = self.get('paths.config_backup_path', './config_backup')
                os.makedirs(backup_dir, exist_ok=True)
                shutil.copy2(self.config_path, 
                           os.path.join(backup_dir, f"config_backup_{int(time.time())}.json"))
            
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=2, ensure_ascii=False)
            logging.info(f"配置已保存: {self.config_path}")
        except Exception as e:
            logging.error(f"保存配置文件失败: {e}")
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        使用点号分隔的路径获取配置值
        例如: get('camera.index') 或 get('station.latitude')
        """
        keys = key_path.split('.')
        value = self.config
        
        try:
            for key in keys:
                value = value[key]
            return value
        except (KeyError, TypeError):
            return default
    
    def set(self, key_path: str, value: Any) -> None:
        """
        使用点号分隔的路径设置配置值
        例如: set('camera.index', 1)
        """
        keys = key_path.split('.')
        config_ref = self.config
        
        for key in keys[:-1]:
            if key not in config_ref:
                config_ref[key] = {}
            config_ref = config_ref[key]
        
        config_ref[keys[-1]] = value
    
    def update_camera_settings(self, settings: Dict[str, Any]) -> None:
        """更新相机设置"""
        current_settings = self.get('camera.default_settings', {})
        current_settings.update(settings)
        self.set('camera.default_settings', current_settings)
        self.save_config()
    
    def update_station_info(self, station_info: Dict[str, Any]) -> None:
        """更新观测站信息"""
        current_station = self.get('station', {})
        current_station.update(station_info)
        self.set('station', current_station)
        self.save_config()
    
    def validate_config(self) -> bool:
        """验证配置的有效性"""
        try:
            # 验证必需的配置项
            required_keys = [
                'camera.index',
                'station.latitude',
                'station.longitude',
                'paths.output_path'
            ]
            
            for key in required_keys:
                if self.get(key) is None:
                    logging.error(f"缺少必需的配置项: {key}")
                    return False
            
            # 验证数值范围
            lat = self.get('station.latitude')
            lng = self.get('station.longitude')
            
            if not (-90 <= lat <= 90):
                logging.error(f"纬度值无效: {lat}")
                return False
            
            if not (-180 <= lng <= 180):
                logging.error(f"经度值无效: {lng}")
                return False
            
            return True
        except Exception as e:
            logging.error(f"配置验证失败: {e}")
            return False


# 全局配置管理器实例
config_manager = ConfigManager()