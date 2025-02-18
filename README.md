# TheFinals Bot

## 简介
TheFinals 工具箱机器人，提供排名查询、世界巡回赛查询等功能。现已支持API服务器，可通过HTTP接口访问机器人功能。

## 功能特性
- 排名查询
- 世界巡回赛查询
- 玩家ID绑定
- API服务器支持
- 更多功能开发中...

## 环境要求
- Python 3.8+
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
- 配置API服务器（可选）：
  ```yaml
  server:
    api:
      enabled: true
      host: 127.0.0.1
      port: 8000
  ```

4. 运行机器人
```bash
python bot.py
```

## 使用说明
### 机器人命令
- `/rank` - 查询排名
- `/wt` - 查询世界巡回赛
- `/bind` - 绑定游戏ID
- `/help` - 查看帮助


API接口说明请参考 `docs/api.md`。

## 开发说明
请参考 `docs` 目录下的开发文档：
- `bot.md` - 机器人核心功能
- `plugin.md` - 插件系统说明
- `api.md` - API接口说明
- `message_api.md` - 消息API说明
- `extension_guide.md` - 扩展开发指南
