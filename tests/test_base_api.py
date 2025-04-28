import os
os.environ["PYTHONPATH"] = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# 强制添加项目根目录到Python路径
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import asyncio
from utils.base_api import BaseAPI
from unittest.mock import patch, AsyncMock
import httpx



async def test_base_api_main_backup_switch():
    """测试BaseAPI主备切换机制（主API可用场景）"""
    api = BaseAPI(base_url="https://api.the-finals-leaderboard.com")
    endpoint = "/v1/leaderboard/s6worldtour/crossplay"
    try:
        response = await api.get(endpoint, use_cache=False)
        data = BaseAPI.handle_response(response)
        print("主API响应：", data)
        assert response.status_code == 200, f"主API状态码异常: {response.status_code}"
        assert data, "主API响应数据为空"
        print("主API可用性测试通过！")
    finally:
        await BaseAPI.close_all_clients()

async def test_base_api_switch_to_backup():
    """强制模拟主API失败，确保会切换到备用API"""
    api = BaseAPI(base_url="https://api.the-finals-leaderboard.com")
    endpoint = "/v1/leaderboard/s6worldtour/crossplay"
    main_url = "https://api.the-finals-leaderboard.com/v1/leaderboard/s6worldtour/crossplay"
    backup_url = "https://99z.top/https://api.the-finals-leaderboard.com/v1/leaderboard/s6worldtour/crossplay"
    fake_backup_data = {"result": "from-backup"}

    async def fake_request(self, method, url, **kwargs):
        if url == main_url:
            raise httpx.ConnectTimeout("mock main api timeout")
        elif url == backup_url:
            request = httpx.Request(method, url)
            response = httpx.Response(200, json=fake_backup_data, request=request)
            return response
        else:
            raise RuntimeError(f"unexpected url: {url}")

    with patch.object(httpx.AsyncClient, "request", new=fake_request):
        response = await api.get(endpoint, use_cache=False)
        data = BaseAPI.handle_response(response)
        print("备用API响应：", data)
        assert response.status_code == 200, f"备用API状态码异常: {response.status_code}"
        assert data == fake_backup_data, f"备用API响应数据异常: {data}"
        print("主备切换测试通过！")
    await BaseAPI.close_all_clients()

async def main():
    print("\n--- 主API可用性测试 ---")
    try:
        await test_base_api_main_backup_switch()
    except Exception as e:
        print(f"主API可用性测试失败: {e}")
    print("\n--- 主备切换mock测试 ---")
    try:
        await test_base_api_switch_to_backup()
    except Exception as e:
        print(f"主备切换mock测试失败: {e}")

if __name__ == "__main__":
    asyncio.run(main()) 