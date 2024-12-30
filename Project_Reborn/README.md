# Reborn Bot

[![Game](https://img.shields.io/badge/Game-THE%20FINALS-e6323c.svg)](https://www.reachthefinals.com/)
[![Platform](https://img.shields.io/badge/Platform-Steam-1b2838.svg)](https://store.steampowered.com/app/2073850/THE_FINALS/)
[![Bot Version](https://img.shields.io/badge/Bot-v1.0.0-e6323c.svg)](https://github.com/your-repo/releases)
[![Status](https://img.shields.io/badge/Status-Beta-ff6b6b.svg)](https://github.com/your-repo/releases)
[![Language](https://img.shields.io/badge/Language-ZH-1b2838.svg)](https://qun.qq.com/)


THE FINALS 游戏数据查询机器人，提供排名查询、比赛数据统计等功能。THE FINALS 是一款由 Embark Studios 开发的免费多人第一人称射击游戏，具有独特的环境破坏系统和团队竞技玩法。


| 快速导航 | 链接 |
|----------|------|
| 🎮 功能模块 | [机器人核心](docs/bot.md) • [消息API](docs/message_api.md) • [扩展开发](docs/extension_guide.md) |
| 📖 项目文档 | [配置说明](docs/config.md) • [绑定系统](docs/bind.md) • [关于信息](docs/about.md) |
| ⚙️ 配置指南 | [环境变量](docs/config.md#环境变量) • [消息API配置](docs/message_api.md#配置说明-️) |
| 💻 开发指南 | [新功能开发](docs/extension_guide.md#-添加新功能) • [代码规范](docs/extension_guide.md#-文档规范) • [提交规范](docs/extension_guide.md#-提交规范) |


## 功能特性 🌟

### 排名查询

> 命令：`/rank`, `/r`

- 查询 THE FINALS 玩家排位信息和排行榜数据
- 支持多种排行榜类型（个人、团队、赛季）

### 世界巡回赛信息

> 命令：`/wt`

- 获取 THE FINALS 最新的世界巡回赛赛程
- 查看职业比赛结果和选手数据

### 游戏ID绑定

> 命令：`/bind`

- 绑定 THE FINALS 游戏账号与QQ账号
- 便捷查询个人数据和战绩

### 关于信息

> 命令：`/about`

- 查看机器人版本和功能说明
- 获取使用帮助

### 调试功能

> 命令：`/test`

- 仅在开发环境可用
- 用于功能测试和问题排查

## 环境要求 ⚙️

- Python 3.8+
- QQ机器人应用ID和密钥
- 阿里云OSS账号（用于图片存储）

## 安装 🚀

1. 克隆仓库
```bash
git clone [repository-url]
cd Project_Reborn
```

2. 安装依赖
```bash
pip install -r requirements.txt
```

3. 配置环境变量
创建 `.env` 文件并配置以下变量：
```env
BOT_APPID=你的机器人AppID
BOT_SECRET=你的机器人Secret
BOT_SANDBOX=false  # 是否使用沙箱环境
DEBUG_TEST_REPLY=false  # 是否启用测试回复
```

4. 配置消息API
在 `config.yaml` 中设置以下参数：
```yaml
message_api:
  max_retry: 3        # 最大重试次数
  retry_delay: 1.0    # 重试延迟（秒）
  rate_limit: 1.0     # 频率限制（秒）
  queue_size: 100     # 队列大小限制
```
