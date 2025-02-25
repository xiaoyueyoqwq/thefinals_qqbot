#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
启动自动PR MCP服务器（SSE模式）
"""

import os
import sys
import logging
import subprocess
from pathlib import Path

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("start_auto_pr")

def check_dependencies():
    """检查依赖是否安装"""
    try:
        import mcp
    except ImportError:
        logger.error("缺少必要的依赖，正在安装...")
        subprocess.run([
            sys.executable, "-m", "pip", "install", "mcp"
        ], check=True)
        logger.info("依赖安装完成")

def check_git_setup():
    """检查Git设置"""
    try:
        # 检查是否可以访问GitHub
        result = subprocess.run(
            ["git", "remote", "-v"],
            capture_output=True,
            text=True
        )
        
        if "github.com" not in result.stdout.lower():
            logger.warning("未检测到GitHub远程仓库，自动PR功能可能无法正常工作")
        
        # 检查GitHub CLI
        try:
            subprocess.run(["gh", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.warning(
                "GitHub CLI未安装，无法自动创建PR。"
                "请安装GitHub CLI: https://cli.github.com/"
            )
            logger.warning("安装后请运行 `gh auth login` 进行认证")
    
    except Exception as e:
        logger.error(f"检查Git设置时出错: {str(e)}")

def start_server():
    """启动MCP服务器（SSE模式）"""
    try:
        # 获取当前脚本所在目录
        current_dir = Path(__file__).parent.absolute()
        server_path = current_dir / "auto_pr_server.py"
        
        if not server_path.exists():
            logger.error(f"找不到服务器脚本: {server_path}")
            return
        
        # 启动服务器，使用SSE模式
        logger.info("正在启动自动PR MCP服务器（SSE模式）...")
        
        # 使用Python解释器启动服务器
        subprocess.run([
            sys.executable, 
            str(server_path),
            "--transport", "sse",
            "--port", "8000"
        ])
    
    except Exception as e:
        logger.error(f"启动服务器失败: {str(e)}")

if __name__ == "__main__":
    print("="*50)
    print("自动PR MCP服务器启动工具 (SSE模式)")
    print("="*50)
    
    # 检查依赖
    check_dependencies()
    
    # 检查Git设置
    check_git_setup()
    
    # 启动服务器
    start_server() 