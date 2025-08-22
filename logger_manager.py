import logging
import os
import sys
import functools
from logging.handlers import RotatingFileHandler
from datetime import datetime
from typing import Optional


class LoggerManager:
    """日志管理器，提供统一的日志配置和管理功能"""
    
    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        self.logger = None
        self._setup_logger()
    
    def _setup_logger(self) -> None:
        """设置日志配置"""
        # 获取配置
        if self.config_manager:
            log_level = self.config_manager.get('logging.level', 'INFO')
            log_file = self.config_manager.get('logging.file_path', './logs/allsky.log')
            max_file_size = self.config_manager.get('logging.max_file_size', '10MB')
            backup_count = self.config_manager.get('logging.backup_count', 5)
        else:
            log_level = 'INFO'
            log_file = './logs/allsky.log'
            max_file_size = '10MB'
            backup_count = 5
        
        # 创建日志目录
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        
        # 设置日志级别
        level = getattr(logging, log_level.upper(), logging.INFO)
        
        # 创建logger
        self.logger = logging.getLogger('allsky')
        self.logger.setLevel(level)
        
        # 清除已有的handlers
        for handler in self.logger.handlers[:]:
            self.logger.removeHandler(handler)
        
        # 创建格式化器
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        # 控制台处理器
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)
        
        # 文件处理器（滚动文件）
        try:
            # 解析文件大小
            size_bytes = self._parse_size(max_file_size)
            file_handler = RotatingFileHandler(
                log_file,
                maxBytes=size_bytes,
                backupCount=backup_count,
                encoding='utf-8'
            )
            file_handler.setLevel(level)
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
        except Exception as e:
            self.logger.error(f"无法创建文件日志处理器: {e}")
        
        # 设置为根logger
        logging.root = self.logger
    
    def _parse_size(self, size_str: str) -> int:
        """解析文件大小字符串，如 '10MB' -> 字节数"""
        size_str = size_str.upper().strip()
        
        if size_str.endswith('KB'):
            return int(float(size_str[:-2]) * 1024)
        elif size_str.endswith('MB'):
            return int(float(size_str[:-2]) * 1024 * 1024)
        elif size_str.endswith('GB'):
            return int(float(size_str[:-2]) * 1024 * 1024 * 1024)
        else:
            # 默认假设为字节
            return int(size_str)
    
    def get_logger(self, name: Optional[str] = None) -> logging.Logger:
        """获取logger实例"""
        if name:
            return logging.getLogger(f'allsky.{name}')
        return self.logger
    
    def log_camera_event(self, event: str, details: dict = None) -> None:
        """记录相机相关事件"""
        message = f"相机事件: {event}"
        if details:
            message += f" - 详细信息: {details}"
        self.logger.info(message)
    
    def log_image_capture(self, filename: str, settings: dict = None) -> None:
        """记录图像捕获事件"""
        message = f"图像捕获: {filename}"
        if settings:
            message += f" - 设置: {settings}"
        self.logger.info(message)
    
    def log_api_request(self, endpoint: str, method: str, params: dict = None) -> None:
        """记录API请求"""
        message = f"API请求: {method} {endpoint}"
        if params:
            message += f" - 参数: {params}"
        self.logger.info(message)
    
    def log_weather_update(self, data: dict) -> None:
        """记录天气数据更新"""
        self.logger.info(f"天气数据更新: {data}")
    
    def log_astronomy_calculation(self, calculation_type: str, result: dict) -> None:
        """记录天文计算结果"""
        self.logger.info(f"天文计算 [{calculation_type}]: {result}")
    
    def log_error_with_context(self, error: Exception, context: str) -> None:
        """记录带上下文的错误"""
        self.logger.error(f"错误发生在 {context}: {str(error)}", exc_info=True)
    
    def log_performance_metric(self, operation: str, duration: float) -> None:
        """记录性能指标"""
        self.logger.info(f"性能指标 - {operation}: {duration:.3f}秒")


# 创建一个装饰器来记录函数执行时间
def log_execution_time(operation_name: str = None):
    """装饰器：记录函数执行时间"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = datetime.now()
            try:
                result = func(*args, **kwargs)
                duration = (datetime.now() - start_time).total_seconds()
                
                name = operation_name or func.__name__
                logging.getLogger('allsky').info(f"执行完成 - {name}: {duration:.3f}秒")
                return result
            except Exception as e:
                duration = (datetime.now() - start_time).total_seconds()
                name = operation_name or func.__name__
                logging.getLogger('allsky').error(
                    f"执行失败 - {name}: {duration:.3f}秒, 错误: {str(e)}", 
                    exc_info=True
                )
                raise
        return wrapper
    return decorator


# 全局日志管理器（在主程序中初始化）
logger_manager = None

def init_logger(config_manager=None):
    """初始化全局日志管理器"""
    global logger_manager
    logger_manager = LoggerManager(config_manager)
    return logger_manager

def get_logger(name: str = None) -> logging.Logger:
    """获取logger实例的便捷函数"""
    if logger_manager:
        return logger_manager.get_logger(name)
    else:
        # 如果没有初始化，返回默认logger
        return logging.getLogger(name or 'allsky')