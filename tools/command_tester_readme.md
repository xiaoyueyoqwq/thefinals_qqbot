# 命令测试工具

这个工具允许你在不启动QQ机器人服务的情况下测试机器人的所有命令

## 为什么要用

之前的方法是和生产环境的bot用一个机器人账号，然后来测试。这样的缺点是：

- 服务器和本地会生成两条消息
- 有可能被QQ做去重
- 如果单开的话，本地环境不如生产环境稳定

## 有哪些特点

自己看，我懒

---



## 快速启动

一键式：

```bash
python bot.py -local
```

手动：

Windows

```bash
pip install aiohttp aiohttp_cors ; python tools/command_tester.py
```

Linux用

```bash
pip install aiohttp aiohttp_cors && python tools/command_tester.py

```


2. 默认情况下，服务会在 `http://127.0.0.1:8080` 启动

3. 使用浏览器访问该地址，即可打开命令测试界面。或者如果你现在是在用ide的话可以摁住Ctrl，然后单击这个链接。

---

## 其他

支持自定义配置，比如说：

```bash
python tools/command_tester.py --host 0.0.0.0 --port 9000
```
