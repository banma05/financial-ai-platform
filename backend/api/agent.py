"""
数据分析 Agent API（模块二）

端点：
- POST /api/v1/agent/analyze        同步分析
- POST /api/v1/agent/analyze/stream SSE 流式分析（主要端点）
- GET  /api/v1/agent/templates      分析模板列表
- GET  /api/v1/agent/formulas       财务公式列表
"""
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from loguru import logger
import json

from models.schemas import AgentRequest, AgentResponse, TemplateInfo
from agent import run_agent_stream, run_agent_sync, BUILTIN_TEMPLATES, FORMULA_REGISTRY

router = APIRouter(prefix="/api/v1/agent", tags=["数据分析 Agent"])


@router.post("/analyze", response_model=AgentResponse)
async def analyze(request: AgentRequest):
    """
    同步分析 — 提交分析需求，等待完整结果返回。

    适合快速验证，正式使用建议走 /analyze/stream 流式接口。
    """
    try:
        result = run_agent_sync(
            user_input=request.query,
            session_id=request.session_id,
            template_name=request.template,
        )
        return AgentResponse(
            report=result.get("report", ""),
            charts=result.get("charts", []),
            chart_options=result.get("chart_options", []),
            processing_time=result.get("processing_time", 0),
            task_count=result.get("task_count", 0),
            clarification=result.get("clarification"),
        )
    except Exception as e:
        logger.error(f"Agent 分析失败: {e}")
        raise HTTPException(status_code=500, detail=f"分析失败: {str(e)}")


@router.post("/analyze/stream")
async def analyze_stream(req: AgentRequest, request: Request):
    """
    SSE 流式分析（主要端点）— 实时推送分析进度。

    事件类型：
    - plan_start:     {"type":"plan_start","task_count":5,"tasks":[...]}
    - task_start:     {"type":"task_start","task_id":"1","description":"..."}
    - task_complete:  {"type":"task_complete","task_id":"1","success":true,"summary":"..."}
    - chart:          {"type":"chart","chart_option":{...},"chart_index":1}
    - report_start:   {"type":"report_start"}
    - done:           {"type":"done","report":"...","charts":[...],"processing_time":12.5}
    - error:          {"type":"error","message":"..."}
    - clarification:  {"type":"clarification","question":"..."}

    V6.0: 支持客户端断开检测（request.is_disconnected()）
    """

    async def event_generator():
        try:
            for sse_event in run_agent_stream(
                user_input=req.query,
                session_id=req.session_id,
                template_name=req.template,
            ):
                yield sse_event
                # ── V6.0: 客户端断开则停止推送 ──
                if await request.is_disconnected():
                    logger.info(f"客户端断开连接: {req.session_id}")
                    break
        except Exception as e:
            logger.error(f"Agent SSE 流异常: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': f'分析服务异常: {str(e)}'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/templates", response_model=list[TemplateInfo])
async def list_templates():
    """列出可用的分析模板"""
    return [
        TemplateInfo(
            name=t["name"],
            display_name=t["display_name"],
            description=t["description"],
            category=t["category"],
        )
        for t in BUILTIN_TEMPLATES.values()
    ]


@router.get("/formulas")
async def list_formulas():
    """列出所有可用财务公式及其参数"""
    formulas = []
    for name, info in FORMULA_REGISTRY.items():
        formulas.append({
            "name": name,
            "display_name": info["display_name"],
            "category": info["category"],
            "formula_text": info["formula_text"],
            "params": info["params"],
            "unit": info["unit"],
        })
    return {"total": len(formulas), "formulas": formulas}


@router.get("/health")
async def agent_health():
    """Agent 模块健康检查"""
    return {
        "status": "ok",
        "templates": len(BUILTIN_TEMPLATES),
        "formulas": len(FORMULA_REGISTRY),
        "tools": 3,  # DataQuery + FinancialCalc + Chart
    }
