# -*- coding: utf-8 -*-
"""
项目主入口。只负责解析命令行、配置日志并调用 core.runner.main 。
# Copyright (c) 2025 Xiaoyueyoqwq (https://github.com/Xiaoyueyoqwq/thefinals_qqbot).
# Licensed under the CC BY-NC-SA 4.0.
"""
import argparse
from utils.logger import initialize_logging, print_banner
from utils.config import settings
from core.runner import main as run_bot


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="TheFinals QQ Bot")
    parser.add_argument(
        "-local",
        "--local",
        action="store_true",
        help="启动本地命令测试工具",
    )
    return parser.parse_args()


def main() -> None:
    print_banner()
    initialize_logging(log_level="DEBUG" if settings.DEBUG_ENABLED else "INFO")
    args = _parse_args()
    run_bot(local_mode=args.local)


if __name__ == "__main__":
    main()