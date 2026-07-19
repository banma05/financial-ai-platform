"""
智能依赖注入 — 三层回退参数匹配

Level1: 精确映射（60对中→英映射表）
Level2: 编辑距离模糊匹配（≤2字符差异自动匹配）
Level3: LLM辅助语义匹配（前两层都失败时调用一次小模型）

注入命中率统计（Level1/2/3分布），通过 get_stats() 获取。
"""

import json
import re
from typing import Dict, List, Optional, Tuple, Any
from loguru import logger


# ==================== 财务术语中→英映射表（60+对） ====================
# DataQuery 的 LLM 提取返回中文键名，但公式参数使用英文名
# 此映射在依赖注入时将中文键名转换为公式可识别的参数名

FINANCIAL_TERM_TO_PARAM: Dict[str, str] = {
    # ── 盈利能力 ──
    "营业收入": "revenue", "营业总收入": "revenue", "营收": "revenue",
    "营业成本": "cost", "成本": "cost",
    "净利润": "net_profit", "归母净利润": "net_profit",
    "归属于母公司股东的净利润": "net_profit",
    "净资产": "equity", "股东权益": "equity",
    "平均净资产": "avg_equity", "净资产平均值": "avg_equity",
    "总资产": "total_assets", "资产总计": "total_assets",
    "平均总资产": "avg_total_assets", "总资产平均值": "avg_total_assets",
    "毛利润": "gross_profit",
    # ── 偿债能力 ──
    "总负债": "total_liabilities", "负债合计": "total_liabilities",
    "流动资产": "current_assets", "流动资产合计": "current_assets",
    "流动负债": "current_liabilities", "流动负债合计": "current_liabilities",
    "存货": "inventory", "存货净额": "inventory",
    "利息费用": "interest_expense", "财务费用": "interest_expense",
    "EBIT": "ebit", "息税前利润": "ebit",
    # ── 现金流 ──
    "经营活动现金流净额": "operating_cf",
    "经营活动产生的现金流量净额": "operating_cf",
    "经营活动现金流": "operating_cf",
    "投资活动现金流净额": "investing_cf",
    "投资活动产生的现金流量净额": "investing_cf",
    "投资活动现金流": "investing_cf",
    "筹资活动现金流净额": "financing_cf",
    "筹资活动产生的现金流量净额": "financing_cf",
    "筹资活动现金流": "financing_cf",
    "资本支出": "capital_expenditure",
    "购建固定资产无形资产和其他长期资产支付的现金": "capital_expenditure",
    # ── 估值 ──
    "基本每股收益": "eps", "每股收益": "eps", "EPS": "eps",
    "股价": "stock_price", "股票价格": "stock_price",
    "price": "stock_price",  # MCP stock_price 返回的英文键名
    # ── 成长（跨年对比）──
    "上期营业收入": "previous_revenue", "上期营收": "previous_revenue",
    "上期净利润": "previous_profit",
    "当期营业收入": "current_revenue", "当期营收": "current_revenue",
    "当期净利润": "current_profit",
    "营业收入_上期": "previous_revenue", "净利润_上期": "previous_profit",
    "营业收入_当期": "current_revenue", "净利润_当期": "current_profit",
    # ── 通用 ──
    "EBITDA": "ebitda",
    # ── V7.0: 参数回退映射（期末值→平均值，解决 ROE/ROA 缺参数问题）──
    "净资产": "equity", "净资产(期末)": "equity",
    "平均净资产": "avg_equity", "净资产平均值": "avg_equity",
    "平均总资产": "avg_total_assets", "总资产平均值": "avg_total_assets",
    "期初净资产": "equity_beginning", "期初总资产": "total_assets_beginning",
    "期末净资产": "equity", "期末总资产": "total_assets",
}


# ==================== 金额单位解析 ====================

_UNIT_PATTERN = re.compile(
    r'^(-?\d+\.?\d*)\s*(亿元|万元|元|亿|万|%|％)?$'
)

_UNIT_TO_MULTIPLIER = {
    "亿元": 100_000_000, "亿": 100_000_000,
    "万元": 10_000, "万": 10_000,
    "元": 1,
    "%": 1, "％": 1,
}


