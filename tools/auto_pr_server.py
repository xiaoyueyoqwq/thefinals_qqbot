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
import time
from typing import Dict, Any, List, Optional, Tuple
from mcp.server.fastmcp import FastMCP

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/auto_pr_server.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("auto_pr_server")

# 确保日志目录存在
os.makedirs("logs", exist_ok=True)

# 初始化MCP服务器
mcp = FastMCP("auto_pr")

def run_command(
    cmd: List[str], 
    check: bool = False, 
    timeout: Optional[int] = None,
    silent: bool = False
) -> Tuple[int, str, str]:
    """
    运行命令并返回结果
    
    Args:
        cmd: 命令列表
        check: 是否在命令失败时抛出异常
        timeout: 超时时间（秒）
        silent: 是否不记录日志
        
    Returns:
        (返回码, 标准输出, 错误输出)
    """
    if not silent:
        logger.info(f"执行命令: {' '.join(cmd)}")
    
    try:
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8"
        )
        
        stdout, stderr = process.communicate(timeout=timeout)
        returncode = process.returncode
        
        if returncode != 0 and not silent:
            logger.warning(f"命令返回非零值: {returncode}")
            logger.warning(f"错误输出: {stderr.strip()}")
            
        if check and returncode != 0:
            raise subprocess.CalledProcessError(returncode, cmd, stdout, stderr)
            
        return returncode, stdout.strip(), stderr.strip()
    
    except subprocess.TimeoutExpired:
        process.kill()
        if not silent:
            logger.error(f"命令执行超时: {' '.join(cmd)}")
        return 1, "", "命令执行超时"
    
    except Exception as e:
        if not silent:
            logger.error(f"执行命令时出错: {str(e)}")
        return 1, "", str(e)

def get_current_branch() -> str:
    """获取当前分支名称"""
    returncode, stdout, stderr = run_command(
        ["git", "branch", "--show-current"],
        silent=True
    )
    
    if returncode != 0:
        logger.warning(f"无法获取当前分支: {stderr}")
        return "unknown"
    
    return stdout.strip()

def get_default_branch() -> str:
    """
    获取默认分支名称
    尝试多种方式确定默认分支，同时兼容main和master
    """
    # 方法1: 从远程仓库信息中获取
    returncode, stdout, stderr = run_command(
        ["git", "remote", "show", "origin"],
        silent=True
    )
    
    if returncode == 0:
        for line in stdout.splitlines():
            if "HEAD branch" in line:
                branch = line.split(":")[-1].strip()
                logger.info(f"从远程仓库信息中发现默认分支: {branch}")
                return branch
    
    # 方法2: 检查本地main或master分支
    returncode, stdout, stderr = run_command(
        ["git", "branch"],
        silent=True
    )
    
    if returncode == 0:
        branches = [b.strip() for b in stdout.splitlines()]
        branches = [b[2:] if b.startswith('* ') else b for b in branches]
        
        # 优先使用main分支，其次master
        if "main" in branches:
            logger.info("使用main作为默认分支")
            return "main"
        elif "master" in branches:
            logger.info("使用master作为默认分支")
            return "master"
    
    # 方法3: 尝试获取远程默认分支
    candidates = ["main", "master"]
    for branch in candidates:
        returncode, stdout, stderr = run_command(
            ["git", "ls-remote", "--exit-code", "origin", branch],
            silent=True
        )
        
        if returncode == 0:
            logger.info(f"发现远程默认分支: {branch}")
            return branch
    
    # 回退到最常见的默认值
    logger.warning("无法确定默认分支，使用master作为默认")
    return "master"

