# -*- coding: utf-8 -*-
"""
丰富的 Traceback 支持。若环境已安装 `rich` 则启用彩色、带局部变量的
堆栈信息；否则静默降级到默认行为。

外部只需在程序入口处调用 `install_pretty_traceback()` 一次。
"""
from __future__ import annotations

import logging

def install_pretty_traceback() -> None:
    """Try to enable rich‑traceback; safe (no‑op) if Rich is absent."""
    try:
        from rich.traceback import install as _install

        _install(
            width=120,
            extra_lines=1,
            show_locals=True,
            max_frames=100,
            suppress=[logging],  # 隐去 logging 内部调用栈
        )
    except ImportError:
        logging.getLogger(__name__).debug(
            "package 'rich' not found – using default traceback."
        ) 