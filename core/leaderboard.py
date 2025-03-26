import aiohttp
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
import io
import logging
import json
import random
import os
from typing import List, Dict, Any
from matplotlib.font_manager import FontProperties
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patheffects import withStroke
from utils.logger import bot_logger

class LeaderboardCore:
    """排位分数走势图核心类"""
    
    def __init__(self):
        self.api_base_url = "https://www.davg25.com/app/the-finals-leaderboard-tracker/api/vaiiya/player-history"
        self.logger = logging.getLogger("LeaderboardCore")
        # 设置中文字体
        self.font = FontProperties(fname='static/font/SourceHanSansSC-Medium.otf')
        # 加载小知识
        self.tips = self._load_tips()

    def _load_tips(self) -> list:
        """加载小知识数据"""
        try:
            tips_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "did_you_know.json")
            bot_logger.debug(f"[LeaderboardCore] 正在加载小知识文件: {tips_path}")
            
            # 确保data目录存在
            os.makedirs(os.path.dirname(tips_path), exist_ok=True)
            
            with open(tips_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                tips = data.get("tips", [])
                bot_logger.info(f"[LeaderboardCore] 成功加载 {len(tips)} 条小知识")
                return tips
        except Exception as e:
            bot_logger.error(f"[LeaderboardCore] 加载小知识数据失败: {str(e)}")
            return []
            
    def get_random_tip(self) -> str:
        """获取随机小知识"""
        if not self.tips:
            bot_logger.warning(f"[LeaderboardCore] 小知识列表为空")
            return "暂无小知识"
        return random.choice(self.tips)

    async def fetch_player_history(self, player_id: str, time_range: int = 604800) -> List[Dict[str, Any]]:
        """
        获取玩家历史数据
        
        Args:
            player_id: 玩家ID
            time_range: 时间范围（秒），默认7天
            
        Returns:
            List[Dict]: 历史数据列表
        """
        try:
            params = {
                "id": player_id,
                "range": time_range
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.api_base_url, params=params) as response:
                    if response.status == 404:
                        raise ValueError("玩家不存在")
                    elif response.status != 200:
                        raise RuntimeError(f"API请求失败: {response.status}")
                        
                    return await response.json()
                    
        except Exception as e:
            self.logger.error(f"获取玩家历史数据失败: {str(e)}")
            raise

    def generate_trend_chart(self, history_data: List[Dict[str, Any]], player_id: str) -> bytes:
        """
        生成走势图
        
        Args:
            history_data: 历史数据列表
            player_id: 玩家ID
            
        Returns:
            bytes: 图片数据
        """
        try:
            # 数据处理
            timestamps = [datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00")) 
                        for item in history_data]
            points = [item["points"] for item in history_data]
            ranks = [item["rank"] for item in history_data]
            
            # 创建图表
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), height_ratios=[2, 1])
            fig.patch.set_facecolor('#1E1E1E')
            
            # 设置间距
            plt.subplots_adjust(hspace=0.3)
            
            # 通用样式设置
            for ax in [ax1, ax2]:
                ax.set_facecolor('#1E1E1E')
                ax.grid(True, linestyle='--', alpha=0.15, color='#FFFFFF')
                ax.spines['top'].set_visible(False)
                ax.spines['right'].set_visible(False)
                ax.spines['left'].set_color('#333333')
                ax.spines['bottom'].set_color('#333333')
                ax.tick_params(colors='#CCCCCC', labelsize=10)
                
            # 积分走势
            # 创建渐变填充
            points_color = '#00A8FF'
            glow_color = '#00A8FF'
            
            # 主线
            line1 = ax1.plot(timestamps, points, '-', linewidth=2.5, color=points_color, label='积分',
                          path_effects=[withStroke(linewidth=4, foreground=glow_color, alpha=0.3)])[0]
            
            # 数据点
            ax1.scatter(timestamps, points, color=points_color, s=50, alpha=0.6,
                      path_effects=[withStroke(linewidth=3, foreground=glow_color, alpha=0.3)])
            
            # 填充区域
            ax1.fill_between(timestamps, points, min(points), alpha=0.1, color=points_color)
            
            # 设置标题和样式
            title1 = ax1.set_title(f'THE FINALS | {player_id} 排位走势', pad=20, fontsize=16, fontproperties=self.font, color='#FFFFFF')
            title1.set_path_effects([withStroke(linewidth=3, foreground='#000000', alpha=0.5)])
            
            ax1.set_ylabel('排位分', fontproperties=self.font, color='#FFFFFF', fontsize=12)
            
            # 排名走势
            ranks_color = '#FF3366'
            ranks_glow = '#FF3366'
            
            # 主线
            line2 = ax2.plot(timestamps, ranks, '-', linewidth=2.5, color=ranks_color, label='排名',
                          path_effects=[withStroke(linewidth=4, foreground=ranks_glow, alpha=0.3)])[0]
            
            # 数据点
            ax2.scatter(timestamps, ranks, color=ranks_color, s=50, alpha=0.6,
                      path_effects=[withStroke(linewidth=3, foreground=ranks_glow, alpha=0.3)])
            
            # 填充区域
            ax2.fill_between(timestamps, ranks, max(ranks), alpha=0.1, color=ranks_color)
            
            # 设置标题和样式
            title2 = ax2.set_title('排名变化', pad=20, fontsize=16, fontproperties=self.font, color='#FFFFFF')
            title2.set_path_effects([withStroke(linewidth=3, foreground='#000000', alpha=0.5)])
            
            ax2.set_ylabel('排名', fontproperties=self.font, color='#FFFFFF', fontsize=12)
            ax2.invert_yaxis()
            
            # 设置x轴格式
            for ax in [ax1, ax2]:
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
                for label in ax.get_xticklabels():
                    label.set_rotation(30)
                    label.set_horizontalalignment('right')
            
            # 添加最新数据标注
            latest_point = points[-1]
            latest_rank = ranks[-1]
            latest_time = timestamps[-1]
            
            ax1.annotate(f'{latest_point}',
                        xy=(latest_time, latest_point),
                        xytext=(10, 10), textcoords='offset points',
                        color='#FFFFFF',
                        fontproperties=self.font,
                        bbox=dict(boxstyle='round,pad=0.5', fc='#1E1E1E', ec=points_color, alpha=0.7))
            
            ax2.annotate(f'{latest_rank}',
                        xy=(latest_time, latest_rank),
                        xytext=(10, 10), textcoords='offset points',
                        color='#FFFFFF',
                        fontproperties=self.font,
                        bbox=dict(boxstyle='round,pad=0.5', fc='#1E1E1E', ec=ranks_color, alpha=0.7))
            
            # 自动调整布局
            plt.tight_layout()
            
            # 将图表转换为字节流
            img_buf = io.BytesIO()
            plt.savefig(img_buf, format='png', dpi=120, bbox_inches='tight', facecolor='#1E1E1E')
            img_buf.seek(0)
            plt.close()
            
            return img_buf.getvalue()
            
        except Exception as e:
            self.logger.error(f"生成走势图失败: {str(e)}")
            raise 