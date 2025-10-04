# THE FINALS 机器人

[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=flat-square&logo=docker&logoColor=white)](https://github.com/xiaoyueyoqwq/thefinals_qqbot)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey?style=flat-square)](https://creativecommons.org/licenses/by-nc-sa/4.0/)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/xiaoyueyoqwq/thefinals_qqbot)

[English](./README.md) | **[中文]**

> [!NOTE]
> 一个功能完善的 THE FINALS 游戏数据查询机器人，支持实时玩家统计、排行榜追踪和赛事数据查询，覆盖 QQ、小黑盒和开黑啦多个平台。采用现代异步架构设计，支持容器化部署。

## 快速开始

```bash
# Docker Compose（推荐）
docker-compose up -d

# 传统 Python 部署
python bot.py
```

本文档涵盖系统架构、核心组件和功能特性。详细的安装配置信息请参阅[安装和设置](https://deepwiki.com/xiaoyueyoqwq/thefinals_qqbot/1.1-installation-and-setup)。完整的命令列表请查看[可用命令](https://deepwiki.com/xiaoyueyoqwq/thefinals_qqbot/1.2-available-commands)。

## 功能特性

### 核心功能

机器人实现了基于插件的架构和多平台提供者抽象层，支持无缝跨平台运行。核心功能包括使用 Redis 的实时数据缓存、通过 Playwright 的动态图片生成，以及涵盖排位赛、世界巡回赛、快速提现和死亡竞赛等多种游戏模式的全面玩家统计追踪。

### 命令列表

- `/rank <ID> [赛季]` - 查询排位数据
- `/all <ID>` - 查询全赛季数据
- `/wt <ID> [赛季]` - 查询世界巡回赛
- `/ps <ID>` - 查询平台争霸
- `/club <标签>` - 查询俱乐部信息
- `/bind <ID>` - 绑定游戏ID
- `/unbind <ID>` - 解绑游戏ID
- `/df` - 查询当前赛季底分
- `/ds` - 深度查询玩家ID数据
- `/ask <问题>` - 向神奇海螺提问
- `/bird` - 查看 Flappy Bird 游戏排行榜
- `/qc <ID>` - 查询快速提现数据
- `/dm <ID>` - 查询死亡竞赛数据
- `/lb <ID> [天数]` - 查询排位排行榜走势
- `/info` - 查看机器人状态
- `/about` - 关于我们

## 文档

访问我们的[完整文档](https://deepwiki.com/xiaoyueyoqwq/thefinals_qqbot/1-overview)获取部署、配置和开发的详细指南。

## 技术栈

![Python](https://img.shields.io/badge/Python-%233776AB.svg?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-%23009688.svg?style=flat-square&logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-%232496ED.svg?style=flat-square&logo=docker&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-%23DC382D.svg?style=flat-square&logo=redis&logoColor=white)
![Playwright](https://img.shields.io/badge/Playwright-%232EAD33.svg?style=flat-square&logo=playwright&logoColor=white)

## 统计数据

[![Star History Chart](https://api.star-history.com/svg?repos=xiaoyueyoqwq/thefinals_qqbot&type=Date)](https://star-history.com/#xiaoyueyoqwq/thefinals_qqbot&Date)

## 许可证

本项目采用 [知识共享署名-非商业性使用-相同方式共享 4.0 国际许可协议](https://creativecommons.org/licenses/by-nc-sa/4.0/deed.zh) 进行许可。

