# 自动PR功能使用示例

本文档提供了使用Cursor MCP自动PR功能的详细示例。

## 示例场景

假设你正在使用Cursor开发一个项目，需要进行以下更改：
1. 修复了一个Bug
2. 添加了一个新功能
3. 更新了文档

你希望将这些更改一次性提交到GitHub，并创建一个Pull Request。

在Cursor中，当你与AI对话并希望创建PR时，可以这样描述：

```
请帮我创建一个PR，将我刚才的更改提交到GitHub。
```

AI会调用MCP工具，并自动填写（先自动调用
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
git --no-pager diff | Out-File -FilePath changes.txt -Encoding utf8
获取更改 然后看
）需要填写的信息：

比如：我已经阅读完了更改，生成如下：

```
PR标题: Fix bug in login feature and add user profile page
分支名: feature/user-profile
变更内容:
- Fixed login authentication bug
- Added user profile page with edit functionality
- Updated documentation for new features
```

```
正在调用MCP创建PR...请稍候...
```

MCP服务器会执行以下操作：
1. 创建`feature/user-profile`分支
2. 将所有更改添加到Git暂存区
3. 使用提供的标题和描述创建提交
4. 将分支推送到GitHub
5. 创建Pull Request

## 步骤4：查看结果

完成后，AI会向你展示PR结果：

```
✅ PR创建成功！

📌 PR标题: Fix bug in login feature and add user profile page

📄 PR描述:
## What's Changed
- Fixed login authentication bug
- Added user profile page with edit functionality
- Updated documentation for new features

🔗 PR链接: https://github.com/username/repo/pull/123
```

## 常见问题排解

### 如果工具调用失败

如果看到错误信息，可能需要检查：

1. MCP服务器是否正在运行
2. GitHub CLI是否已安装并登录
3. 你的更改是否已保存

例如，如果GitHub CLI未安装，你会看到：

```
错误: GitHub CLI未安装。请安装GitHub CLI: https://cli.github.com/
```

### 自定义PR模板

如果你想使用自定义PR模板，可以在描述中直接使用Markdown格式：

```
PR标题: Add new API endpoints
分支名: feature/new-api
变更内容:
## Features
- Added user authentication API
- Added data export API

## Testing
All endpoints have been tested with Postman.

## Documentation
API documentation has been updated in `/docs/api.md`.
```

## 使用提示

1. 确保在创建PR前保存所有文件更改
2. 提供清晰、描述性的PR标题和内容
3. 使用英文编写PR标题和描述，以符合大多数项目的国际化标准
4. 分支名称应遵循项目的命名约定，通常使用`feature/`、`bugfix/`、`hotfix/`等前缀 