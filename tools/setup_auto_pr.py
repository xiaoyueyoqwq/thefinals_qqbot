#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
自动PR功能设置脚本
设置MCP代理的自动启动和自启动功能
"""

import os
import sys
import json
import shutil
import logging
import platform
import subprocess
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("setup_auto_pr")

# 获取工作目录
working_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
tools_dir = os.path.join(working_dir, "tools")
cursor_dir = os.path.join(working_dir, ".cursor")

def ensure_dir_exists(dir_path):
    """确保目录存在"""
    os.makedirs(dir_path, exist_ok=True)

def check_dependencies():
    """检查依赖是否安装"""
    try:
        import fastapi
        import uvicorn
        import requests
    except ImportError:
        logger.error("缺少必要的依赖，正在安装...")
        subprocess.run([
            sys.executable, "-m", "pip", "install", 
            "fastapi", "uvicorn[standard]", "requests"
        ], check=True)
        logger.info("依赖安装完成")

def update_mcp_config():
    """更新MCP配置文件"""
    try:
        # 确保.cursor目录存在
        ensure_dir_exists(cursor_dir)
        
        mcp_config_path = os.path.join(cursor_dir, "mcp.json")
        
        # 构建代理URL
        proxy_url = "http://localhost:3333/mcp"
        
        # 如果配置文件存在，读取并更新
        if os.path.exists(mcp_config_path):
            with open(mcp_config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
            # 更新Auto PR Server的URL
            for server in config.get("servers", []):
                if server.get("name") == "Auto PR Server":
                    server["url"] = proxy_url
                    logger.info("已更新MCP配置文件中的服务器URL")
                    break
        else:
            # 创建新的配置文件
            config = {
                "version": "1.0",
                "servers": [
                    {
                        "name": "Auto PR Server",
                        "description": "自动创建PR的MCP服务器",
                        "url": proxy_url,
                        "tools": [
                            {
                                "name": "create_pr",
                                "description": "创建PR并提交更改",
                                "input_schema": {
                                    "type": "object",
                                    "properties": {
                                        "title": {
                                            "type": "string",
                                            "description": "PR标题（英文）"
                                        },
                                        "branch": {
                                            "type": "string",
                                            "description": "目标分支名称"
                                        },
                                        "changes": {
                                            "type": "string",
                                            "description": "变更内容描述（英文）"
                                        }
                                    },
                                    "required": ["title", "branch", "changes"]
                                },
                                "output_schema": {
                                    "type": "object",
                                    "properties": {
                                        "pr_url": {
                                            "type": "string",
                                            "description": "创建的PR链接"
                                        },
                                        "pr_title": {
                                            "type": "string",
                                            "description": "PR标题"
                                        },
                                        "pr_description": {
                                            "type": "string",
                                            "description": "PR描述"
                                        }
                                    }
                                }
                            }
                        ]
                    }
                ]
            }
            logger.info("已创建新的MCP配置文件")
        
        # 保存配置文件
        with open(mcp_config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
            
        logger.info(f"MCP配置文件已保存至: {mcp_config_path}")
        return True
        
    except Exception as e:
        logger.error(f"更新MCP配置文件失败: {str(e)}")
        return False

def setup_windows_autostart():
    """设置Windows自启动"""
    try:
        import winreg
        
        # 准备自启动脚本
        startup_script = os.path.join(tools_dir, "auto_pr_proxy_startup.bat")
        
        with open(startup_script, 'w') as f:
            f.write(f'@echo off\n')
            f.write(f'cd /d "{working_dir}"\n')
            f.write(f'start /min "{sys.executable}" "{os.path.join(tools_dir, "auto_pr_proxy.py")}" --background\n')
        
        # 添加到注册表
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, 
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\Run", 
            0, 
            winreg.KEY_WRITE
        )
        
        winreg.SetValueEx(
            key, 
            "CursorAutoPR", 
            0, 
            winreg.REG_SZ, 
            startup_script
        )
        
        winreg.CloseKey(key)
        logger.info("已添加到Windows自启动项")
        return True
        
    except Exception as e:
        logger.error(f"设置Windows自启动失败: {str(e)}")
        return False

def setup_linux_macos_autostart():
    """设置Linux/macOS自启动"""
    try:
        # 确定用户主目录
        home_dir = str(Path.home())
        
        # 创建自启动脚本
        startup_script = os.path.join(tools_dir, "auto_pr_proxy_startup.sh")
        
        with open(startup_script, 'w') as f:
            f.write('#!/bin/bash\n')
            f.write(f'cd "{working_dir}"\n')
            f.write(f'nohup {sys.executable} "{os.path.join(tools_dir, "auto_pr_proxy.py")}" --background > /dev/null 2>&1 &\n')
        
        # 设置执行权限
        os.chmod(startup_script, 0o755)
        
        if platform.system() == "Darwin":  # macOS
            # 创建启动代理plist文件
            plist_path = os.path.join(home_dir, "Library/LaunchAgents/com.cursor.autopr.plist")
            plist_dir = os.path.dirname(plist_path)
            
            if not os.path.exists(plist_dir):
                os.makedirs(plist_dir)
            
            with open(plist_path, 'w') as f:
                f.write(f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.cursor.autopr</string>
    <key>ProgramArguments</key>
    <array>
        <string>{startup_script}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
</dict>
</plist>''')
                
            # 加载启动代理
            subprocess.run(["launchctl", "load", plist_path], check=True)
            logger.info("已添加到macOS自启动项")
            
        else:  # Linux
            # 创建systemd用户服务
            service_path = os.path.join(home_dir, ".config/systemd/user/cursor-autopr.service")
            service_dir = os.path.dirname(service_path)
            
            if not os.path.exists(service_dir):
                os.makedirs(service_dir)
            
            with open(service_path, 'w') as f:
                f.write(f'''[Unit]
Description=Cursor Auto PR Proxy
After=network.target

[Service]
Type=simple
ExecStart={startup_script}
Restart=on-failure

[Install]
WantedBy=default.target
''')
            
            # 启用并启动服务
            subprocess.run(["systemctl", "--user", "enable", "cursor-autopr.service"], check=True)
            subprocess.run(["systemctl", "--user", "start", "cursor-autopr.service"], check=True)
            logger.info("已添加到Linux自启动项")
            
        return True
        
    except Exception as e:
        logger.error(f"设置Linux/macOS自启动失败: {str(e)}")
        return False

def setup_autostart():
    """设置自启动"""
    system = platform.system()
    
    if system == "Windows":
        return setup_windows_autostart()
    elif system in ["Darwin", "Linux"]:
        return setup_linux_macos_autostart()
    else:
        logger.error(f"不支持的操作系统: {system}")
        return False

def start_proxy_now():
    """立即启动代理"""
    try:
        proxy_script = os.path.join(tools_dir, "auto_pr_proxy.py")
        
        if os.name == 'nt':  # Windows
            subprocess.Popen(
                ["start", "/min", sys.executable, proxy_script, "--background"],
                shell=True
            )
        else:  # Linux/macOS
            subprocess.Popen(
                [sys.executable, proxy_script, "--background"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
        
        logger.info("代理服务器已在后台启动")
        return True
        
    except Exception as e:
        logger.error(f"启动代理服务器失败: {str(e)}")
        return False

def main():
    """主函数"""
    print("="*50)
    print("自动PR功能设置工具")
    print("="*50)
    print("此工具将设置MCP代理的自动启动功能")
    print()
    
    # 检查依赖
    check_dependencies()
    
    # 更新MCP配置
    if update_mcp_config():
        print("✓ MCP配置文件更新成功")
    else:
        print("✗ MCP配置文件更新失败")
        return
    
    # 设置自启动
    if setup_autostart():
        print("✓ 自启动设置成功")
    else:
        print("✗ 自启动设置失败")
    
    # 立即启动代理
    if start_proxy_now():
        print("✓ 代理服务器已在后台启动")
    else:
        print("✗ 代理服务器启动失败")
    
    print()
    print("设置完成！现在你可以在Cursor中直接使用自动PR功能，无需手动启动服务器。")
    print("下次电脑启动时，代理服务器将自动运行。")
    print()
    print("使用说明：")
    print("1. 在与AI对话时，直接请求创建PR")
    print("2. AI会自动调用MCP工具，代理会按需启动服务器")
    print("3. 你只需提供PR标题、分支名和变更内容描述即可")
    print()
    print("享受自动化的PR创建体验吧！")

if __name__ == "__main__":
    main() 