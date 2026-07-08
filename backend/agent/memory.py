"""
用户长时记忆（V6.0）— 跨会话记住分析偏好

设计原则：
1. 轻量：只存公司和指标偏好，不存完整历史
2. 渐进：每次分析自动更新，不需要用户主动操作
3. 静默：失败不影响主流程
"""
from typing import Optional
from loguru import logger


KNOWN_COMPANIES = ["贵州茅台", "茅台", "比亚迪", "腾讯控股", "腾讯",
                   "五粮液", "宁德时代", "宁德", "阿里巴巴", "阿里", "京东", "美团"]

KNOWN_METRICS = ["毛利率", "净利率", "ROE", "ROA", "营收", "净利润", "现金流",
                 "资产负债率", "流动比率", "存货周转率", "营收增长率", "净利润增长率",
                 "杜邦分析", "每股收益", "市盈率", "市净率"]


class UserMemory:
    """用户偏好记忆：从分析请求中提取偏好，下次分析时自动注入"""

    def get_preferences(self, session_id: str) -> dict:
        """获取用户偏好"""
        from db import SessionLocal, UserPreference
        db = SessionLocal()
        try:
            pref = db.query(UserPreference).filter_by(session_id=session_id).first()
            if pref:
                return {
                    "preferred_company": pref.preferred_company or "",
                    "preferred_metrics": pref.preferred_metrics or "",
                }
            return {}
        except Exception as e:
            logger.debug(f"读取用户偏好失败: {e}")
            return {}
        finally:
            db.close()

    def update_from_query(self, session_id: str, user_input: str):
        """从用户查询中提取并更新偏好（增量合并）"""
        # 提取公司
        found_company = next((c for c in KNOWN_COMPANIES if c in user_input), "")
        # 提取指标
        found_metrics = [m for m in KNOWN_METRICS if m in user_input]

        if not found_company and not found_metrics:
            return

        from db import SessionLocal, UserPreference
        db = SessionLocal()
        try:
            pref = db.query(UserPreference).filter_by(session_id=session_id).first()
            if pref:
                if found_company and found_company != pref.preferred_company:
                    pref.preferred_company = found_company
                if found_metrics:
                    existing = set(pref.preferred_metrics.split(",")) if pref.preferred_metrics else set()
                    existing.update(found_metrics)
                    pref.preferred_metrics = ",".join(list(existing)[:5])  # 最多5个
            else:
                pref = UserPreference(
                    session_id=session_id,
                    preferred_company=found_company,
                    preferred_metrics=",".join(found_metrics[:5]),
                )
                db.add(pref)
            db.commit()
            logger.debug(f"用户偏好已更新: {found_company}, {found_metrics[:3]}")
        except Exception as e:
            db.rollback()
            logger.debug(f"更新用户偏好失败: {e}")
        finally:
            db.close()