def create_branch(branch_name: str) -> str:
    """
    创建Git分支
    
    如果成功，返回空字符串；如果失败，返回错误消息
    """
    try:
        # 获取当前分支
        current_branch = get_current_branch()
        logger.info(f"当前分支: {current_branch}")
        
        # 获取默认分支
        default_branch = get_default_branch()
        logger.info(f"默认分支: {default_branch}")
        
        # 检查远程仓库配置
        returncode, stdout, stderr = run_command(
            ["git", "remote", "-v"],
            silent=True
        )
        
        if returncode != 0 or not stdout.strip():
            logger.warning("未检测到远程仓库配置")
        else:
            logger.info(f"远程仓库配置: \n{stdout}")
            
            # 尝试检出默认分支
            logger.info(f"尝试切换到默认分支: {default_branch}")
            returncode, stdout, stderr = run_command(
                ["git", "checkout", default_branch]
            )
            
            if returncode != 0:
                logger.warning(f"无法直接切换到默认分支，尝试从远程检出")
                
                # 尝试从远程检出
                returncode, stdout, stderr = run_command(
                    ["git", "checkout", "-b", default_branch, f"origin/{default_branch}"]
                )
                
                if returncode != 0:
                    logger.warning(f"无法从远程检出默认分支: {stderr}")
                    
                    # 如果既不能切换也不能检出，返回到原始分支
                    if current_branch != "unknown":
                        returncode, stdout, stderr = run_command(
                            ["git", "checkout", current_branch]
                        )
                        logger.info(f"返回到原始分支: {current_branch}")
                else:
                    logger.info(f"成功从远程检出默认分支: {default_branch}")
            else:
                logger.info(f"成功切换到默认分支: {default_branch}")
                
                # 尝试拉取最新代码
                logger.info("尝试拉取最新代码")
                returncode, stdout, stderr = run_command(
                    ["git", "pull"]
                )
                
                if returncode != 0:
                    logger.warning(f"拉取代码失败: {stderr}")
                    
                    # 尝试设置上游分支
                    logger.info(f"尝试设置上游分支为 origin/{default_branch}")
                    returncode, stdout, stderr = run_command(
                        ["git", "branch", "--set-upstream-to", f"origin/{default_branch}"]
                    )
                    
                    if returncode == 0:
                        logger.info("成功设置上游分支，再次尝试拉取")
                        returncode, stdout, stderr = run_command(
                            ["git", "pull"]
                        )
                        
                        if returncode != 0:
                            logger.warning(f"再次拉取仍然失败: {stderr}")
                else:
                    logger.info("成功拉取最新代码")
        
        # 现在从当前分支(可能是默认分支或原始分支)创建新分支
        logger.info(f"创建新分支: {branch_name}")
        returncode, stdout, stderr = run_command(
            ["git", "checkout", "-b", branch_name]
        )
        
        if returncode != 0:
            # 检查分支是否已存在
            if "already exists" in stderr:
                logger.info(f"分支 {branch_name} 已存在，尝试切换")
                
                returncode, stdout, stderr = run_command(
                    ["git", "checkout", branch_name]
                )
                
                if returncode != 0:
                    return f"无法切换到已存在的分支 {branch_name}: {stderr}"
                
                logger.info(f"已切换到已存在的分支: {branch_name}")
                
                # 尝试重置到默认分支
                logger.info(f"尝试将分支重置到 {default_branch}")
                returncode, stdout, stderr = run_command(
                    ["git", "reset", "--hard", default_branch]
                )
                
                if returncode != 0:
                    logger.warning(f"重置分支失败: {stderr}")
                    # 继续使用，不返回错误
                else:
                    logger.info(f"成功重置分支到 {default_branch}")
            else:
                return f"创建分支失败: {stderr}"
        
        logger.info(f"已成功切换到分支: {branch_name}")
        return ""
    
    except Exception as e:
        logger.error(f"创建分支过程中发生异常: {str(e)}")
        logger.exception("详细异常信息:")
        return f"创建分支过程中发生错误: {str(e)}"

def commit_changes(commit_message: str) -> str:
    """
    提交所有修改
    
    如果成功，返回空字符串；如果失败，返回错误消息
    """
    try:
        # 检查是否有修改
        returncode, stdout, stderr = run_command(
            ["git", "status", "--porcelain"]
        )
        
        if returncode != 0:
            return f"获取文件状态失败: {stderr}"
        
        # 如果没有修改，创建空提交
        if not stdout.strip():
            logger.warning("没有发现需要提交的修改，将创建空提交")
            returncode, stdout, stderr = run_command(
                ["git", "commit", "--allow-empty", "-m", commit_message]
            )
            
            if returncode != 0:
                return f"创建空提交失败: {stderr}"
                
            logger.info("成功创建空提交")
            return ""
        
        # 添加所有修改
        logger.info("添加所有修改到暂存区")
        returncode, stdout, stderr = run_command(
            ["git", "add", "."]
        )
        
        if returncode != 0:
            return f"添加修改失败: {stderr}"
        
        # 创建提交
        logger.info("创建提交")
        returncode, stdout, stderr = run_command(
            ["git", "commit", "-m", commit_message]
        )
        
        if returncode != 0:
            return f"提交修改失败: {stderr}"
        
        logger.info("成功提交所有修改")
        return ""
    
    except Exception as e:
        logger.error(f"提交修改过程中发生异常: {str(e)}")
        logger.exception("详细异常信息:")
        return f"提交修改过程中发生错误: {str(e)}"

