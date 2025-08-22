# AllSky 星空相机系统

## 项目简介
AllSky 是一个基于 Python 和 OpenCV 的全景星空相机系统，支持自动捕获夜空图像，并在图片上叠加观测站信息、时间、经纬度、曝光、气象、罗盘、LOGO、星体标注等，生成美观的全天空观测图片。适用于天文台、科普、气象等场景。

## 🆕 改进版本
项目现在提供了两个版本：
- **`allsky.py`** - 原始版本，功能完整但代码结构较简单
- **`allsky_improved.py`** - 改进版本，具有更好的架构、错误处理和性能

## 🆕 完整版本
项目现在提供了三个版本：
- **`allsky.py`** - 原始版本，功能完整但代码结构较简单
- **`allsky_improved.py`** - 改进版本，具有更好的架构、错误处理和性能
- **`allsky_complete.py`** - 完整版本，集成所有新功能模块

### 完整版本特性
- 🌤️ **真实天气数据** - 集成OpenWeatherMap API，实时获取气象信息
- ⭐ **天文数据计算** - 真实的星体位置、行星轨道、月相等计算
- 📸 **图像历史管理** - 自动存储策略、定时拍摄、批处理功能
- 🌐 **现代化Web界面** - 响应式设计、实时预览、移动端支持
- 📊 **完整监控系统** - 系统状态、性能指标、错误统计
- 🔧 **高级配置管理** - 热更新、验证、备份恢复

## 主要功能
- 自动根据昼夜切换曝光参数，捕获全景星空图片
- 图片自动叠加：
  - 观测站名、经纬度、时间、日出日落、曝光
  - 罗盘（N/E/S/W，支持外部方向数据）
  - 气象数据（支持外部接口，默认N/A）
  - LOGO（可自定义）
  - 星体标注（支持扩展真实星表）
- 支持通过 HTTP 接口远程控制和配置参数

## 主要接口
- `GET /capture_image`：捕获一张图片并返回，图片带全部叠加信息
- `POST /apply_settings`：设置不同天光阶段的曝光/增益参数
- `POST /set_station_info`：设置观测站名和经纬度
- `GET /get_station_info`：查询当前观测站参数

## 运行方法

### 快速开始
1. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
   主要依赖：opencv-python, flask, astral, numpy

2. 启动服务：
   ```bash
   # 使用完整版本（推荐）
   python allsky_complete.py
   
   # 或使用改进版本
   python allsky_improved.py
   
   # 或使用原始版本
   python allsky.py
   ```

3. 访问接口：
   - 图像捕获：`http://localhost:5000/capture_image`
   - 健康检查：`http://localhost:5000/health`
   - 前端页面：`http://localhost:5000/allsky.html`

### 配置说明
改进版支持通过 `config.json` 进行配置：

```json
{
  "camera": {
    "index": 0,  // 相机索引
    "default_settings": {
      "day": {"exposure": -5, "gain": 10},
      "night": {"exposure": 5, "gain": 40}
    }
  },
  "station": {
    "name": "Your Observatory",
    "latitude": 40.7128,
    "longitude": -74.0060
  },
  "server": {
    "host": "0.0.0.0",
    "port": 5000
  }
}
```

## 目录结构
### 主程序文件
- `allsky.py`                原始主程序，Flask接口与图像处理
- `allsky_improved.py`       改进版主程序，具有更好的架构和错误处理
- `allsky_complete.py`       完整版主程序，集成所有新功能模块

### 功能模块
- `config_manager.py`        配置管理模块
- `logger_manager.py`        日志管理模块
- `exceptions.py`            异常处理模块
- `weather_manager.py`       天气API管理模块
- `astronomy_manager.py`     天文数据管理模块
- `image_manager.py`         图像历史管理模块

### 配置和文档
- `config.json`              配置文件（改进版使用）
- `requirements.txt`         Python依赖包列表
- `IMPROVEMENTS.md`          详细改进说明文档
- `README.md`                项目说明文档

### Web界面
- `allsky.html`              简单前端页面
- `camera_settings.html`     摄像头参数设置页面
- `dashboard.html`           现代化控制面板（完整版使用）

### 资源文件
- `WechatIMG38126.jpg`       默认LOGO图片

## 扩展建议
- 对接真实气象/罗盘/星表数据
- 增加定时自动拍摄、历史图片管理等功能
- 美化前端页面，支持远程实时预览

---

> 开源地址：https://github.com/rockets-cn/allsky 