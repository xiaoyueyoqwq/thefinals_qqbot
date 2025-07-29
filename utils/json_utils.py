import aiofiles
import orjson as json
from pathlib import Path
from typing import Any, Dict, List, Union
from utils.logger import bot_logger
import asyncio

# 创建一个文件锁字典，为每个文件路径创建一个锁
_file_locks: Dict[Path, asyncio.Lock] = {}

def _get_file_lock(file_path: Path) -> asyncio.Lock:
    """获取或创建文件路径对应的锁"""
    # 确保路径是绝对路径，以避免因相对路径变化导致的问题
    abs_path = file_path.resolve()
    if abs_path not in _file_locks:
        _file_locks[abs_path] = asyncio.Lock()
    return _file_locks[abs_path]

async def save_json(file_path: Union[str, Path], data: Any) -> bool:
    """
    异步、线程安全地将数据保存为JSON文件。

    Args:
        file_path (Union[str, Path]): 要保存的文件路径。
        data (Any): 要保存的数据。

    Returns:
        bool: 如果成功保存则返回 True，否则返回 False。
    """
    path = Path(file_path)
    lock = _get_file_lock(path)
    
    async with lock:
        try:
            # 确保目录存在
            path.parent.mkdir(parents=True, exist_ok=True)
            
            async with aiofiles.open(path, "wb") as f:
                await f.write(json.dumps(data, option=json.OPT_INDENT_2))
            return True
        except Exception as e:
            bot_logger.error(f"保存JSON文件失败: {path} - {e}", exc_info=True)
            return False

async def load_json(file_path: Union[str, Path], default: Any = None) -> Any:
    """
    异步、线程安全地从JSON文件加载数据。

    Args:
        file_path (Union[str, Path]): 要加载的文件路径。
        default (Any, optional): 如果文件不存在或解析失败时返回的默认值。默认为 None。

    Returns:
        Any: 加载的数据或默认值。
    """
    path = Path(file_path)
    lock = _get_file_lock(path)
    
    async with lock:
        if not path.exists():
            return default
        
        try:
            async with aiofiles.open(path, "rb") as f:
                content = await f.read()
                return json.loads(content)
        except Exception as e:
            bot_logger.error(f"加载JSON文件失败: {path} - {e}", exc_info=True)
            return default 