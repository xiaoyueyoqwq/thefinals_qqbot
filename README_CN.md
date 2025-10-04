# THE FINALS 机器人

[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=flat-square&logo=docker&logoColor=white)](https://github.com/xiaoyueyoqwq/thefinals_qqbot)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-059669?style=flat-square&logoColor=white)](https://creativecommons.org/licenses/by-nc-sa/4.0/)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/xiaoyueyoqwq/thefinals_qqbot)
[![English Docs](https://img.shields.io/badge/Docs-English-059669?style=flat-square)](./README.md)

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

机器人提供全面的多模式玩家数据查询功能。通过 `/rank` 和 `/r` 命令访问实时排名统计，使用 `/wt` 探索世界巡回赛数据，通过专用命令追踪快速提现、平台争霸和死亡竞赛的竞技表现。系统支持 `/ds` 进行玩家模糊搜索，提供账号绑定功能以简化查询流程，并能动态生成排行榜趋势可视化图表。

武器数据通过 `/weapon` 命令访问，提供详细的伤害数值、射速、击杀时间计算和技术规格。俱乐部信息可通过 `/club` 标签查询，而 `/df` 命令则提供当前赛季的竞技排名分数线。账号管理功能包括 `/bind` 绑定游戏 ID 和 `/unbind` 解除绑定，绑定后可在所有玩家数据命令中省略 ID 参数。

## 系统架构

基于插件化架构和多平台提供者抽象层构建，机器人无缝运行于 QQ、小黑盒和开黑啦平台。核心基础设施利用 Redis 实现高性能数据缓存，通过 Playwright 生成动态图片，并使用 FastAPI 提供 RESTful API 端点。命令处理管道通过结构化的事件驱动系统处理解析、验证和执行流程。

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

