# 自动PR功能使用指南

Cursor的MCP（Model Context Protocol）提供了一种标准化的方式，使AI模型能够访问和操作外部工具。本项目实现了基于MCP的自动PR创建功能，让AI模型能够直接创建GitHub Pull Request。

## 功能概述

自动PR功能允许AI模型：

1. 创建新的Git分支
2. 提交所有更改
3. 将分支推送到远程仓库
4. 创建Pull Request

整个过程完全自动化，无需手动操作Git命令。

## 设置步骤

### 前提条件

- 安装[GitHub CLI](https://cli.github.com/)
- 已配置Git仓库（与GitHub关联）
- 已安装Python 3.7+

### 安装步骤

1. 安装依赖（如果尚未安装）：

```bash
pip install fastapi uvicorn[standard] requests
```

2. 安装GitHub CLI并登录：

```bash
# 安装GitHub CLI（根据官方文档）
# 登录GitHub
gh auth login
```

3. 确认项目已设置GitHub远程仓库：

```bash
git remote -v
# 应该看到类似 origin https://github.com/username/repo.git 的输出
```

4. 运行设置工具，配置自动启动：

```bash
python tools/setup_auto_pr.py
```

设置工具会：
- 配置MCP代理
- 设置系统自启动
- 立即启动代理服务器

## 使用方法

### 全自动模式（推荐）

安装完成后，你只需在Cursor中与AI对话，当需要创建PR时，直接告诉AI你想创建PR即可。无需手动启动任何服务器。

例如：
```
请帮我创建一个PR，提交我的更改
```

AI会引导你提供必要的信息，然后自动处理剩下的一切。

### 手动启动模式（备选）

如果你不想使用自动启动功能，也可以手动启动MCP服务器：

```bash
python tools/start_auto_pr_server.py
```

服务器将在`http://localhost:3000/mcp`运行，准备接收来自Cursor的请求。

## 工作原理

### 自动启动机制

该功能通过三层结构实现：

1. **MCP配置文件** (`.cursor/mcp.json`)：定义工具接口并指向代理服务器
2. **代理服务器** (`tools/auto_pr_proxy.py`)：按需启动实际的MCP服务器
3. **MCP服务器** (`tools/auto_pr_server.py`)：执行Git操作和PR创建

当AI尝试调用MCP工具时：
1. 请求首先发送到代理服务器
2. 代理检查MCP服务器是否运行，如果没有则启动它
3. 代理转发请求到MCP服务器
4. MCP服务器处理请求并返回结果

### 系统自启动

设置工具会将代理服务器添加到系统自启动项，确保电脑重启后代理仍然可用。支持：
- Windows（通过注册表）
- macOS（通过LaunchAgents）
- Linux（通过systemd用户服务）

## 配置文件

MCP配置文件位于`.cursor/mcp.json`，定义了自动PR工具的接口。默认指向代理服务器：

```json
{
  "version": "1.0",
  "servers": [
    {
      "name": "Auto PR Server",
      "description": "自动创建PR的MCP服务器",
      "url": "http://localhost:3333/mcp",
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
```

## 故障排除

- **服务器无法启动**：检查依赖是否正确安装，端口3333或3000是否被占用
- **无法创建PR**：确认已安装GitHub CLI并完成登录
- **分支推送失败**：检查远程仓库配置和权限
- **找不到工具**：确认`.cursor/mcp.json`配置正确，代理服务器是否运行

### 日志文件

如果遇到问题，可以查看日志文件：
- 代理服务器日志：`logs/auto_pr_proxy.log`
- MCP服务器日志：`logs/auto_pr_server.log`

### 手动重启服务

如果需要手动重启服务：

```bash
# 找到并终止现有进程
taskkill /F /IM python.exe /FI "WINDOWTITLE eq auto_pr_proxy*"  # Windows
pkill -f "auto_pr_proxy.py" # Linux/macOS

# 重新启动代理
python tools/auto_pr_proxy.py --background
```

## 高级用法

### 自定义端口

如果默认端口（3333/3000）被占用，可以修改：

1. 编辑`tools/auto_pr_proxy.py`中的`proxy_port`值
2. 编辑`tools/auto_pr_server.py`启动参数中的端口号
3. 重新运行设置工具：`python tools/setup_auto_pr.py`

### 安全考虑

- 请确保在受信任的环境中运行MCP服务器
- 服务器默认只在本地运行，如需在网络中共享，请添加适当的认证机制 