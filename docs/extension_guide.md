> [!WARNING]
> 这份文档已经过期，不建议参考以下教程进行开发。
> 
> 新插件系统 [文档](/docs/plugin.md)

## 扩展开发指南

👋 欢迎来到扩展开发指南！

本指南旨在帮助开发者快速了解如何为项目添加新功能。无论你是初学者还是经验丰富的开发者，这里都包含了清晰的步骤、代码示例和最佳实践，帮助你高效扩展项目功能。

---

## 🌟 项目目录结构

以下是项目的主要目录结构及其用途说明：

```
Project_Reborn/
├── core/               # 核心功能模块（核心逻辑实现）
│   ├── rank.py        # 排位查询功能
│   ├── world_tour.py  # 世界巡回赛模块
│   ├── bind.py        # 用户ID绑定功能
│   ├── about.py       # 项目关于信息
│   └── debug.py       # 调试功能模块
├── utils/             # 工具模块（通用工具类和API）
│   ├── base_api.py    # API基类封装
│   ├── logger.py      # 日志处理工具
│   └── message_api.py # 消息API工具
├── plugins/           # 插件目录（用于扩展功能）
├── resources/         # 资源文件（静态资源和模板）
│   ├── templates/     # HTML模板文件
│   └── images/        # 图片和图标资源
├── docs/              # 项目文档
└── data/              # 数据存储
```

---

## 🔌 添加新功能

按照以下步骤添加新功能模块到项目中：

### 第一步：创建新模块

在 `core` 目录下，创建一个新的 Python 文件，例如 `core/new_feature.py`，用于实现新功能模块。

```python
# core/new_feature.py

class NewFeature:
    """
    新功能模块

    主要功能：
    - 描述功能1
    - 描述功能2
    """

    def __init__(self):
        # 初始化模块
        pass

    async def process_command(self, args: str) -> str:
        """
        处理用户命令的核心逻辑
        
        参数:
        - args (str): 用户输入的命令参数
        
        返回:
        - str: 命令处理结果
        """
        try:
            # 实现核心逻辑
            return f"处理结果: {args}"
        except Exception as e:
            # 错误处理逻辑
            return f"处理失败: {str(e)}"
```

**⚠️ 注意**：
- 确保模块中的所有方法都遵循异步编程规范（`async/await`）。
- 在模块文件顶部添加必要的依赖和导入。

---

### 第二步：注册插件

在 `bot.py` 文件中，将新功能注册到插件管理器中，确保机器人能够识别和处理新命令。

```python
def _register_plugins(self):
    # ... 现有插件 ...
    self.plugin_manager.register_plugin(
        "new",  # 新功能的命令前缀
        NewFeaturePlugin(self.config)  # 插件的实例
    )
```

---

## 📝 文档规范

开发者在撰写代码时，应遵循以下文档规范：

### **代码注释模板**

为每个类和方法添加详细的注释，示例如下：

```python
class NewFeature:
    """
    新功能模块

    功能概述:
    - 提供特定的功能A和B
    - 支持异步操作

    使用示例:
    >>> feature = NewFeature()
    >>> result = await feature.process_command("示例参数")
    >>> print(result)
    """

    async def process_command(self, args: str) -> str:
        """
        处理用户命令的核心逻辑

        参数:
        - args (str): 用户输入的命令参数

        返回:
        - str: 命令处理结果
        """
        pass
```

---

## 📋 提交规范

为了保持代码质量和文档的可维护性，请遵循以下提交规范：

### **1. 提交信息模板**

在提交代码时，请确保提交信息清晰且具有描述性，格式如下：
```
feat(core): 添加新功能模块NewFeature

描述:
- 实现了基本的命令处理逻辑
- 添加了单元测试覆盖率
- 更新了README文档

问题修复:
- 修复了bind模块中的小问题
```

### **2. 检查代码质量**

在提交之前，使用以下工具检查代码规范：
- **代码格式**：使用 `flake8` 或 `black` 检查代码风格。
- **测试覆盖率**：使用 `pytest` 测试并确保覆盖率在80%以上。

---

## 总结

通过以上优化和规范，您可以更加高效地扩展功能、提高代码质量，并为项目的长期维护提供保障。如果有任何问题，请参考上述步骤或联系相关负责人。
