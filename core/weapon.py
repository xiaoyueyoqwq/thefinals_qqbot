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
        """
        parts = [f"✨ {weapon_name} | THE FINALS"]

        if intro_part := self._format_introduction(data):
            parts.append(intro_part)
        if damage_part := self._format_damage(data):
            parts.append(damage_part)
        if decay_part := self._format_damage_decay(data):
            parts.append(decay_part)
        if tech_part := self._format_technical_data(data):
            parts.append(tech_part)
        if ttk_part := self._format_ttk(data):
            parts.append(ttk_part)

        return f"\n{f'\n{SEPARATOR}\n'.join(parts)}\n{SEPARATOR}"

    def _format_introduction(self, data: Dict[str, Any]) -> Optional[str]:
        """格式化武器介绍部分"""
        if intro := data.get('introduction'):
            return f"📖 简介: {intro}"
        return None

    def _format_damage(self, data: Dict[str, Any]) -> Optional[str]:
        """格式化武器伤害部分"""
        damage = data.get('damage', {})
        if not damage:
            return None

        damage_parts = ["▎💥 基础伤害:"]
        damage_translations = {
            'body': '躯干伤害', 'head': '爆头伤害',
            'pellet_damage': '每颗弹丸伤害', 'pellet_count': '弹丸数量',
            'secondary': '次要攻击', 'bullet_damage': '子弹伤害',
            'head_bullet_damage': '子弹爆头伤害', 'bullet_count': '子弹数量',
            'direct': '直接命中伤害', 'splash': '溅射伤害',
            'splash_radius': '溅射范围'
        }
        for key, value in damage.items():
            key_name = damage_translations.get(key, key)
            damage_parts.append(f"▎ {key_name}: {value}")
        return "\n".join(damage_parts)

    def _format_damage_decay(self, data: Dict[str, Any]) -> Optional[str]:
        """格式化武器伤害衰减部分"""
        damage_decay = data.get('damage_decay', {})
        if not damage_decay:
            return None
            
        decay_parts = ["▎📉 伤害衰减:"]
        decay_parts.append(f"▎ 起始衰减: {damage_decay.get('min_range', 'N/A')}m")
        decay_parts.append(f"▎ 最大衰减: {damage_decay.get('max_range', 'N/A')}m")
        decay_parts.append(f"▎ 衰减系数: {damage_decay.get('decay_multiplier', 'N/A')}")
        return "\n".join(decay_parts)

    def _format_technical_data(self, data: Dict[str, Any]) -> Optional[str]:
        """格式化武器技术数据部分"""
        technical_data = data.get('technical_data', {})
        if not technical_data:
            return None

        tech_parts = ["▎🎯 武器参数:"]
        tech_translations = {
            'rpm': '射速', 'magazine_size': '弹匣容量',
            'empty_reload': '空仓装填', 'tactical_reload': '战术装填',
            'fire_mode': '射击模式'
        }
        
        display_order = ['rpm', 'magazine_size', 'empty_reload', 'tactical_reload', 'fire_mode']
        
        for key in display_order:
            if key in technical_data:
                translated_key = tech_translations.get(key, key)
                tech_parts.append(f"▎ {translated_key}: {technical_data[key]}")

        for key, value in technical_data.items():
            if key not in display_order:
                translated_key = tech_translations.get(key, key)
                tech_parts.append(f"▎ {translated_key}: {value}")
        
        damage = data.get('damage', {})
        rpm_str = str(technical_data.get('rpm', '0'))
        match = re.search(r'^\d+', rpm_str)
        rpm = int(match.group()) if match else 0
        
        damage_per_shot = 0
        if 'body' in damage:
            damage_per_shot = damage['body']
        elif 'pellet_damage' in damage and 'pellet_count' in damage:
            damage_per_shot = damage['pellet_damage'] * damage['pellet_count']
        elif 'bullet_damage' in damage and 'bullet_count' in damage:
            damage_per_shot = damage['bullet_damage'] * damage['bullet_count']
            
        dps = int((rpm * damage_per_shot) / 60) if rpm > 0 and damage_per_shot > 0 else 0
        tech_parts.append(f"▎ 每秒伤害 (DPS): {dps}")
        
        return "\n".join(tech_parts)

    def _format_ttk(self, data: Dict[str, Any]) -> Optional[str]:
        """格式化武器TTK部分"""
        ttk_data = data.get('ttk', {})
        if not ttk_data:
            return None

        ttk_parts = ["▎🔒 武器TTK:"]
        class_hp_map = {'轻型': '150', '中型': '250', '重型': '350'}
        for class_name, hp_key in class_hp_map.items():
            ttk_value = ttk_data.get(hp_key)
            if ttk_value is not None:
                ttk_parts.append(f"▎ {class_name} ({hp_key} HP): {ttk_value:.3f}s")
            else:
                ttk_parts.append(f"▎ {class_name} ({hp_key} HP): N/A")
        return "\n".join(ttk_parts)
