# TheFinals Bot

## 简介
TheFinals 工具箱机器人，提供排名查询、世界巡回赛查询等功能。支持 QQ 机器人指令和 HTTP API 双重访问方式。

## 功能特性
- 排位数据查询
- 世界巡回赛数据查询
- 玩家 ID 绑定
- 当前赛季底分查询
- 神奇海螺问答
- 机器人状态监控
- HTTP API 服务
- 插件化架构

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
- 配置 API 服务器（可选）：
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
- `/rank <ID> [赛季]` - 查询排位数据
- `/wt <ID> [赛季]` - 查询世界巡回赛
- `/bind <ID>` - 绑定游戏ID
- `/df` - 查询当前赛季底分
- `/ask <问题>` - 向神奇海螺提问
- `/info` - 查看机器人状态
- `/about` - 关于我们

### API 服务
机器人提供 HTTP API 服务，可通过 API 接口访问机器人功能：

- API 文档访问：`http://127.0.0.1:8000/docs`
- 支持 RESTful API 接口
- 插件化 API 设计
- 自动生成 API 文档

详细 API 接口说明请参考 `docs/api.md`。

## 开发说明
请参考 `docs` 目录下的开发文档：
- `bot.md` - 机器人核心功能
- `plugin.md` - 插件系统说明
- `api.md` - API 接口说明
- `message_api.md` - 消息API说明
- `extension_guide.md` - 扩展开发指南

## 许可证
本项目采用 [Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License](https://creativecommons.org/licenses/by-nc-sa/4.0/deed.zh) 进行许可。