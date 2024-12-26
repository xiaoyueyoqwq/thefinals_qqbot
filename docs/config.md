# 配置文件指南 - config.yaml

👋 你好! 这是机器人的配置指南。通过修改这个文件,你可以轻松地调整机器人的各种行为。让我们一起来看看如何配置吧!

## 机器人设置 🤖

这部分是机器人的基本设置:

```yaml
bot:
  appid: "102291722"      # 机器人的身份证号
  token: "xxx"            # 机器人的通行证
  secret: "xxx"           # 机器人的密钥
  sandbox: true           # 是否在游乐场(测试环境)玩耍
```

💡 小贴士: 
- 在正式环境请将 `sandbox` 设为 `false`
- 请保管好你的 token 和 secret,它们就像钥匙一样重要!

## 图片存储设置 🖼️

机器人需要一个地方存储图片,我们使用DogeCloudOSS:

```yaml
oss:
  access_key: "xxx"           # OSS的用户名
  secret_key: "xxx"           # OSS的密码
  bucket: "thefinals"         # 存储桶名称
  bucket_url: "xxx"           # 访问地址
  image_rule: "/image"        # 图片处理规则
```

💡 小贴士:
- 确保bucket已经配置了正确的访问权限
- bucket_url 最好配置自定义域名

## 性能调优 ⚡

这些设置可以帮助你调整机器人的性能:

```yaml
    max_concurrent: 5    # 最多同时处理几个请求
    max_workers: 10      # 后台工作人员数量
    ```

💡 小贴士:
- `max_concurrent` 建议设置为 CPU核心数 * 2
- `max_workers` 建议设置为 `max_concurrent` 的2倍

## 调试选项 🔧

开发时的好帮手:

```yaml
debug:
  test_reply: true   # 是否启用测试回复
```

💡 小贴士:
- 开发时可以打开这些选项
- 生产环境建议关闭,以获得更好的性能

## 配置检查清单 ✅

在启动机器人前,请确认:

1. [ ] 所有必需的配置项都已填写
2. [ ] 敏感信息(token/secret)已正确设置
3. [ ] 环境(sandbox)设置正确
4. [ ] OSS配置可以正常访问
5. [ ] 性能参数适合你的服务器配置

## 需要帮助? 🆘

- 检查配置文件格式是否正确
- 确保YAML语法没有错误
- 有问题可以查看错误日志