def push_branch(branch_name: str) -> str:
    """
    推送分支到远程仓库
    
    如果成功，返回空字符串；如果失败，返回错误消息
    """
    try:
        logger.info(f"推送分支 {branch_name} 到远程仓库")
        returncode, stdout, stderr = run_command(
            ["git", "push", "--set-upstream", "origin", branch_name],
            timeout=60  # 设置60秒超时
        )
        
        if returncode != 0:
            # 检查常见问题
            if "unable to access" in stderr or "could not resolve host" in stderr:
                logger.error("网络连接问题或无法访问远程仓库")
                return "无法连接到远程仓库，请检查网络连接和仓库配置"
                
            elif "Permission denied" in stderr:
                logger.error("权限被拒绝，可能是SSH密钥或认证问题")
                return "无权限推送到远程仓库，请检查认证配置"
                
            elif "Updates were rejected" in stderr:
                logger.warning("推送被拒绝，可能因为远程分支已存在或历史冲突")
                
                # 尝试强制推送
                logger.info("尝试强制推送")
                returncode, stdout, stderr = run_command(
                    ["git", "push", "--force", "--set-upstream", "origin", branch_name],
                    timeout=60
                )
                
                if returncode != 0:
                    logger.error(f"强制推送也失败了: {stderr}")
                    return f"推送被远程仓库拒绝，强制推送也失败: {stderr}"
                    
                logger.info("强制推送成功")
                return ""
            
            return f"推送分支失败: {stderr}"
        
        logger.info(f"成功推送分支: {branch_name}")
        return ""
    
    except Exception as e:
        logger.error(f"推送分支过程中发生异常: {str(e)}")
        logger.exception("详细异常信息:")
        return f"推送分支过程中发生错误: {str(e)}"

def create_github_pr(title: str, body: str, branch: str) -> str:
    """
    使用GitHub CLI创建PR
    
    返回PR URL或错误信息
    """
    try:
        # 检查GitHub CLI
        returncode, stdout, stderr = run_command(
            ["gh", "--version"],
            silent=True
        )
        
        if returncode != 0:
            logger.error("GitHub CLI未安装或无法运行")
            return f"无法使用GitHub CLI创建PR，但分支 {branch} 已成功创建并推送。请手动创建PR: 标题 '{title}'"
        
        # 检查登录状态
        returncode, stdout, stderr = run_command(
            ["gh", "auth", "status"],
            silent=True
        )
        
        if returncode != 0:
            logger.error(f"GitHub认证状态检查失败: {stderr}")
            return f"GitHub认证失败，但分支 {branch} 已成功创建并推送。请运行 'gh auth login' 后手动创建PR。"
        
        # 获取默认分支
        default_branch = get_default_branch()
        logger.info(f"将创建PR: {branch} -> {default_branch}")
        
        # 创建PR
        logger.info(f"执行创建PR命令")
        try:
            # 使用更长的超时时间
            returncode, stdout, stderr = run_command(
                [
                    "gh", "pr", "create",
                    "--title", title,
                    "--body", body,
                    "--base", default_branch,
                    "--head", branch
                ],
                timeout=60
            )
            
            if returncode != 0:
                logger.error(f"创建PR失败: {stderr}")
                
                # 检查是否已存在PR
                if "already exists" in stderr or "failed to create" in stderr:
                    logger.info(f"可能PR已存在，检查分支 {branch} 的PR")
                    returncode, stdout, stderr = run_command(
                        ["gh", "pr", "list", "--head", branch, "--json", "url", "--jq", ".[0].url"],
                        silent=True
                    )
                    
                    if returncode == 0 and stdout.strip():
                        logger.info(f"找到已存在的PR: {stdout}")
                        return stdout.strip()
                
                # 如果是网络问题，返回更友好的消息
                if "timeout" in stderr or "connection" in stderr or "unable to resolve" in stderr:
                    return f"网络连接问题导致PR创建失败，但分支 {branch} 已成功创建并推送。请稍后手动创建PR。"
                
                return f"无法创建PR: {stderr}，但分支 {branch} 已成功创建并推送。请手动创建PR。"
            
            # 成功获取PR URL
            pr_url = stdout.strip()
            logger.info(f"成功创建PR: {pr_url}")
            return pr_url
            
        except Exception as e:
            logger.error(f"执行gh pr create命令过程中发生异常: {str(e)}")
            return f"创建PR过程中发生错误，但分支 {branch} 已成功创建并推送。请手动创建PR。"
    
    except Exception as e:
        logger.error(f"创建PR过程中发生异常: {str(e)}")
        logger.exception("详细异常信息:")
        return f"创建PR过程中发生错误，但分支 {branch} 可能已创建。错误: {str(e)}"

