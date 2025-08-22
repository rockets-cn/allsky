"""
天气API管理模块
支持多种天气数据源，如OpenWeatherMap、AccuWeather等
"""

import requests
import time
import json
from typing import Dict, Optional, Any
from datetime import datetime, timedelta
from abc import ABC, abstractmethod

from logger_manager import get_logger
from exceptions import WeatherAPIError, safe_execute, retry_on_failure

logger = get_logger('weather')


class WeatherProvider(ABC):
    """天气数据提供者抽象基类"""
    
    @abstractmethod
    def get_weather_data(self, lat: float, lon: float) -> Dict[str, Any]:
        """获取天气数据"""
        pass
    
    @abstractmethod
    def is_configured(self) -> bool:
        """检查是否已正确配置"""
        pass


class OpenWeatherMapProvider(WeatherProvider):
    """OpenWeatherMap API提供者"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.openweathermap.org/data/2.5"
    
    def is_configured(self) -> bool:
        return bool(self.api_key and self.api_key != "")
    
    @retry_on_failure(max_retries=3, delay=1.0)
    @safe_execute("获取OpenWeatherMap数据", reraise=True)
    def get_weather_data(self, lat: float, lon: float) -> Dict[str, Any]:
        """从OpenWeatherMap获取天气数据"""
        if not self.is_configured():
            raise WeatherAPIError("OpenWeatherMap API密钥未配置", "openweathermap")
        
        url = f"{self.base_url}/weather"
        params = {
            'lat': lat,
            'lon': lon,
            'appid': self.api_key,
            'units': 'metric',  # 使用摄氏度
            'lang': 'zh_cn'     # 中文描述
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            return self._parse_openweather_data(data)
            
        except requests.exceptions.RequestException as e:
            raise WeatherAPIError(f"OpenWeatherMap API请求失败: {str(e)}", "openweathermap")
        except (KeyError, ValueError) as e:
            raise WeatherAPIError(f"OpenWeatherMap数据解析失败: {str(e)}", "openweathermap")
    
    def _parse_openweather_data(self, data: Dict) -> Dict[str, Any]:
        """解析OpenWeatherMap返回的数据"""
        try:
            weather_info = {
                'Cloud Cover': f"{data.get('clouds', {}).get('all', 0)}%",
                'Humidity': f"{data.get('main', {}).get('humidity', 0)}%",
                'Pressure': f"{data.get('main', {}).get('pressure', 0)} hPa",
                'Temperature': f"{data.get('main', {}).get('temp', 0):.1f}°C",
                'Wind Speed': f"{data.get('wind', {}).get('speed', 0):.1f} m/s",
                'Wind Gust': f"{data.get('wind', {}).get('gust', 0):.1f} m/s",
                'Weather': data.get('weather', [{}])[0].get('description', 'N/A'),
                'Visibility': f"{data.get('visibility', 0) / 1000:.1f} km",
                'Rain Rate': '0 mm/h',  # OpenWeatherMap没有直接提供，需要计算
                'Dew Point': 'N/A',     # 需要通过温度和湿度计算
                'SkyTemperature': 'N/A', # 需要红外传感器数据
                'Sky Quality': 'N/A'     # 需要专业设备测量
            }
            
            # 计算露点温度（Magnus公式）
            temp = data.get('main', {}).get('temp', 0)
            humidity = data.get('main', {}).get('humidity', 0)
            if temp and humidity:
                dew_point = self._calculate_dew_point(temp, humidity)
                weather_info['Dew Point'] = f"{dew_point:.1f}°C"
            
            # 处理降雨信息
            rain_data = data.get('rain', {})
            if rain_data:
                rain_1h = rain_data.get('1h', 0)
                weather_info['Rain Rate'] = f"{rain_1h:.1f} mm/h"
            
            logger.info(f"天气数据获取成功: {weather_info['Temperature']}, {weather_info['Weather']}")
            return weather_info
            
        except Exception as e:
            raise WeatherAPIError(f"天气数据解析失败: {str(e)}", "openweathermap")
    
    def _calculate_dew_point(self, temperature: float, humidity: float) -> float:
        """使用Magnus公式计算露点温度"""
        try:
            a = 17.27
            b = 237.7
            alpha = ((a * temperature) / (b + temperature)) + (humidity / 100.0)
            dew_point = (b * alpha) / (a - alpha)
            return dew_point
        except:
            return 0.0


class MockWeatherProvider(WeatherProvider):
    """模拟天气数据提供者，用于测试和演示"""
    
    def is_configured(self) -> bool:
        return True
    
    def get_weather_data(self, lat: float, lon: float) -> Dict[str, Any]:
        """返回模拟的天气数据"""
        import random
        
        # 生成合理的模拟数据
        temp = random.uniform(-10, 35)
        humidity = random.uniform(30, 90)
        
        return {
            'Cloud Cover': f"{random.randint(0, 100)}%",
            'Humidity': f"{humidity:.0f}%",
            'Dew Point': f"{temp - random.uniform(5, 15):.1f}°C",
            'Pressure': f"{random.uniform(990, 1030):.1f} hPa",
            'Wind Speed': f"{random.uniform(0, 20):.1f} m/s",
            'Wind Gust': f"{random.uniform(0, 30):.1f} m/s",
            'SkyTemperature': f"{temp - random.uniform(10, 30):.1f}°C",
            'Temperature': f"{temp:.1f}°C",
            'Sky Quality': f"{random.uniform(15, 22):.1f} mag/arcsec²",
            'Rain Rate': f"{random.uniform(0, 5):.1f} mm/h",
            'Weather': random.choice(['晴朗', '多云', '阴天', '小雨', '晴转多云'])
        }


class WeatherManager:
    """天气管理器，负责管理天气数据的获取、缓存和更新"""
    
    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        self.providers = {}
        self.current_provider = None
        self.cache = {}
        self.cache_duration = 300  # 5分钟缓存
        self.last_update = None
        
        self._initialize_providers()
    
    def _initialize_providers(self):
        """初始化天气数据提供者"""
        try:
            if self.config_manager:
                weather_config = self.config_manager.get('weather', {})
                
                # OpenWeatherMap提供者
                owm_api_key = weather_config.get('openweathermap_api_key', '')
                if owm_api_key:
                    self.providers['openweathermap'] = OpenWeatherMapProvider(owm_api_key)
                    logger.info("OpenWeatherMap提供者已初始化")
                
                # 缓存时间配置
                self.cache_duration = weather_config.get('cache_duration', 300)
            
            # 总是添加模拟提供者作为备用
            self.providers['mock'] = MockWeatherProvider()
            
            # 选择默认提供者
            if self.config_manager:
                preferred_provider = self.config_manager.get('weather.preferred_provider', 'mock')
                if preferred_provider in self.providers and self.providers[preferred_provider].is_configured():
                    self.current_provider = self.providers[preferred_provider]
                    logger.info(f"使用天气提供者: {preferred_provider}")
                else:
                    self.current_provider = self.providers['mock']
                    logger.warning(f"首选提供者 {preferred_provider} 不可用，使用模拟数据")
            else:
                self.current_provider = self.providers['mock']
                logger.info("使用模拟天气数据提供者")
                
        except Exception as e:
            logger.error(f"天气提供者初始化失败: {e}")
            self.current_provider = MockWeatherProvider()
    
    def _is_cache_valid(self) -> bool:
        """检查缓存是否有效"""
        if not self.last_update or not self.cache:
            return False
        
        time_diff = time.time() - self.last_update
        return time_diff < self.cache_duration
    
    @safe_execute("获取天气数据")
    def get_weather_data(self, lat: float = None, lon: float = None) -> Dict[str, Any]:
        """获取天气数据，支持缓存"""
        try:
            # 如果没有提供坐标，从配置中获取
            if lat is None or lon is None:
                if self.config_manager:
                    station = self.config_manager.get('station', {})
                    lat = station.get('latitude', 31.2304)
                    lon = station.get('longitude', 121.4737)
                else:
                    lat, lon = 31.2304, 121.4737  # 默认上海坐标
            
            # 检查缓存
            cache_key = f"{lat:.4f},{lon:.4f}"
            if self._is_cache_valid() and cache_key in self.cache:
                logger.debug("返回缓存的天气数据")
                return self.cache[cache_key]
            
            # 获取新数据
            if not self.current_provider:
                raise WeatherAPIError("没有可用的天气数据提供者")
            
            weather_data = self.current_provider.get_weather_data(lat, lon)
            
            # 添加元数据
            weather_data['_metadata'] = {
                'provider': type(self.current_provider).__name__,
                'update_time': datetime.now().isoformat(),
                'coordinates': {'lat': lat, 'lon': lon}
            }
            
            # 更新缓存
            self.cache[cache_key] = weather_data
            self.last_update = time.time()
            
            logger.info(f"天气数据更新成功: {weather_data.get('Temperature', 'N/A')}")
            return weather_data
            
        except Exception as e:
            logger.error(f"获取天气数据失败: {e}")
            
            # 返回上次缓存的数据或默认数据
            if self.cache:
                logger.warning("返回过期的缓存数据")
                return list(self.cache.values())[-1]
            else:
                logger.warning("返回默认天气数据")
                return self._get_default_weather_data()
    
    def _get_default_weather_data(self) -> Dict[str, Any]:
        """获取默认天气数据"""
        return {
            'Cloud Cover': 'N/A',
            'Humidity': 'N/A',
            'Dew Point': 'N/A',
            'Pressure': 'N/A',
            'Wind Speed': 'N/A',
            'Wind Gust': 'N/A',
            'SkyTemperature': 'N/A',
            'Temperature': 'N/A',
            'Sky Quality': 'N/A',
            'Rain Rate': 'N/A',
            'Weather': 'N/A',
            '_metadata': {
                'provider': 'default',
                'update_time': datetime.now().isoformat(),
                'error': '无法获取天气数据'
            }
        }
    
    def force_update(self, lat: float = None, lon: float = None) -> Dict[str, Any]:
        """强制更新天气数据，忽略缓存"""
        self.cache.clear()
        self.last_update = None
        return self.get_weather_data(lat, lon)
    
    def switch_provider(self, provider_name: str) -> bool:
        """切换天气数据提供者"""
        if provider_name in self.providers and self.providers[provider_name].is_configured():
            self.current_provider = self.providers[provider_name]
            self.cache.clear()  # 清除缓存
            logger.info(f"切换到天气提供者: {provider_name}")
            return True
        else:
            logger.error(f"天气提供者 {provider_name} 不可用")
            return False
    
    def get_provider_status(self) -> Dict[str, Any]:
        """获取所有提供者的状态"""
        status = {}
        for name, provider in self.providers.items():
            status[name] = {
                'configured': provider.is_configured(),
                'active': provider == self.current_provider
            }
        return status
    
    def clear_cache(self):
        """清除天气数据缓存"""
        self.cache.clear()
        self.last_update = None
        logger.info("天气数据缓存已清除")


# 全局天气管理器实例
weather_manager = None

def init_weather_manager(config_manager=None):
    """初始化全局天气管理器"""
    global weather_manager
    weather_manager = WeatherManager(config_manager)
    return weather_manager

def get_weather_manager() -> WeatherManager:
    """获取全局天气管理器"""
    global weather_manager
    if weather_manager is None:
        weather_manager = WeatherManager()
    return weather_manager