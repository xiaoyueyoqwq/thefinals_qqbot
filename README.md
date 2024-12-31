# TheFinals Bot

## 简介
TheFinals 工具箱机器人，提供排名查询、世界巡回赛查询等功能。

## 功能特性
- 排名查询
- 世界巡回赛查询
- 玩家ID绑定
- 更多功能开发中...

## 环境要求
- Python 3.10+
- QQ机器人开发者账号
- 稳定的网络环境

## 安装部署
1. 克隆仓库
```bash
git clone https://github.com/your-username/thefinals-bot.git
cd thefinals-bot
```

2. 安装依赖
```bash
pip install -r requirements.txt
```

3. 配置机器人
- 复制 `config.yaml.example` 为 `config.yaml`
- 填写机器人配置信息

4. 运行机器人
```bash
python bot.py
```

## 使用说明
- `/rank` - 查询排名
- `/wt` - 查询世界巡回赛
- `/bind` - 绑定游戏ID
- `/lock` - 保护游戏ID
- `/help` - 查看帮助

## 开发说明
请参考 `docs` 目录下的开发文档：
- `bot.md` - 机器人核心功能
- `plugin.md` - 插件系统说明
- `message_api.md` - 消息API说明
- `extension_guide.md` - 扩展开发指南

## 许可协议
本项目采用 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/deed.zh) 协议开源。

您可以自由地：
- 共享 — 在任何媒介以任何形式复制、发行本作品
- 演绎 — 修改、转换或以本作品为基础进行创作

惟须遵守下列条件：
- 署名 — 您必须给出适当的署名，提供指向本许可协议的链接
- 非商业性使用 — 您不得将本作品用于商业目的
- 相同方式共享 — 您必须基于与原先许可协议相同的许可协议分发您贡献的作品

详细信息请查看 [LICENSE](LICENSE) 文件。
