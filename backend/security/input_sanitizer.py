"""
LLM 输入净化器 — 所有用户输入进入 LLM 前必须经过此层。

设计原则：
- 不拒绝请求：清洗而非阻断，注入特征被替换为无害标记
- 多层防护：正则清洗 + XML 硬隔离 + System Prompt 铁律优先级
- 日志可审计：检测到注入时记录 warning 级别日志

面试亮点：V9.1 主动识别了 Planner/DataQuery/RAG 三个 LLM 注入点的
全链路风险，建立了从输入到输出的三层 Prompt 注入防护体系。
"""

import re
import logging

logger = logging.getLogger(__name__)


class InputSanitizer:
    """防止用户通过自然语言注入覆盖系统指令"""

    # 中英文注入特征模式 → 替换标记
    _INJECTION_PATTERNS: list[tuple[str, str]] = [
        # ── 中文注入 ──
        (r"忽略.{0,10}(以上|之前|前面|所有)(的)?(指令|规则|要求|提示|限制|约束)", "[已过滤-指令覆盖]"),
        (r"(不要|禁止|不准|停止|拒绝).{0,5}(遵守|遵循|执行|按照|服从)", "[已过滤-规则否定]"),
        (r"(你|现在)(是|作为|扮演|充当).{0,15}(模型|角色|AI|助手|专家|机器人)", "[已过滤-角色覆盖]"),
        (r"(输出|显示|打印|告诉我|透露|泄露).{0,10}(系统|原始|内部|隐藏).{0,5}(提示|指令|prompt|规则)", "[已过滤-信息泄露]"),
        (r"\[SYSTEM\]|\[INST\]|\[PROMPT\]|<\|im_start\|>|<\|im_end\|>", "[已过滤-标记注入]"),
        (r"(忘记|清除|重置|覆盖).{0,5}(之前|以上|前面|上面)?(的|所有)?(对话|指令|规则|设定|历史)", "[已过滤-上下文覆盖]"),
        # ── 英文注入 ──
        (r"ignore\s+(all|everything\s+)?(previous|above|prior)\s+(instructions?|prompts?|rules?|constraints?)", "[已过滤-指令覆盖]"),
        (r"(you\s+are(\s+now)?|act\s+as|you're|you\s+now)\s+(a\s+)?(model|ai|assistant|system|chatbot)", "[已过滤-角色覆盖]"),
        (r"(print|show|reveal|output|display|tell\s+me)\s+(your\s+)?(system\s+)?(prompt|instructions?|rules?)", "[已过滤-信息泄露]"),
        (r"(forget|ignore|disregard|override|clear)\s+(all\s+|everything\s+)?(previous|earlier|above|prior)", "[已过滤-上下文覆盖]"),
        (r"(do\s+not|don't|never|stop)\s+(follow|obey|comply)", "[已过滤-规则否定]"),
    ]

    @classmethod
    def sanitize(cls, user_input: str) -> tuple[str, bool]:
        """
        清洗注入模式，返回 (清洗后文本, 是否检测到注入)。

        不拒绝请求——替换注入关键词为无害标记，保持对话连续性。
        """
        cleaned = user_input
        detected = False

        for pattern, replacement in cls._INJECTION_PATTERNS:
            if re.search(pattern, cleaned, re.IGNORECASE):
                logger.warning(f"[安全] 检测到潜在 Prompt 注入模式: {pattern}")
                cleaned = re.sub(pattern, replacement, cleaned, flags=re.IGNORECASE)
                detected = True

        return cleaned, detected

    @classmethod
    def wrap(cls, user_input: str) -> str:
        """
        清洗并用 XML 标签硬隔离用户输入（幂等：已包裹的不重复包裹）。

        XML 标签在 LLM 训练数据中天然具有结构化语义，
        相比自然语言分隔符（如 "---用户输入---"），
        更难以通过自然语言注入绕过。

        V9.1 修复: 防止 Planner→DataQuery→RAG 链路上的三重包裹，
        避免 XML 标签污染 BM25/向量检索关键词。
        """
        # 幂等性：已包裹的不重复包裹
        if user_input.strip().startswith("<user_query>") and "</user_query>" in user_input:
            return user_input

        cleaned, detected = cls.sanitize(user_input)
        if detected:
            logger.warning(f"[安全] 输入已净化，原始: {user_input[:100]}...")
        return f"<user_query>\n{cleaned}\n</user_query>"
