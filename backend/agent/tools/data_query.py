"""
数据查询工具 — 封装模块一的 RAG 管道，从知识库提取结构化财务数据

流程：
1. 调用 hybrid_search 检索相关 chunks
2. LLM 从检索结果中提取结构化数值
3. 返回结构化数据供后续计算和图表使用
"""
from typing import List, Dict, Any, Optional
from loguru import logger

from rag.hybrid_search import hybrid_search
from rag.query_processor import process_query
from rag.model_router import chat, TaskType


class DataQueryTool:
    """
    数据查询工具：从知识库中检索并提取结构化财务数据。

    与模块一 RAG 的区别：
    - 模块一问"茅台毛利率多少"→ 返回自然语言答案+引用
    - DataQuery 问"茅台2022-2024年毛利率"→ 返回 {"2022": 92.0, "2023": 91.8, "2024": 91.5}
    """

    def __init__(self):
        self.name = "data_query"

    def run(self, query: str, session_id: str = "default", top_k: int = 10) -> dict:
        """
        执行数据查询。

        参数:
            query: 自然语言查询（例如"贵州茅台2022-2024年毛利率和净利率"）
            session_id: 会话 ID
            top_k: 检索文档数（数据提取需要更多候选，默认10）

        返回:
            {
                "found": True/False,
                "data": {...},           # 结构化数值（LLM 提取）
                "summary": "xxx",        # 人类可读摘要
                "raw_chunks": [...],     # 原始检索结果
                "confidence": 0.0-1.0,   # 置信度
            }
        """
        logger.info(f"DataQuery 工具调用: {query}")

        # Step 1: Query 处理（复用模块一）
        processed_query = process_query(query)

        # Step 2: 混合检索
        sources = hybrid_search(processed_query, top_k=top_k)

        if not sources:
            return {
                "found": False,
                "data": {},
                "summary": f"未在知识库中找到与「{query}」相关的数据",
                "raw_chunks": [],
                "confidence": 0.0,
            }

        # Step 3: LLM 从检索结果中提取结构化数据
        extracted = self._extract_structured_data(query, sources)

        return {
            "found": extracted.get("found", False),
            "data": extracted.get("data", {}),
            "summary": extracted.get("summary", ""),
            "raw_chunks": [{"content": s["content"][:300], "source": s["source"], "page": s["page"]} for s in sources],
            "confidence": extracted.get("confidence", 0.5),
        }

    def _extract_structured_data(self, query: str, sources: List[dict]) -> dict:
        """
        LLM 从检索到的 chunks 中提取结构化数值。

        这个方法的核心价值：将自然语言文档内容转为机器可计算的结构化数据。
        """
        # 构建上下文
        context_parts = []
        for i, s in enumerate(sources, 1):
            context_parts.append(
                f"[来源{i}] 文件:{s.get('source','')} 页码:{s.get('page','')}\n{s['content']}"
            )
        context = "\n\n".join(context_parts)

        # 构建提取 prompt（V6.0 加强版：JSON Schema + 多场景 few-shot）
        extract_prompt = f"""你是一个财务数据提取专家。从以下文档片段中提取用户查询所需的结构化数据。

## 用户查询
{query}

## 文档片段
{context}

## 核心规则（违反任何一条即为错误）
1. **只输出一个 JSON 对象，不要任何额外文字、解释、代码块标记**
2. 数值必须是纯数字，严禁带单位（"亿元""万元""%""元" 全部去掉）
3. 金额类统一转为「亿元」单位（原始为"万元"则÷10000，"元"则÷100000000）
4. 百分比类直接输出数值：92.38 而非 "92.38%" 或 "0.9238"
5. 数据结构必须扁平：用 "指标名_年份" 格式，不要嵌套对象
6. 如果文档中没有任何相关数据，found 设为 false，data 为空对象
7. confidence 取值范围 0.0-1.0，数据完整且来源明确时给 0.9+，部分缺失给 0.5-0.7

## Few-shot 示例（严格参照以下格式）

### 示例1：单年多指标
用户查询：贵州茅台2024年盈利指标
文档含：营业收入1709.90亿元，净利润862.28亿元，毛利率92.01%
输出：
{{"found":true,"data":{{"营业收入":1709.90,"净利润":862.28,"毛利率":92.01}},"summary":"贵州茅台2024年营收1709.90亿元，净利润862.28亿元，毛利率92.01%","confidence":0.92}}

### 示例2：多年单指标
用户查询：比亚迪2022-2024年营业收入变化
文档含：2022年4240.61亿元，2023年6023.15亿元，2024年7771.02亿元
输出：
{{"found":true,"data":{{"营业收入_2022":4240.61,"营业收入_2023":6023.15,"营业收入_2024":7771.02}},"summary":"比亚迪营收从2022年4240.61亿元增长至2024年7771.02亿元","confidence":0.95}}

### 示例3：数据缺失
用户查询：贵州茅台2024年EBITDA
文档中无EBITDA直接数据，也无折旧摊销数据可推算
输出：
{{"found":false,"data":{{}},"summary":"文档中未找到贵州茅台2024年EBITDA相关数据","confidence":0.0}}

## 现在请提取（只输出 JSON，不要代码块标记，不要任何解释）
"""

        try:
            messages = [
                {"role": "system", "content": (
                    "你是一个精确的财务数据提取专家。\n"
                    "铁律：只返回一行纯 JSON，不带 ``` 标记，不带任何解释文字。\n"
                    "数值必须是纯数字（无单位），金额统一亿元，百分比去 % 号。\n"
                    "违反格式 = 系统崩溃，请严格遵守。"
                )},
                {"role": "user", "content": extract_prompt},
            ]
            response = chat(messages, query=query, task_type=TaskType.SIMPLE)

            # 尝试解析 JSON（增强容错）
            import json
            import re as regex
            json_str = response.strip()
            # 处理 LLM 可能包裹的 ```json ... ``` 格式
            if json_str.startswith("```"):
                lines = json_str.split("\n")
                json_str = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            # 移除尾部多余字符（截断的 JSON 常见问题）
            json_str = json_str.rstrip().rstrip(",").rstrip()
            # 尝试找到最后一个完整的 }，截断后面的多余内容
            brace_count = 0
            last_valid_pos = 0
            for pos, ch in enumerate(json_str):
                if ch == "{":
                    brace_count += 1
                elif ch == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        last_valid_pos = pos + 1
            if last_valid_pos > 0 and last_valid_pos < len(json_str):
                json_str = json_str[:last_valid_pos]
            result = json.loads(json_str)
            return result

        except Exception as e:
            # 🔧 flash JSON 不稳定时的重试策略：先试 pro，再失败才降级正则
            first_error = str(e)
            try:
                logger.warning(f"Flash JSON 提取失败 ({first_error[:60]})，重试 pro 模型...")
                messages[0]["content"] = "你是一个精确的财务数据提取专家。只返回严格 JSON，不解释，不输出任何其他内容。"
                response_pro = chat(messages, query=query, task_type=TaskType.COMPLEX)
                json_str = response_pro.strip()
                if json_str.startswith("```"):
                    lines = json_str.split("\n")
                    json_str = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
                json_str = json_str.rstrip().rstrip(",").rstrip()
                result = json.loads(json_str)
                logger.info("Pro 模型重试成功")
                return result
            except Exception as retry_e:
                logger.warning(f"Pro 重试也失败: {retry_e}，最终降级正则提取")
                return self._regex_extract_numbers(query, sources)


    def _regex_extract_numbers(self, query: str, sources: List[dict]) -> dict:
        """
        正则兜底提取器：当 LLM JSON 解析失败时，用正则从 chunk 中提取数值。

        策略：
        1. 在检索到的 chunk 中查找 query 提到的财务术语
        2. 提取术语附近出现的数值（含单位）
        3. 构建简单的结构化数据
        """
        import re
        combined = " ".join([s["content"][:800] for s in sources[:3]])

        # 财务术语 → 数值的正则
        # 匹配模式：术语后面跟数字+单位
        # 例如："营业收入 1709.90亿元" → revenue: 1709.90
        patterns = [
            (r'(?:营业收入|营业总收入|营收)\D{0,10}?(\d+\.?\d*)\s*(?:亿元|万元|元)', '营业收入'),
            (r'(?:营业成本|成本)\D{0,10}?(\d+\.?\d*)\s*(?:亿元|万元|元)', '营业成本'),
            (r'(?:净利润|归[属母]净利润)\D{0,10}?(\d+\.?\d*)\s*(?:亿元|万元|元)', '净利润'),
            (r'(?:毛利率|销售毛利率)\D{0,5}?(\d+\.?\d*)\s*%', '毛利率'),
            (r'(?:净利率|销售净利率)\D{0,5}?(\d+\.?\d*)\s*%', '净利率'),
            (r'(?:ROE|净资产收益率)\D{0,5}?(\d+\.?\d*)\s*%', 'ROE'),
            (r'(?:资产负债率|负债率)\D{0,5}?(\d+\.?\d*)\s*%', '资产负债率'),
            (r'(?:总资产)\D{0,10}?(\d+\.?\d*)\s*(?:亿元|万元|元)', '总资产'),
            (r'(?:净资产|股东权益)\D{0,10}?(\d+\.?\d*)\s*(?:亿元|万元|元)', '净资产'),
            (r'(?:经营活动.*?现金流)\D{0,10}?(\d+\.?\d*)\s*(?:亿元|万元|元)', '经营现金流'),
            (r'(?:总负债)\D{0,10}?(\d+\.?\d*)\s*(?:亿元|万元|元)', '总负债'),
            (r'(?:流动资产)\D{0,10}?(\d+\.?\d*)\s*(?:亿元|万元|元)', '流动资产'),
            (r'(?:流动负债)\D{0,10}?(\d+\.?\d*)\s*(?:亿元|万元|元)', '流动负债'),
            (r'(?:研发费用|研发投入)\D{0,10}?(\d+\.?\d*)\s*(?:亿元|万元|元)', '研发费用'),
            (r'(?:基本每股收益|EPS)\D{0,10}?(\d+\.?\d*)\s*元', '基本每股收益'),
        ]

        data = {}
        found_any = False
        for pattern, key in patterns:
            match = re.search(pattern, combined)
            if match:
                try:
                    val = float(match.group(1))
                    data[key] = val
                    found_any = True
                except ValueError:
                    pass

        # 尝试提取年份区分的数据
        years = re.findall(r'(202[0-4])年.*?(\d+\.?\d*)', combined)
        year_data = {}
        for yr, num_str in years:
            try:
                year_data[yr] = float(num_str)
            except ValueError:
                pass

        summary = f"正则提取到 {len(data)} 个指标: {list(data.keys())[:5]}"
        if not found_any:
            summary = sources[0]["content"][:200] if sources else "无法提取数值"

        return {
            "found": found_any,
            "data": data,
            "summary": summary,
            "confidence": 0.3,
        }
