"""
图像管理模块
提供图像历史管理、定时拍摄、批处理和存储策略功能
"""

import os
import cv2
import json
import time
import shutil
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from pathlib import Path
import glob

from logger_manager import get_logger, log_execution_time
from exceptions import FileOperationError, ImageProcessingError, safe_execute

logger = get_logger('image_manager')


class ImageMetadata:
    """图像元数据管理"""
    
    def __init__(self, image_path: str, capture_time: datetime = None):
        self.image_path = image_path
        self.capture_time = capture_time or datetime.now()
        self.file_size = 0
        self.resolution = (0, 0)
        self.exposure_settings = {}
        self.weather_data = {}
        self.astronomy_data = {}
        self.processing_info = {}
        
        self._analyze_image()
    
    def _analyze_image(self):
        """分析图像基本信息"""
        try:
            if os.path.exists(self.image_path):
                self.file_size = os.path.getsize(self.image_path)
                
                # 读取图像分辨率
                img = cv2.imread(self.image_path)
                if img is not None:
                    self.resolution = (img.shape[1], img.shape[0])  # (width, height)
        except Exception as e:
            logger.warning(f"分析图像 {self.image_path} 失败: {e}")
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式"""
        return {
            'image_path': self.image_path,
            'capture_time': self.capture_time.isoformat(),
            'file_size': self.file_size,
            'resolution': self.resolution,
            'exposure_settings': self.exposure_settings,
            'weather_data': self.weather_data,
            'astronomy_data': self.astronomy_data,
            'processing_info': self.processing_info
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ImageMetadata':
        """从字典创建对象"""
        metadata = cls(data['image_path'], datetime.fromisoformat(data['capture_time']))
        metadata.file_size = data.get('file_size', 0)
        metadata.resolution = tuple(data.get('resolution', (0, 0)))
        metadata.exposure_settings = data.get('exposure_settings', {})
        metadata.weather_data = data.get('weather_data', {})
        metadata.astronomy_data = data.get('astronomy_data', {})
        metadata.processing_info = data.get('processing_info', {})
        return metadata


class StorageManager:
    """存储管理器，处理图像文件的存储策略"""
    
    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        
        if config_manager:
            image_config = config_manager.get('image', {})
            self.base_path = config_manager.get('paths.output_path', './all_sky_images')
            self.max_stored_images = image_config.get('max_stored_images', 1000)
            self.archive_enabled = image_config.get('archive_enabled', True)
            self.archive_path = image_config.get('archive_path', './archive')
        else:
            self.base_path = './all_sky_images'
            self.max_stored_images = 1000
            self.archive_enabled = True
            self.archive_path = './archive'
        
        # 确保目录存在
        for path in [self.base_path, self.archive_path]:
            os.makedirs(path, exist_ok=True)
    
    @safe_execute("创建日期目录")
    def create_date_directory(self, date: datetime = None) -> str:
        """创建基于日期的目录结构"""
        if date is None:
            date = datetime.now()
        
        date_str = date.strftime('%Y/%m/%d')
        full_path = os.path.join(self.base_path, date_str)
        os.makedirs(full_path, exist_ok=True)
        return full_path
    
    @safe_execute("生成文件名")
    def generate_filename(self, capture_time: datetime = None, 
                         prefix: str = 'allsky', suffix: str = 'jpg') -> str:
        """生成标准化的文件名"""
        if capture_time is None:
            capture_time = datetime.now()
        
        timestamp = capture_time.strftime('%Y%m%d_%H%M%S')
        return f"{prefix}_{timestamp}.{suffix}"
    
    @safe_execute("获取完整路径")
    def get_full_path(self, filename: str, capture_time: datetime = None) -> str:
        """获取文件的完整路径"""
        date_dir = self.create_date_directory(capture_time)
        return os.path.join(date_dir, filename)
    
    @safe_execute("清理旧文件")
    def cleanup_old_files(self) -> Dict[str, int]:
        """清理旧文件，根据配置的最大存储数量"""
        try:
            # 获取所有图像文件
            pattern = os.path.join(self.base_path, '**', '*.jpg')
            all_files = glob.glob(pattern, recursive=True)
            
            if len(all_files) <= self.max_stored_images:
                return {'deleted': 0, 'archived': 0, 'total': len(all_files)}
            
            # 按修改时间排序
            all_files.sort(key=lambda x: os.path.getmtime(x))
            
            # 计算需要删除的文件数量
            files_to_remove = len(all_files) - self.max_stored_images
            old_files = all_files[:files_to_remove]
            
            deleted_count = 0
            archived_count = 0
            
            for file_path in old_files:
                try:
                    if self.archive_enabled:
                        # 归档文件
                        self._archive_file(file_path)
                        archived_count += 1
                    else:
                        # 直接删除
                        os.remove(file_path)
                        deleted_count += 1
                        
                except Exception as e:
                    logger.error(f"处理文件 {file_path} 失败: {e}")
            
            logger.info(f"清理完成: 删除 {deleted_count} 个文件, 归档 {archived_count} 个文件")
            return {'deleted': deleted_count, 'archived': archived_count, 'total': len(all_files)}
            
        except Exception as e:
            raise FileOperationError(f"清理旧文件失败: {str(e)}", operation="cleanup")
    
    def _archive_file(self, file_path: str):
        """归档单个文件"""
        try:
            # 保持目录结构
            rel_path = os.path.relpath(file_path, self.base_path)
            archive_file_path = os.path.join(self.archive_path, rel_path)
            
            # 创建归档目录
            os.makedirs(os.path.dirname(archive_file_path), exist_ok=True)
            
            # 移动文件到归档目录
            shutil.move(file_path, archive_file_path)
            
        except Exception as e:
            logger.error(f"归档文件 {file_path} 失败: {e}")
    
    @safe_execute("获取存储统计")
    def get_storage_stats(self) -> Dict[str, Any]:
        """获取存储统计信息"""
        try:
            # 当前存储的文件
            pattern = os.path.join(self.base_path, '**', '*.jpg')
            current_files = glob.glob(pattern, recursive=True)
            
            # 计算总大小
            total_size = sum(os.path.getsize(f) for f in current_files if os.path.exists(f))
            
            # 归档文件
            archive_pattern = os.path.join(self.archive_path, '**', '*.jpg')
            archive_files = glob.glob(archive_pattern, recursive=True)
            archive_size = sum(os.path.getsize(f) for f in archive_files if os.path.exists(f))
            
            return {
                'current_files': len(current_files),
                'current_size_mb': total_size / (1024 * 1024),
                'archive_files': len(archive_files),
                'archive_size_mb': archive_size / (1024 * 1024),
                'max_files': self.max_stored_images,
                'usage_percent': (len(current_files) / self.max_stored_images) * 100
            }
            
        except Exception as e:
            logger.error(f"获取存储统计失败: {e}")
            return {}


class ScheduledCapture:
    """定时拍摄管理器"""
    
    def __init__(self, capture_callback: Callable, config_manager=None):
        self.capture_callback = capture_callback
        self.config_manager = config_manager
        self.is_running = False
        self.thread = None
        self.stop_event = threading.Event()
        
        if config_manager:
            image_config = config_manager.get('image', {})
            self.auto_capture = image_config.get('auto_capture', False)
            self.capture_interval = image_config.get('capture_interval', 60)
            self.night_only = image_config.get('night_only', False)
            self.weather_check = image_config.get('weather_check', False)
        else:
            self.auto_capture = False
            self.capture_interval = 60
            self.night_only = False
            self.weather_check = False
    
    @safe_execute("启动定时拍摄")
    def start(self) -> bool:
        """启动定时拍摄"""
        if self.is_running:
            logger.warning("定时拍摄已在运行")
            return False
        
        if not self.auto_capture:
            logger.info("自动拍摄功能已禁用")
            return False
        
        self.is_running = True
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._capture_loop, daemon=True)
        self.thread.start()
        
        logger.info(f"定时拍摄已启动，间隔 {self.capture_interval} 秒")
        return True
    
    @safe_execute("停止定时拍摄")
    def stop(self):
        """停止定时拍摄"""
        if not self.is_running:
            return
        
        self.is_running = False
        self.stop_event.set()
        
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        
        logger.info("定时拍摄已停止")
    
    def _capture_loop(self):
        """拍摄循环"""
        while self.is_running and not self.stop_event.is_set():
            try:
                # 检查是否应该拍摄
                if self._should_capture():
                    logger.info("执行定时拍摄")
                    self.capture_callback()
                else:
                    logger.debug("跳过此次拍摄")
                
                # 等待下次拍摄
                self.stop_event.wait(self.capture_interval)
                
            except Exception as e:
                logger.error(f"定时拍摄出错: {e}")
                # 出错后等待一段时间再继续
                self.stop_event.wait(min(self.capture_interval, 60))
    
    def _should_capture(self) -> bool:
        """判断是否应该进行拍摄"""
        try:
            current_time = datetime.now()
            
            # 夜间拍摄检查
            if self.night_only:
                # 简单的夜间判断 (18:00 - 06:00)
                hour = current_time.hour
                if not (hour >= 18 or hour <= 6):
                    return False
            
            # 天气检查
            if self.weather_check:
                # 这里可以集成天气检查逻辑
                # 例如检查云量、降雨等
                pass
            
            return True
            
        except Exception as e:
            logger.error(f"检查拍摄条件失败: {e}")
            return True  # 出错时默认继续拍摄
    
    def get_status(self) -> Dict[str, Any]:
        """获取定时拍摄状态"""
        return {
            'running': self.is_running,
            'auto_capture': self.auto_capture,
            'interval': self.capture_interval,
            'night_only': self.night_only,
            'weather_check': self.weather_check
        }


class ImageManager:
    """图像管理器，整合所有图像相关功能"""
    
    def __init__(self, config_manager=None):
        self.config_manager = config_manager
        self.storage_manager = StorageManager(config_manager)
        self.metadata_cache = {}
        self.metadata_file = os.path.join(self.storage_manager.base_path, 'metadata.json')
        
        # 加载元数据
        self._load_metadata()
        
        # 定时拍摄管理器（需要在外部设置回调）
        self.scheduled_capture = None
    
    def set_capture_callback(self, callback: Callable):
        """设置拍摄回调函数"""
        self.scheduled_capture = ScheduledCapture(callback, self.config_manager)
    
    @safe_execute("保存图像")
    @log_execution_time("图像保存")
    def save_image(self, image_data, capture_time: datetime = None, 
                  exposure_settings: Dict = None, weather_data: Dict = None,
                  astronomy_data: Dict = None) -> str:
        """保存图像并创建元数据"""
        try:
            if capture_time is None:
                capture_time = datetime.now()
            
            # 生成文件名和路径
            filename = self.storage_manager.generate_filename(capture_time)
            full_path = self.storage_manager.get_full_path(filename, capture_time)
            
            # 保存图像
            if isinstance(image_data, str):
                # 如果是文件路径，复制文件
                shutil.copy2(image_data, full_path)
            else:
                # 如果是图像数据，使用OpenCV保存
                quality = 95
                if self.config_manager:
                    quality = self.config_manager.get('image.image_quality', 95)
                
                success = cv2.imwrite(full_path, image_data, [cv2.IMWRITE_JPEG_QUALITY, quality])
                if not success:
                    raise ImageProcessingError(f"保存图像失败: {full_path}", "image_save")
            
            # 创建元数据
            metadata = ImageMetadata(full_path, capture_time)
            if exposure_settings:
                metadata.exposure_settings = exposure_settings
            if weather_data:
                metadata.weather_data = weather_data
            if astronomy_data:
                metadata.astronomy_data = astronomy_data
            
            # 保存元数据
            self.metadata_cache[full_path] = metadata
            self._save_metadata()
            
            # 清理旧文件
            self.storage_manager.cleanup_old_files()
            
            logger.info(f"图像已保存: {full_path}")
            return full_path
            
        except Exception as e:
            raise ImageProcessingError(f"保存图像失败: {str(e)}", "save_image")
    
    @safe_execute("加载元数据")
    def _load_metadata(self):
        """加载元数据文件"""
        try:
            if os.path.exists(self.metadata_file):
                with open(self.metadata_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                self.metadata_cache = {}
                for path, metadata_dict in data.items():
                    if os.path.exists(path):  # 只加载存在的文件
                        self.metadata_cache[path] = ImageMetadata.from_dict(metadata_dict)
                
                logger.info(f"加载了 {len(self.metadata_cache)} 条图像元数据")
        except Exception as e:
            logger.error(f"加载元数据失败: {e}")
            self.metadata_cache = {}
    
    @safe_execute("保存元数据")
    def _save_metadata(self):
        """保存元数据到文件"""
        try:
            # 只保存最近的元数据，避免文件过大
            recent_metadata = {}
            cutoff_date = datetime.now() - timedelta(days=30)
            
            for path, metadata in self.metadata_cache.items():
                if metadata.capture_time > cutoff_date and os.path.exists(path):
                    recent_metadata[path] = metadata.to_dict()
            
            with open(self.metadata_file, 'w', encoding='utf-8') as f:
                json.dump(recent_metadata, f, indent=2, ensure_ascii=False)
                
        except Exception as e:
            logger.error(f"保存元数据失败: {e}")
    
    @safe_execute("获取图像列表")
    def get_images(self, start_date: datetime = None, end_date: datetime = None,
                  limit: int = 100) -> List[Dict[str, Any]]:
        """获取图像列表"""
        try:
            images = []
            
            for path, metadata in self.metadata_cache.items():
                # 日期筛选
                if start_date and metadata.capture_time < start_date:
                    continue
                if end_date and metadata.capture_time > end_date:
                    continue
                
                # 检查文件是否存在
                if os.path.exists(path):
                    images.append(metadata.to_dict())
            
            # 按时间排序
            images.sort(key=lambda x: x['capture_time'], reverse=True)
            
            # 限制数量
            return images[:limit]
            
        except Exception as e:
            logger.error(f"获取图像列表失败: {e}")
            return []
    
    @safe_execute("获取最新图像")
    def get_latest_images(self, count: int = 10) -> List[Dict[str, Any]]:
        """获取最新的图像"""
        return self.get_images(limit=count)
    
    @safe_execute("删除图像")
    def delete_image(self, image_path: str) -> bool:
        """删除指定图像"""
        try:
            if os.path.exists(image_path):
                os.remove(image_path)
            
            # 从元数据缓存中移除
            if image_path in self.metadata_cache:
                del self.metadata_cache[image_path]
                self._save_metadata()
            
            logger.info(f"图像已删除: {image_path}")
            return True
            
        except Exception as e:
            logger.error(f"删除图像失败: {e}")
            return False
    
    def get_statistics(self) -> Dict[str, Any]:
        """获取图像管理统计信息"""
        try:
            storage_stats = self.storage_manager.get_storage_stats()
            
            # 计算最近活动
            recent_count = 0
            cutoff_time = datetime.now() - timedelta(hours=24)
            
            for metadata in self.metadata_cache.values():
                if metadata.capture_time > cutoff_time:
                    recent_count += 1
            
            stats = {
                'total_images': len(self.metadata_cache),
                'recent_24h': recent_count,
                'storage': storage_stats,
                'scheduled_capture': self.scheduled_capture.get_status() if self.scheduled_capture else None
            }
            
            return stats
            
        except Exception as e:
            logger.error(f"获取统计信息失败: {e}")
            return {}
    
    def start_scheduled_capture(self) -> bool:
        """启动定时拍摄"""
        if self.scheduled_capture:
            return self.scheduled_capture.start()
        return False
    
    def stop_scheduled_capture(self):
        """停止定时拍摄"""
        if self.scheduled_capture:
            self.scheduled_capture.stop()
    
    def cleanup(self):
        """清理资源"""
        try:
            self.stop_scheduled_capture()
            self._save_metadata()
            logger.info("图像管理器清理完成")
        except Exception as e:
            logger.error(f"清理图像管理器失败: {e}")


# 全局图像管理器实例
image_manager = None

def init_image_manager(config_manager=None):
    """初始化全局图像管理器"""
    global image_manager
    image_manager = ImageManager(config_manager)
    return image_manager

def get_image_manager() -> ImageManager:
    """获取全局图像管理器"""
    global image_manager
    if image_manager is None:
        image_manager = ImageManager()
    return image_manager
