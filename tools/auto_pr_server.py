#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
自动PR创建MCP服务器
根据模型输入自动创建GitHub PR
"""

import os
import subprocess
import logging
import argparse
import sys
from typing import Dict, Any
from mcp.server.fastmcp import FastMCP

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/auto_pr_server.log")
    ]
)
logger = logging.getLogger("auto_pr_server")

# 确保日志目录存在
os.makedirs("logs", exist_ok=True)

# 初始化MCP服务器
mcp = FastMCP("auto_pr")

@mcp.tool()
async def create_pr(title: str, branch: str, changes: str) -> Dict[str, str]:
    """创建PR并提交更改
    
    Args:
        title: PR标题（英文）
        branch: 目标分支名称
        changes: 变更内容描述（英文）
    """
    try:
        logger.info(f"创建PR: {title}, 分支: {branch}")
        
        # 检查仓库状态
        try:
            status_result = subprocess.run(
                ["git", "status"], 
                capture_output=True, 
                text=True, 
                check=True
            )
            logger.info(f"仓库状态: \n{status_result.stdout}")
        except Exception as e:
            logger.warning(f"获取仓库状态失败: {str(e)}")
        
        # 1. 创建新分支
        logger.info("步骤1: 创建新分支")
        create_branch(branch)
        
        # 2. 提交所有修改
        logger.info("步骤2: 提交所有修改")
        commit_message = f"{title}\n\n## What's Changed\n{changes}"
        commit_changes(commit_message)
        
        # 3. 推送分支
        logger.info("步骤3: 推送分支")
        push_branch(branch)
        
        # 4. 创建PR
        logger.info("步骤4: 创建GitHub PR")
        pr_url = create_github_pr(title, f"## What's Changed\n{changes}", branch)
        
        # 构建响应
        response = {
            "pr_url": pr_url,
            "pr_title": title,
            "pr_description": f"## What's Changed\n{changes}"
        }
        
        logger.info(f"成功创建PR: {pr_url}")
        return response
    
    except Exception as e:
        error_msg = f"创建PR失败: {str(e)}"
        logger.error(error_msg)
        logger.exception("详细异常信息:")
        
        # 尝试回退到原始分支
        try:
            current_branch_result = subprocess.run(
                ["git", "branch", "--show-current"], 
                capture_output=True, 
                text=True, 
                check=True
            )
            current_branch = current_branch_result.stdout.strip()
            
            if current_branch == branch:
                # 获取默认分支
                result = subprocess.run(
                    ["git", "remote", "show", "origin"], 
                    capture_output=True, 
                    text=True, 
                    check=True
                )
                
                default_branch = "main"  # 默认值
                for line in result.stdout.splitlines():
                    if "HEAD branch" in line:
                        default_branch = line.split(":")[-1].strip()
                        break
                        
                logger.info(f"尝试回退到默认分支: {default_branch}")
                subprocess.run(["git", "checkout", default_branch], check=False)
        except Exception as cleanup_error:
            logger.error(f"回退操作失败: {str(cleanup_error)}")
        
        raise ValueError(error_msg)

def create_branch(branch_name: str) -> None:
    """创建Git分支"""
    try:
        # 获取当前分支作为基础
        result = subprocess.run(
            ["git", "branch", "--show-current"], 
            capture_output=True, 
            text=True, 
            check=True
        )
        base_branch = result.stdout.strip()
        logger.info(f"当前基础分支: {base_branch}")
        
        # 获取默认分支
        try:
            remote_result = subprocess.run(
                ["git", "remote", "-v"], 
                capture_output=True, 
                text=True, 
                check=True
            )
            logger.info(f"远程仓库信息: {remote_result.stdout}")
            
            # 检查远程仓库是否存在
            if not remote_result.stdout.strip():
                logger.warning("未发现远程仓库，将尝试直接创建分支")
            else:
                # 获取默认分支
                default_result = subprocess.run(
                    ["git", "remote", "show", "origin"], 
                    capture_output=True, 
                    text=True, 
                    check=False
                )
                
                default_branch = "main"  # 默认值
                if default_result.returncode == 0:
                    for line in default_result.stdout.splitlines():
                        if "HEAD branch" in line:
                            default_branch = line.split(":")[-1].strip()
                            logger.info(f"发现默认分支: {default_branch}")
                            break
                
                # 切换到默认分支并更新
                logger.info(f"尝试切换到默认分支: {default_branch}")
                checkout_result = subprocess.run(
                    ["git", "checkout", default_branch], 
                    capture_output=True, 
                    text=True, 
                    check=False
                )
                
                if checkout_result.returncode != 0:
                    logger.warning(f"无法切换到默认分支 {default_branch}，尝试创建并跟踪它")
                    track_result = subprocess.run(
                        ["git", "checkout", "-b", default_branch, f"origin/{default_branch}"], 
                        capture_output=True, 
                        text=True, 
                        check=False
                    )
                    
                    if track_result.returncode != 0:
                        logger.warning(f"无法跟踪远程默认分支: {track_result.stderr}")
                        logger.info("将使用当前分支作为基础")
                    else:
                        logger.info(f"成功切换到默认分支 {default_branch}")
                        base_branch = default_branch
                else:
                    logger.info(f"成功切换到默认分支 {default_branch}")
                    base_branch = default_branch
                
                # 更新远程代码
                logger.info("尝试拉取最新代码")
                pull_result = subprocess.run(
                    ["git", "pull"], 
                    capture_output=True, 
                    text=True, 
                    check=False
                )
                
                if pull_result.returncode != 0:
                    logger.warning(f"拉取最新代码失败: {pull_result.stderr}")
                    
                    # 设置上游分支
                    upstream_result = subprocess.run(
                        ["git", "branch", "--set-upstream-to", f"origin/{base_branch}", base_branch], 
                        capture_output=True, 
                        text=True, 
                        check=False
                    )
                    
                    if upstream_result.returncode != 0:
                        logger.warning(f"设置上游分支失败: {upstream_result.stderr}")
                    else:
                        logger.info(f"成功设置上游分支到 origin/{base_branch}")
                        
                        # 再次尝试拉取
                        pull_again_result = subprocess.run(
                            ["git", "pull"], 
                            capture_output=True, 
                            text=True, 
                            check=False
                        )
                        
                        if pull_again_result.returncode != 0:
                            logger.warning(f"第二次拉取仍然失败: {pull_again_result.stderr}")
                        else:
                            logger.info("成功拉取最新代码")
                else:
                    logger.info("成功拉取最新代码")
        except Exception as e:
            logger.warning(f"检查远程仓库失败: {str(e)}")
            logger.info("将使用当前分支作为基础，不进行更新")
        
        # 创建并切换到新分支
        logger.info(f"尝试创建新分支: {branch_name}")
        result = subprocess.run(["git", "checkout", "-b", branch_name], capture_output=True, text=True, check=False)
        
        # 检查分支创建是否成功
        if result.returncode != 0:
            logger.error(f"创建分支失败，错误码: {result.returncode}")
            logger.error(f"标准输出: {result.stdout}")
            logger.error(f"错误输出: {result.stderr}")
            
            # 检查分支是否已存在
            if "already exists" in result.stderr:
                logger.info(f"分支 {branch_name} 已存在，尝试切换到该分支")
                switch_result = subprocess.run(
                    ["git", "checkout", branch_name], 
                    capture_output=True, 
                    text=True, 
                    check=False
                )
                
                if switch_result.returncode != 0:
                    logger.error(f"切换到已存在的分支失败: {switch_result.stderr}")
                    raise ValueError(f"无法切换到已存在的分支 {branch_name}: {switch_result.stderr}")
                
                logger.info(f"成功切换到已存在的分支: {branch_name}")
                
                # 重置分支到基础分支
                logger.info(f"尝试将分支 {branch_name} 重置到 {base_branch}")
                reset_result = subprocess.run(
                    ["git", "reset", "--hard", base_branch], 
                    capture_output=True, 
                    text=True, 
                    check=False
                )
                
                if reset_result.returncode != 0:
                    logger.warning(f"重置分支失败: {reset_result.stderr}")
                else:
                    logger.info("成功重置分支")
            else:
                raise ValueError(f"创建分支失败: 返回码={result.returncode}, 错误={result.stderr}")
        else:        
            logger.info(f"成功创建分支: {branch_name}")
    
    except subprocess.CalledProcessError as e:
        logger.error(f"创建分支失败: 命令={e.cmd}, 返回码={e.returncode}")
        logger.error(f"标准输出: {e.stdout if hasattr(e, 'stdout') else 'N/A'}")
        logger.error(f"错误输出: {e.stderr if hasattr(e, 'stderr') else 'N/A'}")
        raise ValueError(f"创建分支失败: {e.stderr if hasattr(e, 'stderr') else str(e)}")
    except Exception as e:
        logger.error(f"创建分支发生未知错误: {str(e)}")
        logger.exception("详细异常信息:")
        raise ValueError(f"创建分支失败: {str(e)}")

def commit_changes(commit_message: str) -> None:
    """提交所有修改"""
    try:
        # 检查是否有修改可提交
        status_result = subprocess.run(
            ["git", "status", "--porcelain"], 
            capture_output=True, 
            text=True, 
            check=True
        )
        
        if not status_result.stdout.strip():
            logger.warning("没有发现需要提交的修改")
            logger.info("尝试强制创建一个空提交")
            # 创建空提交
            subprocess.run(
                ["git", "commit", "--allow-empty", "-m", commit_message], 
                capture_output=True,
                text=True,
                check=True
            )
            logger.info("成功创建空提交")
            return
        
        # 添加所有修改
        logger.info("添加所有修改到暂存区")
        add_result = subprocess.run(
            ["git", "add", "."], 
            capture_output=True, 
            text=True, 
            check=False
        )
        
        if add_result.returncode != 0:
            logger.error(f"添加修改失败: {add_result.stderr}")
            raise ValueError(f"添加修改失败: {add_result.stderr}")
        
        # 创建提交
        logger.info("创建提交")
        commit_result = subprocess.run(
            ["git", "commit", "-m", commit_message], 
            capture_output=True,
            text=True,
            check=False
        )
        
        if commit_result.returncode != 0:
            logger.error(f"提交失败: {commit_result.stderr}")
            raise ValueError(f"提交失败: {commit_result.stderr}")
            
        logger.info("成功提交所有修改")
    
    except subprocess.CalledProcessError as e:
        logger.error(f"提交修改失败: 命令={e.cmd}, 返回码={e.returncode}")
        logger.error(f"标准输出: {e.stdout if hasattr(e, 'stdout') else 'N/A'}")
        logger.error(f"错误输出: {e.stderr if hasattr(e, 'stderr') else 'N/A'}")
        raise ValueError(f"提交修改失败: {e.stderr if hasattr(e, 'stderr') else str(e)}")
    except Exception as e:
        logger.error(f"提交修改时发生未知错误: {str(e)}")
        logger.exception("详细异常信息:")
        raise ValueError(f"提交修改失败: {str(e)}")

def push_branch(branch_name: str) -> None:
    """推送分支到远程仓库"""
    try:
        logger.info(f"推送分支 {branch_name} 到远程仓库")
        push_result = subprocess.run(
            ["git", "push", "--set-upstream", "origin", branch_name], 
            capture_output=True,
            text=True,
            check=False
        )
        
        if push_result.returncode != 0:
            logger.error(f"推送分支失败: {push_result.stderr}")
            
            # 检查常见问题
            if "unable to access" in push_result.stderr or "could not resolve host" in push_result.stderr:
                logger.error("网络连接问题或无法访问远程仓库")
                raise ValueError("无法连接到远程仓库，请检查网络连接和仓库配置")
            elif "Permission denied" in push_result.stderr:
                logger.error("权限被拒绝，可能是SSH密钥或认证问题")
                raise ValueError("无权限推送到远程仓库，请检查认证配置")
            elif "Updates were rejected" in push_result.stderr:
                logger.error("推送被拒绝，可能是因为远程分支已存在或历史冲突")
                
                # 尝试强制推送
                logger.info("尝试强制推送...")
                force_result = subprocess.run(
                    ["git", "push", "--force", "--set-upstream", "origin", branch_name], 
                    capture_output=True,
                    text=True,
                    check=False
                )
                
                if force_result.returncode != 0:
                    logger.error(f"强制推送也失败了: {force_result.stderr}")
                    raise ValueError(f"推送被远程仓库拒绝，强制推送也失败: {force_result.stderr}")
                else:
                    logger.info("强制推送成功")
                    return
            
            raise ValueError(f"推送分支失败: {push_result.stderr}")
        
        logger.info(f"成功推送分支: {branch_name}")
    
    except subprocess.CalledProcessError as e:
        logger.error(f"推送分支失败: 命令={e.cmd}, 返回码={e.returncode}")
        logger.error(f"标准输出: {e.stdout if hasattr(e, 'stdout') else 'N/A'}")
        logger.error(f"错误输出: {e.stderr if hasattr(e, 'stderr') else 'N/A'}")
        raise ValueError(f"推送分支失败: {e.stderr if hasattr(e, 'stderr') else str(e)}")
    except Exception as e:
        logger.error(f"推送分支时发生未知错误: {str(e)}")
        logger.exception("详细异常信息:")
        raise ValueError(f"推送分支失败: {str(e)}")

def create_github_pr(title: str, body: str, branch: str) -> str:
    """
    使用GitHub CLI创建PR
    
    如果没有安装GitHub CLI，会提示安装说明
    """
    try:
        # 检查是否安装了GitHub CLI
        try:
            subprocess.run(["gh", "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            logger.error("GitHub CLI未安装，无法自动创建PR")
            raise ValueError(
                "GitHub CLI未安装。请安装GitHub CLI: https://cli.github.com/"
            )
        
        # 获取默认分支
        result = subprocess.run(
            ["git", "remote", "show", "origin"], 
            capture_output=True, 
            text=True, 
            check=True
        )
        
        # 解析默认分支
        default_branch = "main"  # 默认值
        for line in result.stdout.splitlines():
            if "HEAD branch" in line:
                default_branch = line.split(":")[-1].strip()
                break
        
        # 创建PR
        result = subprocess.run(
            [
                "gh", "pr", "create",
                "--title", title,
                "--body", body,
                "--base", default_branch,
                "--head", branch
            ],
            capture_output=True,
            text=True,
            check=True
        )
        
        # 返回PR URL
        pr_url = result.stdout.strip()
        logger.info(f"成功创建PR: {pr_url}")
        return pr_url
    
    except subprocess.CalledProcessError as e:
        logger.error(f"创建PR失败: {e.stderr}")
        raise ValueError(f"创建PR失败: {e.stderr}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="自动PR创建MCP服务器")
    parser.add_argument("--transport", choices=["stdio", "sse"], default="stdio", 
                        help="传输方式，可选 stdio 或 sse")
    parser.add_argument("--port", type=int, default=8000, help="SSE 模式的端口")
    
    args = parser.parse_args()
    
    logger.info(f"启动MCP服务器 - 传输方式: {args.transport}")
    
    # 设置环境变量，用于 SSE 模式下的端口配置
    if args.transport == "sse":
        os.environ["MCP_SERVER_PORT"] = str(args.port)
        # 明确设置MCP的其他环境变量
        os.environ["MCP_SERVER_HOST"] = "0.0.0.0"
        os.environ["UVICORN_PORT"] = str(args.port)
        logger.info(f"设置SSE端口: {args.port}")
    
    # 启动MCP服务器
    mcp.run(transport=args.transport) 