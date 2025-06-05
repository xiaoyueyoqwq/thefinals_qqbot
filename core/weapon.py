import json
import os
from typing import Dict, Any, Optional
from utils.templates import SEPARATOR  # 导入分隔线模板

class WeaponData:
    """
    武器数据模块

    功能概述:
    - 加载武器数据
    - 根据武器名称或别名查询武器数据
    - 格式化武器数据输出
    """

    def __init__(self):
        self.weapon_data: Dict[str, Any] = {}
        self._load_weapon_data()

    def _load_weapon_data(self):
        """
        从 data/weapon.json 文件加载武器数据
        """
        file_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'weapon.json')
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                self.weapon_data = json.load(f)
        except FileNotFoundError:
            print(f"Error: weapon.json not found at {file_path}")
        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON from {file_path}")

    def get_weapon_data(self, query: str) -> Optional[str]:
        """
        根据武器名称或别名查询武器数据并格式化输出

        参数:
        - query (str): 用户输入的武器名称或别名

        返回:
        - Optional[str]: 格式化后的武器数据字符串，如果未找到则返回 None
        """

        normalized_query = query.lower()

        for weapon_name, data in self.weapon_data.items():
            aliases = [alias.lower() for alias in data.get('aliases', [])]
            if normalized_query == weapon_name.lower() or normalized_query in aliases:
                return self._format_weapon_data(weapon_name, data)

        return None

    def _format_weapon_data(self, weapon_name: str, data: Dict[str, Any]) -> str:
        """
        格式化武器数据为易读的字符串

        参数:
        - weapon_name (str): 武器的官方名称
        - data (Dict[str, Any]): 武器数据字典

        返回:
        - str: 格式化后的字符串
        """
        # 开始构建输出
        output = f"\n✨ {weapon_name} | THE FINALS\n"

        # 介绍
        if intro := data.get('introduction'):
            output += f"📖 简介: {intro}\n{SEPARATOR}\n"

        # 伤害数据
        damage = data.get('damage', {})
        if damage:
            output += "▎💥 基础伤害:\n"
            damage_translations = {
                'body': '躯干伤害',
                'head': '爆头伤害',
                'pellet_damage': '单发伤害',
                'pellet_count': '弹丸数量',
                'secondary': '特殊伤害'
            }
            for key, value in damage.items():
                key_name = damage_translations.get(key, key)
                output += f"▎ {key_name}: {value}\n"
            output += f"{SEPARATOR}\n"

        # 伤害衰减
        damage_decay = data.get('damage_decay', {})
        if damage_decay:
            output += "▎📉 伤害衰减:\n"
            output += f"▎ 起始衰减: {damage_decay.get('min_range', 'N/A')}m\n"
            output += f"▎ 最大衰减: {damage_decay.get('max_range', 'N/A')}m\n"
            output += f"▎ 衰减系数: {damage_decay.get('decay_multiplier', 'N/A')}\n"
            output += f"{SEPARATOR}\n"

        # 技术数据
        technical_data = data.get('technical_data', {})
        if technical_data:
            output += "▎🎯 武器参数:\n"
            tech_translations = {
                'rpm': '射速',
                'magazine_size': '弹匣容量',
                'empty_reload': '空仓装填',
                'tactical_reload': '战术装填',
                'fire_mode': '射击模式'
            }
            for key, value in technical_data.items():
                translated_key = tech_translations.get(key, key)
                output += f"▎ {translated_key}: {value}\n"
            output += f"{SEPARATOR}\n"

        return output