def parse_financial_value(value) -> Optional[float]:
    """
    将财务数值字符串解析为 float。

    支持格式: "1709.90亿元" → 1709.90（保留原始数值，不换算到元）
              "91.5%" → 91.5
              已经是数字的直接返回
    """
    if isinstance(value, (int, float)):
        return float(value)
    if not isinstance(value, str):
        return None

    match = _UNIT_PATTERN.match(value.strip())
    if match:
        num = float(match.group(1))
        return num
    # 尝试直接转换数字字符串
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


# ==================== 编辑距离（Levenshtein） ====================

def _edit_distance(s1: str, s2: str) -> int:
    """
    计算两个字符串的 Levenshtein 编辑距离。

    纯 Python 实现，不引入额外依赖。
    时间复杂度 O(m*n)，对于短字符串（财务术语通常 <20 字符）足够快。
    """
    if len(s1) < len(s2):
        s1, s2 = s2, s1

    # s1 是较长的字符串
    m, n = len(s1), len(s2)

    # 只保留两行，节省内存
    prev = list(range(n + 1))
    curr = [0] * (n + 1)

    for i in range(1, m + 1):
        curr[0] = i
        for j in range(1, n + 1):
            cost = 0 if s1[i - 1] == s2[j - 1] else 1
            curr[j] = min(
                prev[j] + 1,        # 删除
                curr[j - 1] + 1,    # 插入
                prev[j - 1] + cost, # 替换
            )
        prev, curr = curr, prev

    return prev[n]


# ==================== 参数注入器 ====================

