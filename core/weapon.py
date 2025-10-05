import orjson as json
import os
import re
from typing import Dict, Any, Optional, Union
from utils.templates import SEPARATOR  # 导入分隔线模板
from utils.logger import bot_logger
from pathlib import Path
from core.image_generator import ImageGenerator
from utils.config import settings

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
        # 初始化图片生成器
        template_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'resources', 'templates')
        self.image_generator = ImageGenerator(template_dir)

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

        separator_with_newlines = f'\n{SEPARATOR}\n'
        return f"\n{separator_with_newlines.join(parts)}\n{SEPARATOR}"

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
    
    def _prepare_template_data(self, weapon_name: str, data: Dict[str, Any]) -> Dict:
        """准备模板数据"""
        # 翻译映射
        damage_translations = {
            'body': '躯干伤害', 'head': '爆头伤害',
            'pellet_damage': '每颗弹丸伤害', 'pellet_count': '弹丸数量',
            'secondary': '次要攻击', 'bullet_damage': '子弹伤害',
            'head_bullet_damage': '子弹爆头伤害', 'bullet_count': '子弹数量',
            'direct': '直接命中伤害', 'splash': '溅射伤害',
            'splash_radius': '溅射范围'
        }
        
        tech_translations = {
            'rpm': '射速', 'magazine_size': '弹匣容量',
            'empty_reload': '空仓装填', 'tactical_reload': '战术装填',
            'fire_mode': '射击模式'
        }
        
        decay_translations = {
            'min_range': '起始衰减', 'max_range': '最大衰减',
            'decay_multiplier': '衰减系数'
        }
        
        # 处理伤害数据
        damage = {}
        for key, value in data.get('damage', {}).items():
            translated_key = damage_translations.get(key, key)
            damage[translated_key] = value
        
        # 处理技术数据
        technical_data = {}
        tech_data_raw = data.get('technical_data', {})
        for key, value in tech_data_raw.items():
            translated_key = tech_translations.get(key, key)
            technical_data[translated_key] = value
        
        # 计算DPS
        dps = None
        rpm_str = str(tech_data_raw.get('rpm', '0'))
        match = re.search(r'^\d+', rpm_str)
        rpm = int(match.group()) if match else 0
        
        damage_raw = data.get('damage', {})
        damage_per_shot = 0
        if 'body' in damage_raw:
            damage_per_shot = damage_raw['body']
        elif 'pellet_damage' in damage_raw and 'pellet_count' in damage_raw:
            damage_per_shot = damage_raw['pellet_damage'] * damage_raw['pellet_count']
        elif 'bullet_damage' in damage_raw and 'bullet_count' in damage_raw:
            damage_per_shot = damage_raw['bullet_damage'] * damage_raw['bullet_count']
        
        if rpm > 0 and damage_per_shot > 0:
            dps = int((rpm * damage_per_shot) / 60)
        
        # 处理伤害衰减
        damage_decay = {}
        for key, value in data.get('damage_decay', {}).items():
            translated_key = decay_translations.get(key, key)
            # 格式化数值
            if 'range' in key:
                damage_decay[translated_key] = f"{value}m"
            else:
                damage_decay[translated_key] = str(value)
        
        # 处理TTK数据
        ttk = {}
        ttk_data = data.get('ttk', {})
        class_hp_map = {'轻型 (150HP)': '150', '中型 (250HP)': '250', '重型 (350HP)': '350'}
        for class_name, hp_key in class_hp_map.items():
            ttk_value = ttk_data.get(hp_key)
            if ttk_value is not None:
                ttk[class_name] = f"{ttk_value:.3f}s"
        
        # 确定赛季背景图
        season_bg_map = {
            "s3": "s3.png",
            "s4": "s4.png",
            "s5": "s5.png",
            "s6": "s6.jpg",
            "s7": "s7.jpg",
            "s8": "s8.png"
        }
        season = settings.CURRENT_SEASON
        season_bg = season_bg_map.get(season, "s8.png")
        
        return {
            "weapon_name": weapon_name,
            "introduction": data.get('introduction'),
            "damage": damage if damage else None,
            "technical_data": technical_data if technical_data else None,
            "dps": dps,
            "damage_decay": damage_decay if damage_decay else None,
            "ttk": ttk if ttk else None,
            "season_bg": season_bg
        }
    
    async def generate_weapon_image(self, weapon_name: str, data: Dict[str, Any]) -> Optional[bytes]:
        """生成武器信息图片"""
        try:
            template_data = self._prepare_template_data(weapon_name, data)
            image_bytes = await self.image_generator.generate_image(
                template_data=template_data,
                html_content='weapon.html',
                wait_selectors=['.weapon-header'],
                image_quality=80,
                wait_selectors_timeout_ms=300
            )
            return image_bytes
        except Exception as e:
            bot_logger.error(f"生成武器信息图片失败: {str(e)}", exc_info=True)
            return None
    
    async def get_weapon_data_with_image(self, query: str) -> Union[bytes, str, None]:
        """根据武器名称或别名查询武器数据并返回图片或文本"""
        normalized_query = query.lower()
        for weapon_name, data in self.weapon_data.items():
            aliases = [alias.lower() for alias in data.get('aliases', [])]
            if normalized_query == weapon_name.lower() or normalized_query in aliases:
                # 尝试生成图片
                image_bytes = await self.generate_weapon_image(weapon_name, data)
                if image_bytes:
                    return image_bytes
                # 如果图片生成失败，返回文本格式
                return self._format_weapon_data(weapon_name, data)
        return None
    
    def _calculate_dps(self, weapon_data: Dict[str, Any]) -> Optional[int]:
        """计算武器DPS
        
        Args:
            weapon_data: 武器数据
            
        Returns:
            Optional[int]: DPS值，如果无法计算则返回None
        """
        try:
            tech_data = weapon_data.get('technical_data', {})
            damage_data = weapon_data.get('damage', {})
            
            # 获取RPM
            rpm_str = tech_data.get('rpm', '')
            if not rpm_str or not str(rpm_str).replace(',', '').isdigit():
                return None
            rpm = int(str(rpm_str).replace(',', ''))
            
            # 计算每发伤害
            damage_per_shot = 0
            if 'body' in damage_data:
                # 普通武器：body伤害
                damage_value = damage_data['body']
                if isinstance(damage_value, (int, float)):
                    damage_per_shot = damage_value
                elif isinstance(damage_value, str) and damage_value.replace('.', '').isdigit():
                    damage_per_shot = float(damage_value)
            elif 'pellet_damage' in damage_data and 'pellet_count' in damage_data:
                # 散弹武器：弹丸伤害 × 弹丸数量
                damage_per_shot = damage_data['pellet_damage'] * damage_data['pellet_count']
            elif 'bullet_damage' in damage_data and 'bullet_count' in damage_data:
                # 子弹武器：子弹伤害 × 子弹数量
                damage_per_shot = damage_data['bullet_damage'] * damage_data['bullet_count']
            
            if rpm > 0 and damage_per_shot > 0:
                return int((rpm * damage_per_shot) / 60)
            
            return None
        except Exception as e:
            bot_logger.error(f"[WeaponData] 计算DPS失败: {str(e)}")
            return None
    
    async def generate_weapon_leaderboard(self) -> Optional[bytes]:
        """生成武器排行榜图片
        
        Returns:
            Optional[bytes]: 图片数据，如果生成失败则返回None
        """
        try:
            # 计算所有武器的DPS并排序
            weapons_with_dps = []
            for weapon_name, data in self.weapon_data.items():
                dps = self._calculate_dps(data)
                if dps is not None:  # 只包含能计算DPS的武器
                    tech_data = data.get('technical_data', {})
                    damage_data = data.get('damage', {})
                    
                    # 获取伤害值
                    damage_display = damage_data.get('body', 'N/A')
                    if isinstance(damage_display, (int, float)):
                        damage_display = str(int(damage_display))
                    
                    weapons_with_dps.append({
                        'name': weapon_name,
                        'intro': data.get('introduction', '').strip('"'),
                        'dps': dps,
                        'rpm': tech_data.get('rpm', 'N/A'),
                        'damage': damage_display,
                        'mag': tech_data.get('magazine_size', 'N/A')
                    })
            
            # 按DPS降序排序
            weapons_with_dps.sort(key=lambda x: x['dps'], reverse=True)
            
            # 确定赛季背景图
            season_bg_map = {
                "s3": "s3.png",
                "s4": "s4.png",
                "s5": "s5.png",
                "s6": "s6.jpg",
                "s7": "s7.jpg",
                "s8": "s8.png"
            }
            season = settings.CURRENT_SEASON
            season_bg = season_bg_map.get(season, "s8.png")
            
            # 准备模板数据
            template_data = {
                'weapons': weapons_with_dps,
                'season_bg': season_bg
            }
            
            bot_logger.info(f"[WeaponData] 生成武器排行榜，共 {len(weapons_with_dps)} 个武器")
            
            # 生成图片
            image_data = await self.image_generator.generate_image(
                template_data=template_data,
                html_content='weapon_leaderboard.html',
                wait_selectors=['.leaderboard-table'],
                image_quality=80,
                wait_selectors_timeout_ms=300
            )
            
            return image_data
            
        except Exception as e:
            bot_logger.error(f"[WeaponData] 生成武器排行榜失败: {str(e)}")
            bot_logger.exception(e)
            return None
