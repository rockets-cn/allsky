"""
自定义异常类和错误处理工具
"""
import functools
import traceback
from typing import Optional, Callable, Any
from datetime import datetime


class AllSkyError(Exception):
    """AllSky系统基础异常类"""
    
    def __init__(self, message: str, error_code: str = None, details: dict = None):
        self.message = message
        self.error_code = error_code or "UNKNOWN_ERROR"
        self.details = details or {}
        self.timestamp = datetime.now()
        super().__init__(self.message)
    
    def to_dict(self) -> dict:
        """转换为字典格式，用于API响应"""
        return {
            "error": True,
            "error_code": self.error_code,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat()
        }


class CameraError(AllSkyError):
    """相机相关错误"""
    
    def __init__(self, message: str, camera_index: int = None, details: dict = None):
        super().__init__(message, "CAMERA_ERROR", details)
        self.camera_index = camera_index


class ConfigurationError(AllSkyError):
    """配置相关错误"""
    
    def __init__(self, message: str, config_key: str = None, details: dict = None):
        super().__init__(message, "CONFIG_ERROR", details)
        self.config_key = config_key


class WeatherAPIError(AllSkyError):
    """天气API相关错误"""
    
    def __init__(self, message: str, api_endpoint: str = None, details: dict = None):
        super().__init__(message, "WEATHER_API_ERROR", details)
        self.api_endpoint = api_endpoint


class ImageProcessingError(AllSkyError):
    """图像处理相关错误"""
    
    def __init__(self, message: str, operation: str = None, details: dict = None):
        super().__init__(message, "IMAGE_PROCESSING_ERROR", details)
        self.operation = operation


class AstronomyCalculationError(AllSkyError):
    """天文计算相关错误"""
    
    def __init__(self, message: str, calculation_type: str = None, details: dict = None):
        super().__init__(message, "ASTRONOMY_ERROR", details)
        self.calculation_type = calculation_type


class FileOperationError(AllSkyError):
    """文件操作相关错误"""
    
    def __init__(self, message: str, file_path: str = None, operation: str = None, details: dict = None):
        super().__init__(message, "FILE_ERROR", details)
        self.file_path = file_path
        self.operation = operation


def safe_execute(operation_name: str = None, 
                default_return: Any = None,
                reraise: bool = False,
                logger=None):
    """
    安全执行装饰器，捕获异常并记录日志
    
    Args:
        operation_name: 操作名称，用于日志记录
        default_return: 发生异常时的默认返回值
        reraise: 是否重新抛出异常
        logger: 日志记录器
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            op_name = operation_name or func.__name__
            
            try:
                return func(*args, **kwargs)
            except AllSkyError as e:
                # 自定义异常，直接记录并处理
                if logger:
                    logger.error(f"操作失败 [{op_name}]: {e.message}", extra={"error_details": e.details})
                else:
                    print(f"错误 [{op_name}]: {e.message}")
                
                if reraise:
                    raise
                return default_return
            except Exception as e:
                # 其他异常，包装为AllSkyError
                error_msg = f"操作 '{op_name}' 执行时发生未预期的错误: {str(e)}"
                
                if logger:
                    logger.error(error_msg, exc_info=True)
                else:
                    print(f"错误: {error_msg}")
                    traceback.print_exc()
                
                if reraise:
                    raise AllSkyError(error_msg, "UNEXPECTED_ERROR", {"original_error": str(e)})
                return default_return
        
        return wrapper
    return decorator


def retry_on_failure(max_retries: int = 3, 
                    delay: float = 1.0,
                    exponential_backoff: bool = True,
                    logger=None):
    """
    重试装饰器，在失败时自动重试
    
    Args:
        max_retries: 最大重试次数
        delay: 重试延迟（秒）
        exponential_backoff: 是否使用指数退避
        logger: 日志记录器
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            import time
            
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    
                    if attempt < max_retries:
                        # 计算延迟时间
                        wait_time = delay * (2 ** attempt) if exponential_backoff else delay
                        
                        if logger:
                            logger.warning(f"操作 '{func.__name__}' 第 {attempt + 1} 次尝试失败，"
                                         f"{wait_time:.1f}秒后重试: {str(e)}")
                        
                        time.sleep(wait_time)
                    else:
                        if logger:
                            logger.error(f"操作 '{func.__name__}' 重试 {max_retries} 次后仍然失败")
            
            # 所有重试都失败，抛出最后一个异常
            raise last_exception
        
        return wrapper
    return decorator


def validate_input(validation_func: Callable, error_message: str = None):
    """
    输入验证装饰器
    
    Args:
        validation_func: 验证函数，接收函数参数并返回True/False
        error_message: 验证失败时的错误消息
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            if not validation_func(*args, **kwargs):
                msg = error_message or f"函数 '{func.__name__}' 的输入参数验证失败"
                raise ConfigurationError(msg, details={"args": args, "kwargs": kwargs})
            
            return func(*args, **kwargs)
        
        return wrapper
    return decorator


class ErrorHandler:
    """错误处理器，提供统一的错误处理方法"""
    
    def __init__(self, logger=None):
        self.logger = logger
        self.error_count = 0
        self.last_errors = []
        self.max_stored_errors = 50
    
    def handle_error(self, error: Exception, context: str = None) -> dict:
        """
        处理错误并返回标准化的错误响应
        
        Args:
            error: 异常对象
            context: 错误上下文信息
            
        Returns:
            标准化的错误响应字典
        """
        self.error_count += 1
        
        # 构建错误信息
        if isinstance(error, AllSkyError):
            error_info = error.to_dict()
        else:
            error_info = {
                "error": True,
                "error_code": "UNEXPECTED_ERROR",
                "message": str(error),
                "details": {"type": type(error).__name__},
                "timestamp": datetime.now().isoformat()
            }
        
        # 添加上下文信息
        if context:
            error_info["context"] = context
        
        # 记录到日志
        if self.logger:
            self.logger.error(f"错误处理 - {context or '未知上下文'}: {error_info['message']}", 
                            exc_info=True)
        
        # 存储错误历史
        self.last_errors.append(error_info)
        if len(self.last_errors) > self.max_stored_errors:
            self.last_errors.pop(0)
        
        return error_info
    
    def get_error_statistics(self) -> dict:
        """获取错误统计信息"""
        return {
            "total_errors": self.error_count,
            "recent_errors": len(self.last_errors),
            "last_error": self.last_errors[-1] if self.last_errors else None
        }
    
    def clear_error_history(self) -> None:
        """清除错误历史记录"""
        self.last_errors.clear()


# 全局错误处理器实例
global_error_handler = ErrorHandler()


def set_global_error_handler(error_handler: ErrorHandler) -> None:
    """设置全局错误处理器"""
    global global_error_handler
    global_error_handler = error_handler


def get_global_error_handler() -> ErrorHandler:
    """获取全局错误处理器"""
    return global_error_handler