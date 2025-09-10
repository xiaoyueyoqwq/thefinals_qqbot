import orjson as json
import os
import re
from typing import Dict, Any, Optional
from utils.templates import SEPARATOR  # 导入分隔线模板
from utils.logger import bot_logger
from pathlib import Path

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
        self.data_path = Path("data/weapon.json")
        self.weapon_data = self._load_data()

    def _load_data(self) -> Dict:
        """加载武器数据"""
        try:
            with open(self.data_path, 'rb') as f:
                return json.loads(f.read())
        except (FileNotFoundError, Exception):
            return {}

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
                'pellet_damage': '每颗弹丸伤害',
                'pellet_count': '弹丸数量',
                'secondary': '次要攻击',
                'bullet_damage': '子弹伤害',
                'head_bullet_damage': '子弹爆头伤害',
                'bullet_count': '子弹数量',
                'direct': '直接命中伤害',
                'splash': '溅射伤害',
                'splash_radius': '溅射范围'
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

        # 提取身体伤害和射速，用于后续计算
        technical_data = data.get('technical_data', {})
        
        rpm = 0
        if 'rpm' in technical_data:
            rpm_str = str(technical_data['rpm'])
            match = re.search(r'^\d+', rpm_str)
            if match:
                rpm = int(match.group())

        # 技术数据
        if technical_data:
            output += "▎🎯 武器参数:\n"

            tech_translations = {
                'rpm': '射速',
                'magazine_size': '弹匣容量',
                'empty_reload': '空仓装填',
                'tactical_reload': '战术装填',
                'fire_mode': '射击模式'
            }

            # 定义期望的显示顺序，以规范化输出
            display_order = ['rpm', 'magazine_size', 'empty_reload', 'tactical_reload', 'fire_mode']
            
            # 1. 按预设顺序显示参数
            for key in display_order:
                if key in technical_data:
                    translated_key = tech_translations.get(key, key)
                    output += f"▎ {translated_key}: {technical_data[key]}\n"

            # 2. 显示其他未在display_order中的技术数据 (为了兼容性)
            for key, value in technical_data.items():
                if key not in display_order:
                    translated_key = tech_translations.get(key, key)
                    output += f"▎ {translated_key}: {value}\n"

            # 3. 最后显示DPS
            # 获取躯干伤害
            body_damage = damage.get('body', 0) # 获取躯干伤害，如果不存在则为0
            # 计算DPS: (射速 * 躯干伤害) / 60
            dps = int((rpm * body_damage) / 60) if rpm > 0 and body_damage > 0 else 0 # 确保射速和伤害大于0才计算
            output += f"▎ 每秒伤害 (DPS): {dps}\n"

            output += f"{SEPARATOR}\n"

        # TTK 显示 (Read from JSON instead of calculating)
        ttk_data = data.get('ttk', {})
        if ttk_data:
            output += "▎🔒 武器TTK:\n"
            # Ensure output order and handle missing data
            class_hp_map = {'轻型': '150', '中型': '250', '重型': '350'}
            for class_name, hp_key in class_hp_map.items():
                ttk_value = ttk_data.get(hp_key)
                if ttk_value is not None:
                    output += f"▎ {class_name} ({hp_key} HP): {ttk_value:.3f}s\n"
                else:
                    output += f"▎ {class_name} ({hp_key} HP): N/A\n"
            output += f"{SEPARATOR}"

        return output.rstrip()
