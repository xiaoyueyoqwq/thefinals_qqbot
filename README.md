# THE FINALS Bot

[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?style=flat-square&logo=docker&logoColor=white)](https://github.com/xiaoyueyoqwq/thefinals_qqbot)
[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![License](https://img.shields.io/badge/License-CC%20BY--NC--SA%204.0-lightgrey?style=flat-square)](https://creativecommons.org/licenses/by-nc-sa/4.0/)
[![Ask DeepWiki](https://deepwiki.com/badge.svg)](https://deepwiki.com/xiaoyueyoqwq/thefinals_qqbot)

**[English]** | [中文](./README_CN.md)

> [!NOTE]
> A comprehensive multi-platform bot for THE FINALS game, providing real-time player statistics, leaderboard tracking, and tournament data across QQ, HeyBox, and Kook platforms. Built with modern async architecture and containerized deployment support.

## Quick Start

```bash
# Docker Compose (Recommended)
docker-compose up -d

# Traditional Python
python bot.py
```

This overview covers the system's architecture, core components, and feature set. For detailed information about installation and configuration, see [Installation and Setup](https://deepwiki.com/xiaoyueyoqwq/thefinals_qqbot/1.1-installation-and-setup). For a complete list of available commands, see [Available Commands](https://deepwiki.com/xiaoyueyoqwq/thefinals_qqbot/1.2-available-commands).

## Architecture

The bot implements a plugin-based architecture with multi-platform provider abstraction, enabling seamless cross-platform operation. Core features include real-time data caching with Redis, dynamic image generation via Playwright, and comprehensive player statistics tracking across multiple game modes including Ranked, World Tour, Quick Cash, and Death Match.

## Documentation

Visit our [comprehensive documentation](https://deepwiki.com/xiaoyueyoqwq/thefinals_qqbot/1-overview) for detailed guides on deployment, configuration, and development.

## Tech Stack

![Python](https://img.shields.io/badge/Python-%233776AB.svg?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-%23009688.svg?style=flat-square&logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-%232496ED.svg?style=flat-square&logo=docker&logoColor=white)
![Redis](https://img.shields.io/badge/Redis-%23DC382D.svg?style=flat-square&logo=redis&logoColor=white)
![Playwright](https://img.shields.io/badge/Playwright-%232EAD33.svg?style=flat-square&logo=playwright&logoColor=white)

## Statistics

[![Star History Chart](https://api.star-history.com/svg?repos=xiaoyueyoqwq/thefinals_qqbot&type=Date)](https://star-history.com/#xiaoyueyoqwq/thefinals_qqbot&Date)

## License

This project is licensed under [Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License](https://creativecommons.org/licenses/by-nc-sa/4.0/).
