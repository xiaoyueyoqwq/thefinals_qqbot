import asyncio
import pytest
from pathlib import Path
from datetime import datetime, date, timedelta
from core.df import DFQuery

# 确保测试输出目录存在
output_dir = Path("tests/temp")
output_dir.mkdir(exist_ok=True)

@pytest.fixture
def mock_live_data():
    """模拟实时的排行榜数据"""
    return {
        "500": {
            "player_id": "PlayerRuby",
            "score": 52000,
            "update_time": datetime.now().isoformat()
        },
        "10000": {
            "player_id": "PlayerCutoff",
            "score": 21000,
            "update_time": datetime.now().isoformat()
        },
        "diamond_bottom": {
            "player_id": "PlayerDiamond",
            "update_time": datetime.now().isoformat(),
            "league": "Diamond 4",
            "rank": 2500
        }
    }

@pytest.fixture
def mock_yesterday_data():
    """模拟昨天的历史数据"""
    return {
        500: {
            "score": 51500,
        },
        10000: {
            "score": 21200,
        },
        "diamond_bottom": {
            "numeric_rank": 2550, # 使用修正后的字段
            "rank": "diamond_bottom"
        }
    }

@pytest.mark.asyncio
async def test_generate_df_cutoff_image(monkeypatch, mock_live_data, mock_yesterday_data):
    """
    测试 DFQuery.generate_cutoff_image 是否能成功生成图片。
    """
    # 1. 准备
    df_query = DFQuery()
    safe_score_line = "🛡️ 当前安全分: 15,000 (测试)"

    # 2. 使用 monkeypatch 模拟数据返回，避免依赖外部文件或Redis
    async def mock_get_bottom_scores(*args, **kwargs):
        return mock_live_data

    def mock_get_daily_data_for_stats(*args, **kwargs):
        return mock_yesterday_data

    monkeypatch.setattr(df_query, 'get_bottom_scores', mock_get_bottom_scores)
    monkeypatch.setattr(df_query, '_get_daily_data_for_stats', mock_get_daily_data_for_stats)

    # 3. 执行
    image_bytes = await df_query.generate_cutoff_image(safe_score_line)

    # 4. 断言
    assert image_bytes is not None, "图片生成失败，返回了 None"
    assert isinstance(image_bytes, bytes), "返回的不是 bytes 类型"
    assert len(image_bytes) > 1024, "生成的图片文件过小，可能为空或错误图片"

    # 5. 保存图片以供人工检查
    output_path = output_dir / "df_cutoff_test_output.png"
    with open(output_path, "wb") as f:
        f.write(image_bytes)
    
    print(f"\n✅ 测试图片已成功生成并保存至: {output_path}")
    print("请检查该图片以确认视觉效果和数据准确性。")
    print("预期结果:")
    print("  - 红宝石 (Top 500): 52,000, 变化 +500")
    print("  - 钻石 (Diamond): 排名 2,500, 排名变化 ↑50")
    print("  - 入榜 (Top 10,000): 21,000, 变化 -200")