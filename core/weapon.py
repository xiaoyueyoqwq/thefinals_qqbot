import json
import os
import re
import math
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

    def _calculate_ttk(self, weapon_damage: float, fire_rate: int) -> Dict[str, float]:
        """
        根据武器伤害和射速计算击杀不同体型目标的TTK。
        """
        if weapon_damage <= 0 or fire_rate <= 0:
            return {"重型": float('inf'), "中型": float('inf'), "轻型": float('inf')}

        class_hp = {'重型': 350, '中型': 250, '轻型': 150}
        ttk_results = {}

        for class_name, hp in class_hp.items():
            # 向上取整计算击杀所需子弹数
            bullets_to_kill = math.ceil(hp / weapon_damage)
            # TTK 公式: 60 ÷ 射速 × (击杀需要的子弹数 - 1)
            ttk = (60 / fire_rate) * (bullets_to_kill - 1)
            ttk_results[class_name] = ttk
        
        return ttk_results

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
                'bullet_damage': '每颗子弹伤害',
                'head_bullet_damage': '每颗子弹爆头伤害',
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
        body_damage_per_shot = 0
        
        if 'body' in damage:
            body_damage_str = str(damage['body'])
            match = re.search(r'^\d+', body_damage_str)
            if match:
                body_damage_per_shot = int(match.group())
        elif 'pellet_damage' in damage and 'pellet_count' in damage:
            body_damage_per_shot = damage.get('pellet_damage', 0) * damage.get('pellet_count', 0)
        elif 'bullet_damage' in damage and 'bullet_count' in damage:
            body_damage_per_shot = damage.get('bullet_damage', 0) * damage.get('bullet_count', 0)

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
            if body_damage_per_shot > 0 and rpm > 0:
                dps = int(body_damage_per_shot * rpm / 60)
                output += f"▎ 每秒伤害 (DPS): {dps}\n"

            output += f"{SEPARATOR}\n"

        # TTK 计算与显示
        output += "▎🔒 武器TTK:\n"
        ttks = self._calculate_ttk(body_damage_per_shot, rpm)
        
        # 确保输出顺序并处理无法击杀的情况
        class_order = ['重型', '中型', '轻型']
        for class_name in class_order:
            ttk = ttks.get(class_name, float('inf'))
            if ttk == float('inf'):
                output += f"▎ {class_name}: 无法击杀\n"
            else:
                output += f"▎ {class_name}: {ttk:.3f}s\n"
        output += f"{SEPARATOR}\n"

        return output
