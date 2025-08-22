"""
天文数据管理模块
提供真实的星体位置计算、行星位置、恒星数据等
"""

import ephem
import math
import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from functools import lru_cache

from logger_manager import get_logger
from exceptions import AstronomyCalculationError, safe_execute

logger = get_logger('astronomy')


class StarCatalog:
    """星表管理器，处理恒星数据"""
    
    def __init__(self):
        self.bright_stars = self._load_bright_stars()
        self.constellation_data = self._load_constellation_data()
    
    def _load_bright_stars(self) -> List[Dict]:
        """加载亮星数据（模拟Hipparcos星表的子集）"""
        # 这里包含一些最亮的恒星数据
        bright_stars = [
            # 名称, 赤经(度), 赤纬(度), 星等, 颜色
            {"name": "Sirius", "ra": 101.287, "dec": -16.716, "mag": -1.46, "color": "white"},
            {"name": "Canopus", "ra": 95.988, "dec": -52.696, "mag": -0.74, "color": "white"},
            {"name": "Arcturus", "ra": 213.915, "dec": 19.182, "mag": -0.05, "color": "orange"},
            {"name": "Vega", "ra": 279.234, "dec": 38.784, "mag": 0.03, "color": "white"},
            {"name": "Capella", "ra": 79.172, "dec": 45.998, "mag": 0.08, "color": "yellow"},
            {"name": "Rigel", "ra": 78.634, "dec": -8.202, "mag": 0.13, "color": "blue"},
            {"name": "Procyon", "ra": 114.825, "dec": 5.225, "mag": 0.34, "color": "white"},
            {"name": "Betelgeuse", "ra": 88.793, "dec": 7.407, "mag": 0.50, "color": "red"},
            {"name": "Achernar", "ra": 24.429, "dec": -57.237, "mag": 0.46, "color": "blue"},
            {"name": "Hadar", "ra": 210.956, "dec": -60.373, "mag": 0.61, "color": "blue"},
            {"name": "Altair", "ra": 297.696, "dec": 8.868, "mag": 0.77, "color": "white"},
            {"name": "Aldebaran", "ra": 68.980, "dec": 16.509, "mag": 0.85, "color": "orange"},
            {"name": "Antares", "ra": 247.352, "dec": -26.432, "mag": 1.09, "color": "red"},
            {"name": "Spica", "ra": 201.298, "dec": -11.161, "mag": 1.04, "color": "blue"},
            {"name": "Pollux", "ra": 116.329, "dec": 28.026, "mag": 1.14, "color": "orange"},
            {"name": "Fomalhaut", "ra": 344.413, "dec": -29.622, "mag": 1.16, "color": "white"},
            {"name": "Deneb", "ra": 310.358, "dec": 45.280, "mag": 1.25, "color": "white"},
            {"name": "Regulus", "ra": 152.093, "dec": 11.967, "mag": 1.35, "color": "blue"},
            {"name": "Adhara", "ra": 104.656, "dec": -28.972, "mag": 1.50, "color": "blue"},
            {"name": "Castor", "ra": 113.650, "dec": 31.888, "mag": 1.57, "color": "white"}
        ]
        
        logger.info(f"加载了 {len(bright_stars)} 颗亮星数据")
        return bright_stars
    
    def _load_constellation_data(self) -> Dict:
        """加载星座数据"""
        # 主要星座的代表星
        constellations = {
            "大熊座": ["Dubhe", "Merak", "Phecda", "Megrez", "Alioth", "Mizar", "Alkaid"],
            "小熊座": ["Polaris", "Kochab"],
            "仙后座": ["Schedar", "Caph", "Gamma Cas", "Ruchbah", "Segin"],
            "猎户座": ["Betelgeuse", "Rigel", "Bellatrix", "Mintaka", "Alnilam", "Alnitak"],
            "天鹅座": ["Deneb", "Sadr", "Gienah", "Delta Cyg", "Epsilon Cyg"],
            "天琴座": ["Vega", "Sheliak", "Sulafat"],
            "天鹰座": ["Altair", "Tarazed", "Alshain"],
            "金牛座": ["Aldebaran", "Elnath", "Zeta Tau"],
            "双子座": ["Castor", "Pollux"],
            "狮子座": ["Regulus", "Denebola", "Algieba"]
        }
        
        return constellations
    
    def get_visible_stars(self, observer_lat: float, observer_lon: float, 
                         max_magnitude: float = 4.0, min_altitude: float = 10.0) -> List[Dict]:
        """获取指定位置可见的恒星"""
        try:
            # 创建观测者
            observer = ephem.Observer()
            observer.lat = math.radians(observer_lat)
            observer.lon = math.radians(observer_lon)
            observer.date = ephem.now()
            
            visible_stars = []
            
            for star in self.bright_stars:
                if star['mag'] > max_magnitude:
                    continue
                
                # 创建恒星对象
                star_obj = ephem.FixedBody()
                star_obj._ra = math.radians(star['ra'])
                star_obj._dec = math.radians(star['dec'])
                
                # 计算恒星位置
                star_obj.compute(observer)
                
                # 检查是否在地平线以上
                altitude_deg = math.degrees(star_obj.alt)
                if altitude_deg > min_altitude:
                    visible_stars.append({
                        'name': star['name'],
                        'altitude': altitude_deg,
                        'azimuth': math.degrees(star_obj.az),
                        'magnitude': star['mag'],
                        'color': star['color'],
                        'ra': star['ra'],
                        'dec': star['dec']
                    })
            
            # 按亮度排序
            visible_stars.sort(key=lambda x: x['magnitude'])
            logger.info(f"找到 {len(visible_stars)} 颗可见恒星")
            return visible_stars
            
        except Exception as e:
            raise AstronomyCalculationError(f"计算可见恒星失败: {str(e)}", "visible_stars")


