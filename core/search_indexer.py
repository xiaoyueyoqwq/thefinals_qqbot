"""
一个为TheFinals排行榜深度搜索优化的、基于内存的倒排索引器。
"""

import re
from collections import defaultdict
from typing import List, Dict, Any, Set
from difflib import SequenceMatcher
from utils.logger import bot_logger
import heapq

def get_trigrams(text: str) -> Set[str]:
    """将文本规范化（小写并移除特殊字符）后，分解为三元组。"""
    # 移除所有非字母数字字符
    normalized_text = re.sub(r'[^a-z0-9]+', '', text.lower())
    # 添加边界标记
    normalized_text = f" {normalized_text} "
    if len(normalized_text) < 4: # 如果规范化后太短，无法生成三元组
        return set()
    return {normalized_text[i:i+3] for i in range(len(normalized_text) - 2)}

class SearchIndexer:
    """
    管理玩家姓名的倒排索引，并提供高效的搜索功能。
    """
    def __init__(self):
        self._index: Dict[str, Set[str]] = defaultdict(set)
        self._player_data: Dict[str, Dict[str, Any]] = {}
        self._name_field = "name"
        self._is_ready = False
        bot_logger.info("[SearchIndexer] 搜索索引器已初始化。")

    def is_ready(self) -> bool:
        """检查索引是否已构建并准备就绪。"""
        return self._is_ready

    def build_index(self, players: List[Dict[str, Any]]):
        """
        根据提供的玩家列表，从头开始构建索引。
        这是一个开销较大的操作，应该在后台定期执行。
        """
        bot_logger.info(f"[SearchIndexer] 开始构建索引，共 {len(players)} 名玩家...")
        new_index = defaultdict(set)
        new_player_data = {}

        for player in players:
            player_id = player.get("name")
            name = player.get(self._name_field)

            if not player_id or not name:
                continue

            # 存储玩家原始数据，并确保有 'score' 字段
            player_copy = player.copy()
            player_copy['score'] = player.get('rankScore', player.get('fame', 0))
            new_player_data[player_id] = player_copy

            # 为玩家名字建立索引
            for trigram in get_trigrams(name):
                new_index[trigram].add(player_id)
            
            # (可选) 为其他字段建立索引，如 'steam', 'psn', 'xbox'
            for key in ['steam', 'psn', 'xbox']:
                if alias := player.get(key):
                    for trigram in get_trigrams(alias):
                        new_index[trigram].add(player_id)

        # 原子性地替换旧索引
        self._index = new_index
        self._player_data = new_player_data
        
        if not self._is_ready:
            self._is_ready = True
        
        bot_logger.info(f"[SearchIndexer] 索引构建完成。索引词条数: {len(self._index)}")

    def search(self, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        """
        使用倒排索引高效地搜索玩家。
        """
        if not query or not self._index:
            return []

        bot_logger.debug(f"[SearchIndexer] Searching for query: '{query}'")

        # 1. 从查询中获取三元组
        query_trigrams = get_trigrams(query)
        bot_logger.debug(f"[SearchIndexer] Query trigrams: {query_trigrams}")
        if not query_trigrams:
            return []

        # 2. 在索引中查找候选玩家
        candidate_scores = defaultdict(int)
        for trigram in query_trigrams:
            if trigram in self._index:
                for player_id in self._index[trigram]:
                    candidate_scores[player_id] += 1
        
        bot_logger.debug(f"[SearchIndexer] Found {len(candidate_scores)} candidates with scores: {candidate_scores}")

        if not candidate_scores:
            return []

        candidate_ids = set(candidate_scores.keys())

        # 3. 对候选人进行精确的相似度计算
        scored_candidates = []
        query_lower = query.lower()
        query_normalized = re.sub(r'[^a-z0-9]+', '', query_lower)

        for player_id in candidate_ids:
            player = self._player_data.get(player_id)
            if not player:
                continue

            max_similarity = 0
            # 检查主名和其他别名
            names_to_check = [player.get(self._name_field, "")] + [player.get(k, "") for k in ['steam', 'psn', 'xbox']]
            
            for name in filter(None, names_to_check):
                name_lower = name.lower()
                name_normalized = re.sub(r'[^a-z0-9]+', '', name_lower)
                
                similarity = 0
                # 优先级1: 字面上的前缀匹配 (e.g., 'DY-' matches 'DY-TFtegong')
                if name_lower.startswith(query_lower):
                    similarity = 2.0 + (len(query_lower) / len(name_lower))
                # 优先级2: 规范化后的前缀匹配 (e.g., 'dy' matches 'Dynamic')
                elif name_normalized.startswith(query_normalized):
                    similarity = 1.0 + (len(query_normalized) / len(name_normalized))
                # 优先级3: 模糊匹配
                else:
                    similarity = SequenceMatcher(None, query_normalized, name_normalized).ratio()
                
                if similarity > max_similarity:
                    max_similarity = similarity
            
            # 阈值调整为0.3以容忍更多模糊匹配
            if max_similarity > 0.3:
                scored_candidates.append((max_similarity, player))

        # 4. 使用 heapq.nlargest 高效获取 Top-N 结果
        top_candidates = heapq.nlargest(limit, scored_candidates, key=lambda item: item[0])
        bot_logger.debug(f"[SearchIndexer] Top {len(top_candidates)} candidates: {[(s, p['name']) for s, p in top_candidates]}")

        # 5. 返回排序后的结果,并附上相似度分数
        results = []
        for score, player in top_candidates:
            player_with_score = player.copy()
            player_with_score['similarity'] = score
            results.append(player_with_score)
        
        return results 