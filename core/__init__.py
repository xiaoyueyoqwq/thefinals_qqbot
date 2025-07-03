# -*- coding: utf-8 -*-
"""
core 包初始化。仅导出对外常用对象，方便上层引用。
"""
from .client import MyBot          # noqa: F401
from .runner import main as run    # noqa: F401