class PlanetCalculator:
    """行星位置计算器"""
    
    def __init__(self):
        self.planets = {
            'Mercury': ephem.Mercury(),
            'Venus': ephem.Venus(),
            'Mars': ephem.Mars(),
            'Jupiter': ephem.Jupiter(),
            'Saturn': ephem.Saturn(),
            'Uranus': ephem.Uranus(),
            'Neptune': ephem.Neptune(),
            'Moon': ephem.Moon(),
            'Sun': ephem.Sun()
        }
        
        self.chinese_names = {
            'Mercury': '水星',
            'Venus': '金星',
            'Mars': '火星',
            'Jupiter': '木星',
            'Saturn': '土星',
            'Uranus': '天王星',
            'Neptune': '海王星',
            'Moon': '月球',
            'Sun': '太阳'
        }
    
    @safe_execute("计算行星位置")
    def get_planet_positions(self, observer_lat: float, observer_lon: float, 
                           date_time: datetime = None) -> List[Dict]:
        """计算所有行星的位置"""
        try:
            # 创建观测者
            observer = ephem.Observer()
            observer.lat = math.radians(observer_lat)
            observer.lon = math.radians(observer_lon)
            
            if date_time:
                observer.date = date_time.strftime('%Y/%m/%d %H:%M:%S')
            else:
                observer.date = ephem.now()
            
            planet_positions = []
            
            for name, planet in self.planets.items():
                planet.compute(observer)
                
                altitude_deg = math.degrees(planet.alt)
                
                # 只包含在地平线以上的天体
                if altitude_deg > -5:  # 包含接近地平线的天体
                    chinese_name = self.chinese_names.get(name, name)
                    
                    position_info = {
                        'name': name,
                        'chinese_name': chinese_name,
                        'altitude': altitude_deg,
                        'azimuth': math.degrees(planet.az),
                        'magnitude': float(planet.mag) if hasattr(planet, 'mag') else None,
                        'distance_au': float(planet.earth_distance) if hasattr(planet, 'earth_distance') else None,
                        'phase': float(planet.phase) if hasattr(planet, 'phase') else None,
                        'constellation': ephem.constellation(planet)[1] if hasattr(ephem, 'constellation') else None,
                        'ra_hours': float(planet.ra) * 12 / math.pi,  # 转换为小时
                        'dec_degrees': math.degrees(planet.dec),
                        'rise_time': None,
                        'set_time': None,
                        'transit_time': None
                    }
                    
                    # 计算升起、中天、落下时间
                    try:
                        rise_time = observer.next_rising(planet)
                        set_time = observer.next_setting(planet)
                        transit_time = observer.next_transit(planet)
                        
                        position_info['rise_time'] = ephem.localtime(rise_time).strftime('%H:%M')
                        position_info['set_time'] = ephem.localtime(set_time).strftime('%H:%M')
                        position_info['transit_time'] = ephem.localtime(transit_time).strftime('%H:%M')
                    except ephem.CircumpolarError:
                        # 极昼或极夜情况
                        pass
                    except Exception:
                        # 其他计算错误
                        pass
                    
                    planet_positions.append(position_info)
            
            # 按高度角排序
            planet_positions.sort(key=lambda x: x['altitude'], reverse=True)
            logger.info(f"计算了 {len(planet_positions)} 个天体位置")
            return planet_positions
            
        except Exception as e:
            raise AstronomyCalculationError(f"计算行星位置失败: {str(e)}", "planet_positions")


