import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import io
import logging
import asyncio
from typing import List, Dict, Any, Tuple, Optional
from matplotlib.font_manager import FontProperties
import numpy as np
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.patheffects import withStroke
from utils.logger import bot_logger
from utils.base_api import BaseAPI
import matplotlib.style as mplstyle
import orjson as json
from utils.config import settings
import os

class LeaderboardCore(BaseAPI):
    """排位分数走势图核心类"""
    
    # 类级别的样式缓存
    _style_cache = {
        'common': {
            'facecolor': '#1E1E1E',
            'grid': {'linestyle': ':', 'alpha': 0.2, 'color': '#FFFFFF', 'linewidth': 0.5},
            'spines': {'color': '#333333'},
            'tick': {'colors': '#CCCCCC', 'labelsize': 9}
        },
        'points': {
            'color': '#00A8FF',
            'glow': '#00A8FF',
            'alpha': 0.8
        },
        'ranks': {
            'color': '#FF3366',
            'glow': '#FF3366',
            'alpha': 0.8
        }
    }
    
    def __init__(self):
        super().__init__(base_url="https://www.davg25.com/app/the-finals-leaderboard-tracker/api/vaiiya")
        self.logger = logging.getLogger("LeaderboardCore")
        
        # 预加载字体
        font_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'static', 'font', 'SourceHanSansSC-Medium.otf')
        self.font = FontProperties(fname=font_path)
        
        # 预设图表样式
        self._setup_plot_style()

    def _setup_plot_style(self):
        """预设图表样式"""
        mplstyle.use('fast')  # 使用fast样式提高性能
        plt.rcParams['figure.facecolor'] = self._style_cache['common']['facecolor']
        plt.rcParams['axes.facecolor'] = self._style_cache['common']['facecolor']
        plt.rcParams['savefig.facecolor'] = self._style_cache['common']['facecolor']

    def _apply_axis_style(self, ax):
        """应用轴样式"""
        style = self._style_cache['common']
        ax.set_facecolor(style['facecolor'])
        ax.grid(True, **style['grid'])
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        for spine in ['left', 'bottom']:
            ax.spines[spine].set_color(style['spines']['color'])
        ax.tick_params(**style['tick'])

    def _create_figure(self) -> Tuple[plt.Figure, plt.Axes, plt.Axes]:
        """创建和设置图表"""
        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), height_ratios=[2, 1])
        fig.patch.set_facecolor(self._style_cache['common']['facecolor'])
        plt.subplots_adjust(hspace=0.3)
        
        for ax in [ax1, ax2]:
            self._apply_axis_style(ax)
            
        return fig, ax1, ax2

    def _plot_points(self, ax, timestamps, points, window=5):
        """绘制积分走势"""
        style = self._style_cache['points']
        
        # 计算关键点
        latest_point = points[-1]
        max_point = max(points)
        min_point = min(points)
        max_idx = points.index(max_point)
        min_idx = points.index(min_point)
        
        # 主线
        ax.plot(timestamps, points, '-', linewidth=1.2, color=style['color'], label='积分',
               path_effects=[withStroke(linewidth=2, foreground=style['glow'], alpha=0.2)])
        
        # 关键点
        key_points = {-1: latest_point, max_idx: max_point, min_idx: min_point}
        for idx, value in key_points.items():
            ax.scatter(timestamps[idx], value, color=style['color'], s=40, alpha=style['alpha'],
                      path_effects=[withStroke(linewidth=1.5, foreground=style['glow'], alpha=0.2)])
        
        # 填充区域
        ax.fill_between(timestamps, points, min(points), alpha=0.05, color=style['color'])
        
        # 移动平均线
        if len(points) >= window:
            ma = np.convolve(points, np.ones(window)/window, mode='valid')
            ma_timestamps = timestamps[window-1:]
            ax.plot(ma_timestamps, ma, '--', color='#FFA500', alpha=0.6, linewidth=0.8, label='5点平均')
            
        return ax

    def _plot_ranks(self, ax, timestamps, ranks, window=5):
        """绘制排名走势"""
        style = self._style_cache['ranks']
        
        # 主线
        ax.plot(timestamps, ranks, '-', linewidth=1.2, color=style['color'], label='排名',
               path_effects=[withStroke(linewidth=2, foreground=style['glow'], alpha=0.2)])
        
        # 最新排名点
        ax.scatter(timestamps[-1], ranks[-1], color=style['color'], s=40, alpha=style['alpha'],
                  path_effects=[withStroke(linewidth=1.5, foreground=style['glow'], alpha=0.2)])
        
        # 填充区域
        ax.fill_between(timestamps, ranks, max(ranks), alpha=0.05, color=style['color'])
        
        # 移动平均线
        if len(ranks) >= window:
            ma_ranks = np.convolve(ranks, np.ones(window)/window, mode='valid')
            ma_timestamps = timestamps[window-1:]
            ax.plot(ma_timestamps, ma_ranks, '--', color='#FFA500', alpha=0.6, linewidth=0.8, label='5点平均')
            
        return ax

    def generate_trend_chart(self, history_data: List[Dict[str, Any]], player_id: str) -> bytes:
        """生成走势图"""
        try:
            # 数据预处理
            timestamps = [datetime.fromisoformat(item["timestamp"].replace("Z", "+00:00")) for item in history_data]
            points = [item["points"] for item in history_data]
            ranks = [item["rank"] for item in history_data]
            
            # 创建图表
            fig, ax1, ax2 = self._create_figure()
            
            # 设置积分图表的Y轴
            min_score, max_score = min(points), max(points)
            y_min = (min_score // 1000) * 1000
            y_max = ((max_score + 999) // 1000) * 1000
            score_ticks = np.arange(y_min, y_max + 1000, 1000)
            
            ax1.set_yticks(score_ticks)
            ax1.set_ylim(y_min - 200, y_max + 200)
            ax1.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x):,}'))
            ax1.yaxis.set_minor_locator(plt.MultipleLocator(500))
            ax1.grid(True, which='minor', linestyle=':', alpha=0.1, color='#FFFFFF', linewidth=0.3)
            
            # 绘制走势图
            self._plot_points(ax1, timestamps, points)
            self._plot_ranks(ax2, timestamps, ranks)
            
            # 设置x轴范围，消除边距
            ax1.set_xlim(timestamps[0], timestamps[-1])
            ax2.set_xlim(timestamps[0], timestamps[-1])

            # 设置标题
            for ax, title_text in [(ax1, f'THE FINALS | {player_id} 排位走势'), (ax2, '排名变化')]:
                title = ax.set_title(title_text, pad=20, fontsize=16, fontproperties=self.font, color='#FFFFFF')
                title.set_path_effects([withStroke(linewidth=3, foreground='#000000', alpha=0.5)])
                
                # 设置图例
                ax.legend(loc='upper right', 
                         facecolor='#1E1E1E', 
                         edgecolor='#333333',
                         labelcolor='#FFFFFF', 
                         fontsize=8,
                         prop=self.font)
            
            # 设置标签
            ax1.set_ylabel('排位分', fontproperties=self.font, color='#FFFFFF', fontsize=12)
            ax2.set_ylabel('排名', fontproperties=self.font, color='#FFFFFF', fontsize=12)
            ax2.invert_yaxis()
            
            # 设置x轴格式
            for ax in [ax1, ax2]:
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d %H:%M'))
                for label in ax.get_xticklabels():
                    label.set_rotation(30)
                    label.set_horizontalalignment('right')
            
            # 自动调整布局
            plt.tight_layout()
            
            # 添加署名
            latest_time = timestamps[-1].strftime('%H:%M')
            fig.text(0.02, 0.02, 
                    f'Design by luoxiaohei | Data source: the-finals-leaderboard-tracker | {latest_time} (UTC+8)', 
                    fontsize=7, color='#666666', alpha=0.5,
                    ha='left', va='bottom', style='italic',
                    path_effects=[withStroke(linewidth=0.3, foreground='#000000', alpha=0.2)])
            
            # 导出图片
            img_buf = io.BytesIO()
            plt.savefig(img_buf, format='png', dpi=120, bbox_inches='tight', facecolor='#1E1E1E')
            img_buf.seek(0)
            plt.close()
            
            return img_buf.getvalue()
            
        except Exception as e:
            self.logger.error(f"生成走势图失败: {str(e)}")
            raise

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
            
            response = await self.get("player-history", params=params)
            
            if response.status_code == 404:
                raise ValueError("玩家不存在")
            elif response.status_code != 200:
                raise RuntimeError(f"API请求失败: {response.status_code}")
                
            return response.json()
                    
        except Exception as e:
            self.logger.error(f"获取玩家历史数据失败: {str(e)}")
            raise