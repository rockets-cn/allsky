#!/usr/bin/env python3
"""
AllSky启动脚本 - 自动检测可用端口并启动应用
"""

import socket
import json
import os
import sys
import subprocess


def is_port_available(port):
    """检查端口是否可用"""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(('localhost', port))
            return True
    except OSError:
        return False


def find_available_port(start_port=5000, max_attempts=100):
    """查找可用端口"""
    for port in range(start_port, start_port + max_attempts):
        if is_port_available(port):
            return port
    return None


def update_config_port(port):
    """更新配置文件中的端口"""
    config_file = 'config.json'
    if not os.path.exists(config_file):
        print(f"错误: 配置文件 {config_file} 不存在")
        return False
    
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        config['server']['port'] = port
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        print(f"✅ 已更新配置文件端口为: {port}")
        return True
    except Exception as e:
        print(f"错误: 更新配置文件失败 - {e}")
        return False


def main():
    """主函数"""
    print("🚀 AllSky自动启动脚本")
    print("=" * 40)
    
    # 检查当前配置的端口
    try:
        with open('config.json', 'r', encoding='utf-8') as f:
            config = json.load(f)
        current_port = config.get('server', {}).get('port', 5000)
    except:
        current_port = 5000
    
    print(f"当前配置端口: {current_port}")
    
    # 检查当前端口是否可用
    if is_port_available(current_port):
        print(f"✅ 端口 {current_port} 可用")
        port_to_use = current_port
    else:
        print(f"❌ 端口 {current_port} 不可用，正在查找可用端口...")
        
        # 查找可用端口
        available_port = find_available_port(5000)
        if available_port:
            print(f"✅ 找到可用端口: {available_port}")
            port_to_use = available_port
            
            # 更新配置文件
            if not update_config_port(available_port):
                return 1
        else:
            print("❌ 未找到可用端口 (5000-5099)")
            return 1
    
    # 启动应用
    print(f"🎯 启动AllSky服务器，端口: {port_to_use}")
    print(f"🌐 访问地址: http://localhost:{port_to_use}")
    print("=" * 40)
    
    try:
        # 启动主程序
        subprocess.run([sys.executable, 'allsky_complete.py'], check=True)
    except KeyboardInterrupt:
        print("\n👋 用户中断，正在关闭...")
    except subprocess.CalledProcessError as e:
        print(f"❌ 启动失败: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())