class AstronomyManager:
    """天文数据管理器，整合星表和行星计算功能"""
    
    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        self.star_catalog = StarCatalog()
        self.planet_calculator = PlanetCalculator()
        self.cache = {}
        self.cache_duration = 600  # 10分钟缓存
        
        # 从配置中读取参数
        if config_manager:
            astronomy_config = config_manager.get('astronomy', {})
            self.use_real_data = astronomy_config.get('use_real_star_data', True)
            self.magnitude_limit = astronomy_config.get('magnitude_limit', 4.0)
            self.cache_duration = astronomy_config.get('cache_duration', 600)
        else:
            self.use_real_data = True
            self.magnitude_limit = 4.0
    
    @lru_cache(maxsize=100)
    def _get_cache_key(self, lat: float, lon: float, date_str: str) -> str:
        """生成缓存键"""
        return f"{lat:.4f},{lon:.4f},{date_str}"
    
    def _is_cache_valid(self, cache_key: str) -> bool:
        """检查缓存是否有效"""
        if cache_key not in self.cache:
            return False
        
        cache_time = self.cache[cache_key].get('timestamp', 0)
        return (datetime.now().timestamp() - cache_time) < self.cache_duration
    
    @safe_execute("获取天体数据")
    def get_celestial_objects(self, lat: float = None, lon: float = None, 
                            date_time: datetime = None, include_planets: bool = True,
                            include_stars: bool = True) -> Dict[str, Any]:
        """获取指定位置和时间的天体数据"""
        try:
            # 使用配置中的默认位置
            if lat is None or lon is None:
                if self.config_manager:
                    station = self.config_manager.get('station', {})
                    lat = lat or station.get('latitude', 31.2304)
                    lon = lon or station.get('longitude', 121.4737)
                else:
                    lat, lon = lat or 31.2304, lon or 121.4737
            
            if date_time is None:
                date_time = datetime.now()
            
            # 检查缓存
            date_str = date_time.strftime('%Y-%m-%d %H:%M')
            cache_key = self._get_cache_key(lat, lon, date_str)
            
            if self._is_cache_valid(cache_key):
                logger.debug("返回缓存的天体数据")
                return self.cache[cache_key]['data']
            
            celestial_data = {
                'timestamp': date_time.isoformat(),
                'observer': {'latitude': lat, 'longitude': lon},
                'planets': [],
                'stars': [],
                'metadata': {
                    'use_real_data': self.use_real_data,
                    'magnitude_limit': self.magnitude_limit,
                    'calculation_time': datetime.now().isoformat()
                }
            }
            
            # 获取行星数据
            if include_planets:
                try:
                    planets = self.planet_calculator.get_planet_positions(lat, lon, date_time)
                    celestial_data['planets'] = planets
                    logger.info(f"获取了 {len(planets)} 个行星数据")
                except Exception as e:
                    logger.error(f"获取行星数据失败: {e}")
                    celestial_data['planets'] = []
            
            # 获取恒星数据
            if include_stars and self.use_real_data:
                try:
                    stars = self.star_catalog.get_visible_stars(lat, lon, self.magnitude_limit)
                    celestial_data['stars'] = stars
                    logger.info(f"获取了 {len(stars)} 颗恒星数据")
                except Exception as e:
                    logger.error(f"获取恒星数据失败: {e}")
                    celestial_data['stars'] = []
            
            # 更新缓存
            self.cache[cache_key] = {
                'data': celestial_data,
                'timestamp': datetime.now().timestamp()
            }
            
            return celestial_data
            
        except Exception as e:
            raise AstronomyCalculationError(f"获取天体数据失败: {str(e)}", "celestial_objects")
    
    def get_bright_stars_for_image(self, lat: float = None, lon: float = None,
                                  image_width: int = 1920, image_height: int = 1080,
                                  max_stars: int = 20) -> List[Tuple[str, Tuple[int, int]]]:
        """获取用于图像标注的亮星位置（像素坐标）"""
        try:
            celestial_data = self.get_celestial_objects(lat, lon, include_planets=False, include_stars=True)
            stars = celestial_data.get('stars', [])
            
            if not stars:
                # 如果没有真实数据，返回模拟位置
                return self._generate_mock_star_positions(image_width, image_height, max_stars)
            
            star_positions = []
            
            for star in stars[:max_stars]:
                # 简化的投影计算 - 实际项目中应使用更精确的全天空投影
                # 这里使用简单的方位角-高度角到直角坐标的转换
                azimuth = star['azimuth']
                altitude = star['altitude']
                
                # 将方位角和高度角转换为图像坐标
                # 假设图像中心为天顶，边缘为地平线
                radius = (90 - altitude) / 90 * min(image_width, image_height) / 2
                
                # 计算像素坐标
                x = int(image_width / 2 + radius * math.sin(math.radians(azimuth)))
                y = int(image_height / 2 - radius * math.cos(math.radians(azimuth)))
                
                # 确保坐标在图像范围内
                if 0 <= x < image_width and 0 <= y < image_height:
                    star_positions.append((star['name'], (x, y)))
            
            logger.info(f"生成了 {len(star_positions)} 个星体标注位置")
            return star_positions
            
        except Exception as e:
            logger.error(f"生成星体标注位置失败: {e}")
            return self._generate_mock_star_positions(image_width, image_height, max_stars)
    
    def _generate_mock_star_positions(self, width: int, height: int, count: int) -> List[Tuple[str, Tuple[int, int]]]:
        """生成模拟的星体位置"""
        import random
        
        mock_stars = ["Polaris", "Vega", "Altair", "Deneb", "Mars", "Jupiter", "Saturn", 
                     "Betelgeuse", "Rigel", "Sirius", "Canopus", "Arcturus", "Spica",
                     "Aldebaran", "Antares", "Procyon", "Capella", "Regulus", "Fomalhaut", "Castor"]
        
        positions = []
        for i in range(min(count, len(mock_stars))):
            x = random.randint(50, width - 50)
            y = random.randint(50, height - 50)
            positions.append((mock_stars[i], (x, y)))
        
        return positions
    
    def get_astronomy_summary(self, lat: float = None, lon: float = None) -> Dict[str, Any]:
        """获取天文数据摘要"""
        try:
            celestial_data = self.get_celestial_objects(lat, lon)
            
            # 统计信息
            visible_planets = [p for p in celestial_data['planets'] if p['altitude'] > 0]
            bright_stars = [s for s in celestial_data['stars'] if s['magnitude'] < 2.0]
            
            summary = {
                'total_planets': len(celestial_data['planets']),
                'visible_planets': len(visible_planets),
                'total_stars': len(celestial_data['stars']),
                'bright_stars': len(bright_stars),
                'brightest_planet': None,
                'brightest_star': None,
                'moon_phase': None,
                'observation_quality': 'good'  # 可以根据天气等因素调整
            }
            
            # 找到最亮的行星
            if visible_planets:
                brightest_planet = min(visible_planets, key=lambda x: x.get('magnitude', 10))
                summary['brightest_planet'] = {
                    'name': brightest_planet['chinese_name'],
                    'magnitude': brightest_planet.get('magnitude'),
                    'altitude': brightest_planet['altitude']
                }
            
            # 找到最亮的恒星
            if bright_stars:
                brightest_star = min(bright_stars, key=lambda x: x['magnitude'])
                summary['brightest_star'] = {
                    'name': brightest_star['name'],
                    'magnitude': brightest_star['magnitude'],
                    'altitude': brightest_star['altitude']
                }
            
            # 月相信息
            moon_data = next((p for p in celestial_data['planets'] if p['name'] == 'Moon'), None)
            if moon_data and moon_data.get('phase') is not None:
                summary['moon_phase'] = moon_data['phase']
            
            return summary
            
        except Exception as e:
            logger.error(f"生成天文摘要失败: {e}")
            return {'error': str(e)}
    
    def clear_cache(self):
        """清除缓存"""
        self.cache.clear()
        logger.info("天文数据缓存已清除")


# 全局天文管理器实例
astronomy_manager = None

def init_astronomy_manager(config_manager=None):
    """初始化全局天文管理器"""
    global astronomy_manager
    astronomy_manager = AstronomyManager(config_manager)
    return astronomy_manager

def get_astronomy_manager() -> AstronomyManager:
    """获取全局天文管理器"""
    global astronomy_manager
    if astronomy_manager is None:
        astronomy_manager = AstronomyManager()
    return astronomy_manager