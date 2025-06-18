# AllSky 星空相机系统

## 项目简介
AllSky 是一个基于 Python 和 OpenCV 的全景星空相机系统，支持自动捕获夜空图像，并在图片上叠加观测站信息、时间、经纬度、曝光、气象、罗盘、LOGO、星体标注等，生成美观的全天空观测图片。适用于天文台、科普、气象等场景。

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
1. 安装依赖：
   ```bash
   pip install -r requirements.txt
   ```
   主要依赖：opencv-python, flask, astral, numpy
2. 启动服务：
   ```bash
   python allsky.py
   ```
3. 通过浏览器或 HTTP 工具访问接口，如：
   - `http://localhost:5000/capture_image`

## 目录结构
- `allsky.py`         主程序，Flask接口与图像处理
- `allsky.html`       前端页面（可选）
- `camera_settings.html`  摄像头参数设置页面（可选）
- `WechatIMG38126.jpg`    默认LOGO图片
- `.cursor/scratchpad.md`  项目开发规划文档

## 扩展建议
- 对接真实气象/罗盘/星表数据
- 增加定时自动拍摄、历史图片管理等功能
- 美化前端页面，支持远程实时预览

---

> 开源地址：https://github.com/rockets-cn/allsky 