class ParamInjector:
    """
    智能参数注入器 — 三层回退。

    使用方式:
        injector = ParamInjector()
        params = injector.inject(extracted_data, existing_params)

    统计查询:
        stats = injector.get_stats()  # {"level1": 45, "level2": 8, "level3": 2, "miss": 1}
    """

    # 编辑距离阈值（≤此值视为匹配成功）
    EDIT_DISTANCE_THRESHOLD = 2

    # Level3 LLM 批量匹配的最大键名数（一次调用不超过此数，控制 token 消耗）
    LLM_BATCH_MAX_KEYS = 60

    def __init__(self):
        self._stats: Dict[str, int] = {"level1": 0, "level2": 0, "level3": 0, "miss": 0}
        # Level3 缓存：避免对同一未匹配键名重复调 LLM
        self._llm_cache: Dict[str, Optional[str]] = {}

    # ── 公开 API ──

    def map_key(self, chinese_key: str) -> Tuple[Optional[str], str]:
        """
        单键三层回退匹配（不含 LLM 批量优化）。

        返回:
            (映射后的键名或 None, 命中层级: "level1"/"level2"/"level3"/"miss")

        注意：此方法不会触发 Level3 LLM 调用（需要批量场景用 inject()）。
              对于单键 Level3 场景，返回 (None, "miss")。
        """
        # Level1: 精确匹配
        if chinese_key in FINANCIAL_TERM_TO_PARAM:
            self._stats["level1"] += 1
            return FINANCIAL_TERM_TO_PARAM[chinese_key], "level1"

        # Level2: 编辑距离模糊匹配
        mapped = self._fuzzy_match(chinese_key)
        if mapped:
            self._stats["level2"] += 1
            return mapped, "level2"

        # Level3: 检查 LLM 缓存
        if chinese_key in self._llm_cache:
            cached = self._llm_cache[chinese_key]
            if cached:
                self._stats["level3"] += 1
                return cached, "level3"
            else:
                self._stats["miss"] += 1
                return None, "miss"

        self._stats["miss"] += 1
        return None, "miss"

    @staticmethod
    def _strip_year_suffix(key: str) -> Tuple[str, Optional[str]]:
        """
        V8.4: 剥离年份后缀，供注入时使用。

        "营业收入_2024" → ("营业收入", "_2024")
        "营业收入" → ("营业收入", None)
        """
        m = re.search(r'_(\d{4})$', key)
        if m:
            return key[:m.start()], m.group(0)
        return key, None

    def inject(
        self,
        extracted_data: Dict[str, Any],
        existing_params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        主入口：对提取的数据做三层回退键名映射，注入到参数字典。

        流程:
            1. 遍历 extracted_data，解析数值
            2. Level1 精确匹配 → Level2 编辑距离 → Level3 LLM 批量
            3. 注入到 existing_params（不覆盖已有参数）

        参数:
            extracted_data: DataQuery 提取的原始数据 {中文键名: 值}
            existing_params: 当前任务参数字典（原地修改）

        返回:
            existing_params（已注入新参数）
        """
        level3_batch: List[Tuple[str, float]] = []

        for key, value in extracted_data.items():
            # 跳过元数据键
            if key in ("found", "success", "summary", "error", "confidence",
                       "expression", "display_name", "category", "unit"):
                continue

            # 解析数值
            parsed = parse_financial_value(value)
            if parsed is None:
                continue

            # ── V8.4: 年份后缀剥离 ──
            base_key, year_suffix = ParamInjector._strip_year_suffix(key)

            # Level1: 精确映射（用 base_key 匹配，然后拼接回年份后缀）
            mapped = FINANCIAL_TERM_TO_PARAM.get(base_key)
            if mapped:
                self._stats["level1"] += 1
                result_key = mapped + year_suffix if year_suffix else mapped
                self._do_inject(result_key, key, parsed, existing_params)
                continue

            # Level2: 编辑距离模糊匹配
            mapped = self._fuzzy_match(base_key)
            if mapped:
                self._stats["level2"] += 1
                result_key = mapped + year_suffix if year_suffix else mapped
                self._do_inject(result_key, key, parsed, existing_params)
                continue

            # Level3: 检查 LLM 缓存（用原始 key，LLM 自己处理年份）
            if key in self._llm_cache:
                cached = self._llm_cache[key]
                if cached:
                    self._stats["level3"] += 1
                    self._do_inject(cached, key, parsed, existing_params)
                    continue
                else:
                    self._stats["miss"] += 1
                    continue

            # 收集到 Level3 批量队列
            level3_batch.append((key, parsed))

        # Level3: LLM 批量辅助匹配
        if level3_batch:
            self._llm_batch_match(level3_batch, existing_params)

        return existing_params

    def get_stats(self) -> Dict[str, int]:
        """获取各层命中统计（返回副本，外部不可修改内部状态）"""
        total = sum(self._stats.values())
        stats = dict(self._stats)
        stats["total"] = total
        if total > 0:
            stats["level1_pct"] = round(100 * self._stats["level1"] / total, 1)
            stats["level2_pct"] = round(100 * self._stats["level2"] / total, 1)
            stats["level3_pct"] = round(100 * self._stats["level3"] / total, 1)
            stats["miss_pct"] = round(100 * self._stats["miss"] / total, 1)
        return stats

    def reset_stats(self):
        """重置统计数据"""
        self._stats = {"level1": 0, "level2": 0, "level3": 0, "miss": 0}
        self._llm_cache.clear()

    # ── 内部方法 ──

    def _fuzzy_match(self, chinese_key: str) -> Optional[str]:
        """
        编辑距离模糊匹配。

        在映射表的所有中文键名中，找到编辑距离 ≤2 的最近匹配。
        如果多个候选距离相同，返回 None（保守策略，交给 Level3）。
        """
        best_match = None
        best_distance = self.EDIT_DISTANCE_THRESHOLD + 1
        tie_count = 0

        for candidate in FINANCIAL_TERM_TO_PARAM:
            dist = _edit_distance(chinese_key, candidate)
            if dist < best_distance:
                best_distance = dist
                best_match = candidate
                tie_count = 1
            elif dist == best_distance:
                tie_count += 1

        # 阈值检查 + 平局检查
        if best_distance <= self.EDIT_DISTANCE_THRESHOLD and tie_count == 1:
            return FINANCIAL_TERM_TO_PARAM[best_match]

        return None

    def _llm_batch_match(
        self,
        batch: List[Tuple[str, float]],
        existing_params: Dict[str, Any],
    ):
        """
        Level3: LLM 批量辅助语义匹配。

        将一批未匹配的中文键名发送给 LLM，让它推断对应的英文参数名。
        结果缓存到 self._llm_cache，后续相同键名直接命中缓存。
        """
        if not batch:
            return

        # 去重（同一批次中可能有重复键名）
        unique_keys = list(dict.fromkeys(key for key, _ in batch))

        # 超过批量上限时分批处理
        if len(unique_keys) > self.LLM_BATCH_MAX_KEYS:
            logger.warning(
                f"Level3 批量匹配键名过多 ({len(unique_keys)})，"
                f"截断为 {self.LLM_BATCH_MAX_KEYS} 个"
            )
            unique_keys = unique_keys[:self.LLM_BATCH_MAX_KEYS]

        # 构建候选参数列表（供 LLM 参考）
        param_list = sorted(set(FINANCIAL_TERM_TO_PARAM.values()))

        prompt = _build_level3_prompt(unique_keys, param_list)

        try:
            from rag.model_router import chat, TaskType

            response = chat(
                messages=[{"role": "user", "content": prompt}],
                task_type=TaskType.SIMPLE,  # 简单匹配任务，用 flash 省钱
            )

            # 解析 LLM 返回的 JSON
            mappings = _parse_level3_response(response, unique_keys)

            # 缓存结果 + 注入参数
            for key, parsed in batch:
                if key in mappings and mappings[key]:
                    self._stats["level3"] += 1
                    self._llm_cache[key] = mappings[key]
                    self._do_inject(mappings[key], key, parsed, existing_params)
                else:
                    self._stats["miss"] += 1
                    self._llm_cache[key] = None  # 缓存失败结果，避免重复 LLM 调用

        except Exception as e:
            logger.error(f"Level3 LLM 批量匹配失败: {e}")
            # LLM 调用失败时，所有批量键名标记为 miss
            for key, _ in batch:
                self._stats["miss"] += 1
                if key not in self._llm_cache:
                    self._llm_cache[key] = None

    def _do_inject(
        self,
        mapped_key: str,
        original_key: str,
        value: float,
        params: Dict[str, Any],
    ):
        """
        安全注入：不覆盖已有参数，同时保留英文键名和原始中文键名。
        """
        if mapped_key not in params:
            params[mapped_key] = value

        # 同时保留原始键名（兜底）
        if original_key != mapped_key and original_key not in params:
            params[original_key] = value


# ==================== Level3 Prompt 构建 ====================

def _build_level3_prompt(unknown_keys: List[str], candidate_params: List[str]) -> str:
    """
    构建 Level3 LLM 语义匹配的 prompt。

    要求 LLM 返回严格的 JSON 格式，方便解析。
    """
    keys_json = json.dumps(unknown_keys, ensure_ascii=False)
    params_json = json.dumps(candidate_params, ensure_ascii=False)

    return f"""你是一个财务数据映射助手。以下是一些从财务报告中提取的中文指标名，需要映射到标准英文参数名。

## 待映射的中文键名
{keys_json}

## 可用的英文参数名（候选列表）
{params_json}

## 映射规则
1. 根据语义相似度将每个中文键名映射到最合适的英文参数名
2. 如果某个中文键名没有合适的英文参数名对应，请将它映射为 null
3. 忽略中文键名中可能包含的单位后缀（如"（亿元）"、"（万元）"等）
4. 注意区分近似但不相同的概念（如"营业收入"→"revenue"，"营业成本"→"cost"）

## 输出格式
请严格输出一个 JSON 对象，键为中文键名，值为英文参数名或 null：
```json
{{"中文键名1": "english_param", "中文键名2": null}}
```

只输出 JSON，不要任何解释文字。"""


def _parse_level3_response(response: str, expected_keys: List[str]) -> Dict[str, Optional[str]]:
    """
    解析 LLM 返回的 Level3 映射结果。

    容错处理：
    1. 尝试直接解析整个响应
    2. 尝试提取 ```json ... ``` 代码块
    3. 尝试提取 { ... } 对象
    """
    # 提取 JSON 内容
    text = response.strip()

    # 尝试提取 ```json ... ``` 代码块
    code_block_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if code_block_match:
        text = code_block_match.group(1).strip()

    # 尝试提取最外层 { ... }
    if not text.startswith('{'):
        brace_match = re.search(r'\{.*\}', text, re.DOTALL)
        if brace_match:
            text = brace_match.group(0)

    try:
        result = json.loads(text)
        if isinstance(result, dict):
            # 只保留预期键名列表中的映射
            filtered = {}
            for key in expected_keys:
                filtered[key] = result.get(key)
            return filtered
    except json.JSONDecodeError as e:
        logger.warning(f"Level3 LLM 返回 JSON 解析失败: {e}，原始响应: {response[:200]}")

    # 解析失败，返回空映射
    return {key: None for key in expected_keys}


# ==================== 模块级便捷函数 ====================

# 全局注入器实例（供 executor 使用，保持状态一致）
_default_injector: Optional[ParamInjector] = None


def get_injector() -> ParamInjector:
    """获取全局注入器实例（懒初始化）"""
    global _default_injector
    if _default_injector is None:
        _default_injector = ParamInjector()
    return _default_injector


def reset_injector():
    """重置全局注入器（测试用）"""
    global _default_injector
    _default_injector = ParamInjector()