@mcp.tool()
async def create_pr(title: str, branch: str, changes: str) -> Dict[str, Any]:
    """创建PR并提交更改
    
    Args:
        title: PR标题（英文）
        branch: 目标分支名称
        changes: 变更内容描述（英文）
    """
    logger.info(f"开始创建PR: {title}, 分支: {branch}")
    result = {
        "title": title,
        "branch": branch,
        "changes": changes,
        "steps": []
    }
    
    try:
        # 获取仓库状态
        returncode, stdout, stderr = run_command(
            ["git", "status"],
            silent=True
        )
        result["steps"].append({
            "step": "检查仓库状态",
            "status": "completed" if returncode == 0 else "failed",
            "details": stdout if returncode == 0 else stderr
        })
        logger.info(f"仓库状态: \n{stdout if returncode == 0 else stderr}")
        
        # 1. 创建新分支
        logger.info("步骤1: 创建新分支")
        error = create_branch(branch)
        result["steps"].append({
            "step": "创建分支",
            "status": "completed" if not error else "failed",
            "details": "成功创建分支" if not error else error
        })
        
        if error:
            result["status"] = "failed"
            result["error"] = error
            return result
        
        # 2. 提交更改
        logger.info("步骤2: 提交更改")
        commit_message = f"{title}\n\n## What's Changed\n{changes}"
        error = commit_changes(commit_message)
        result["steps"].append({
            "step": "提交更改",
            "status": "completed" if not error else "failed",
            "details": "成功提交更改" if not error else error
        })
        
        if error:
            result["status"] = "failed"
            result["error"] = error
            return result
        
        # 3. 推送分支
        logger.info("步骤3: 推送分支")
        error = push_branch(branch)
        result["steps"].append({
            "step": "推送分支",
            "status": "completed" if not error else "failed",
            "details": "成功推送分支" if not error else error
        })
        
        if error:
            result["status"] = "partial_success"
            result["message"] = f"创建了本地分支和提交，但推送失败: {error}"
            return result
        
        # 4. 创建PR
        logger.info("步骤4: 创建PR")
        pr_result = create_github_pr(title, f"## What's Changed\n{changes}", branch)
        
        # 判断PR创建是否成功
        is_url = "http" in pr_result.lower()
        result["steps"].append({
            "step": "创建PR",
            "status": "completed" if is_url else "failed",
            "details": pr_result
        })
        
        if is_url:
            result["status"] = "success"
            result["pr_url"] = pr_result
            result["message"] = f"成功创建PR: {pr_result}"
        else:
            result["status"] = "partial_success"
            result["message"] = pr_result
        
        return result
        
    except Exception as e:
        logger.error(f"创建PR过程中发生异常: {str(e)}")
        logger.exception("详细异常信息:")
        
        # 尝试回退到默认分支
        try:
            default_branch = get_default_branch()
            current_branch = get_current_branch()
            
            if current_branch == branch:
                logger.info(f"尝试回退到默认分支: {default_branch}")
                run_command(["git", "checkout", default_branch], silent=True)
        except:
            pass
        
        result["status"] = "error"
        result["error"] = str(e)
        result["message"] = f"创建PR过程中发生错误: {str(e)}"
        return result

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