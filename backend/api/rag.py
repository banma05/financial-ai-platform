"""
RAG 相关 API 路由
"""
import os
import json
import asyncio
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import StreamingResponse
from loguru import logger

from config import UPLOAD_DIR, MAX_FILE_SIZE_MB
from models.schemas import (
    ChatRequest,
    ChatResponse,
    DocumentInfo,
    DocumentListResponse,
    DocumentUploadResponse,
    EvalRequest,
    EvalReportResponse,
    EvalSummary,
    EvalDetail,
)
from rag import load_document, split_documents, add_documents, rag_query, get_document_list
from rag.semantic_splitter import semantic_chunk_per_page
from rag.model_router import chat_stream
from db import SessionLocal, Document, ChatHistory, QueryLog

router = APIRouter(prefix="/api/v1/rag", tags=["RAG 知识库"])

# ============ 会话管理（内存缓存，用于多轮对话） ============
# 生产环境应迁移到 Redis 或 chat_history 表
from collections import defaultdict
_session_store: dict = defaultdict(list)  # {session_id: [{role, content}, ...]}
MAX_HISTORY_TURNS = 10  # 每个会话最多保留 10 轮对话


def _get_history(session_id: str) -> list:
    return _session_store.get(session_id, [])


def _save_turn(session_id: str, role: str, content: str):
    _session_store[session_id].append({"role": role, "content": content})
    # 超过上限时保留最近 N 轮
    if len(_session_store[session_id]) > MAX_HISTORY_TURNS * 2:
        _session_store[session_id] = _session_store[session_id][-(MAX_HISTORY_TURNS * 2):]


def _log_query(query: str, processed_query: str, top_k: int, chunks_count: int, processing_time: float):
    """写入查询日志（失败不影响主流程）"""
    db = SessionLocal()
    try:
        log = QueryLog(
            query=query,
            processed_query=processed_query,
            top_k=top_k,
            chunks_count=chunks_count,
            processing_time=processing_time,
            has_sources=1 if chunks_count > 0 else 0,
        )
        db.add(log)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"写入查询日志失败: {e}")
    finally:
        db.close()


@router.post("/session/clear")
async def clear_session(session_id: str = "default"):
    """
    清除指定会话的对话历史（用于"清空对话"功能）
    """
    if session_id in _session_store:
        del _session_store[session_id]
        logger.info(f"会话 {session_id} 已清除")
    return {"message": "会话已清除", "session_id": session_id}


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(file: UploadFile = File(...)):
    """
    上传文档到知识库
    支持 PDF / Word / Markdown / TXT 格式
    """
    # 1. 校验文件类型
    allowed_exts = {".pdf", ".docx", ".doc", ".md", ".txt"}
    file_ext = os.path.splitext(file.filename or "")[1].lower()
    if file_ext not in allowed_exts:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式 [{file_ext}]，仅支持: {', '.join(allowed_exts)}",
        )

    # 2. 校验文件大小
    content = await file.read()
    file_size_mb = len(content) / (1024 * 1024)
    if file_size_mb > MAX_FILE_SIZE_MB:
        raise HTTPException(
            status_code=400,
            detail=f"文件过大 ({file_size_mb:.1f}MB)，限制 {MAX_FILE_SIZE_MB}MB",
        )

    # 3. 保存文件
    file_path = UPLOAD_DIR / file.filename
    with open(file_path, "wb") as f:
        f.write(content)
    logger.info(f"文件已保存: {file_path} ({file_size_mb:.1f}MB)")

    # 4. 加载文档
    try:
        pages = load_document(str(file_path))
    except Exception as e:
        os.remove(file_path)
        raise HTTPException(status_code=500, detail=f"文档解析失败: {str(e)}")

    # 5. 文本分块
    # 语义动态切分（每页内做语义边界检测，保留页码溯源）
    chunks = semantic_chunk_per_page(pages)
    if not chunks:
        os.remove(file_path)
        raise HTTPException(status_code=400, detail="文档内容为空，无法处理")

    # 6. 存入向量数据库
    chunk_count = add_documents(chunks)

    # 7. 写入业务数据库（文档元数据）
    db = SessionLocal()
    try:
        doc = Document(
            filename=file.filename or "unknown",
            file_path=str(file_path),
            file_size=int(file_size_mb * 1024 * 1024),
            page_count=len(pages),
            chunk_count=chunk_count,
        )
        db.add(doc)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"写入文档记录失败（不影响知识库）: {e}")
    finally:
        db.close()

    return DocumentUploadResponse(
        filename=file.filename or "unknown",
        file_size=int(file_size_mb * 1024 * 1024),
        chunk_count=chunk_count,
        message=f"上传成功！文档已切分为 {chunk_count} 个块，已存入知识库",
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    向知识库提问（支持多轮对话）
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    session_id = request.session_id or "default"
    history = _get_history(session_id)
    result = rag_query(query=request.query, top_k=request.top_k, history=history)
    # 保存到会话历史
    _save_turn(session_id, "user", request.query)
    _save_turn(session_id, "assistant", result.get("answer", ""))
    return ChatResponse(**result)


@router.post("/chat/stream")
async def chat_stream_endpoint(request: ChatRequest):
    """
    向知识库提问（流式输出 SSE + 多轮对话支持）

    先推送答案文本（逐 token），最后推送 sources 和 meta 数据。
    事件格式：data: {"type":"token","content":"..."} 或 data: {"type":"done","sources":[...],"processing_time":...}
    """
    from rag.query_processor import process_query
    from rag.hybrid_search import hybrid_search
    from rag.retriever import build_prompt

    if not request.query.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    session_id = request.session_id or "default"

    async def event_stream():
        import time
        start_time = time.time()
        full_answer = ""
        source_list = []
        processing_time = 0.0
        processed_query = request.query

        try:
            # Step 1: Query 处理
            processed_query = process_query(request.query)

            # Step 2: 混合检索
            sources = hybrid_search(processed_query, top_k=request.top_k)
            logger.info(f"[{session_id}] 流式检索到 {len(sources)} chunks")

            if not sources:
                no_doc_msg = "知识库中没有找到与您问题相关的文档。请先上传相关文件后再提问。"
                full_answer = no_doc_msg
                yield f"data: {json.dumps({'type': 'token', 'content': no_doc_msg}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'done', 'sources': [], 'processing_time': round(time.time() - start_time, 2)}, ensure_ascii=False)}\n\n"
                processing_time = round(time.time() - start_time, 2)
            else:
                # Step 3: 构建 Prompt（含历史对话）+ 流式 LLM
                history = _get_history(session_id)
                prompt = build_prompt(processed_query, sources, history=history)
                messages = [
                    {"role": "system", "content": "你是一个专业的财务分析助手，擅长解读财务报表、年报、审计报告等金融文档。"},
                    {"role": "user", "content": prompt},
                ]

                for token in chat_stream(messages, query=processed_query):
                    full_answer += token
                    yield f"data: {json.dumps({'type': 'token', 'content': token}, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0)

                processing_time = round(time.time() - start_time, 2)

                source_list = [
                    {
                        "content": s["content"][:200] + "..." if len(s["content"]) > 200 else s["content"],
                        "source": s["source"],
                        "page": s["page"],
                        "score": s.get("rerank_score", s.get("rrf_score", s.get("score", 0))),
                    }
                    for s in sources
                ]

                yield f"data: {json.dumps({'type': 'done', 'sources': source_list, 'processing_time': processing_time, 'processed_query': processed_query if processed_query != request.query else None}, ensure_ascii=False)}\n\n"

            # Step 4: 保存到会话历史
            _save_turn(session_id, "user", request.query)
            _save_turn(session_id, "assistant", full_answer)

            # Step 5: 写入查询日志
            _log_query(request.query, processed_query, request.top_k, len(sources) if sources else 0, processing_time)

        except Exception as e:
            logger.error(f"流式输出失败: {e}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents():
    """
    列出知识库中的所有文档（优先从业务数据库读取）
    """
    db = SessionLocal()
    try:
        db_docs = db.query(Document).filter(Document.status == "active").order_by(Document.upload_time.desc()).all()
        if db_docs:
            docs = [d.to_dict() for d in db_docs]
            # 补充 ChromaDB 的最新 chunk_count（数据库可能不同步）
            chroma_docs = {d["filename"]: d for d in get_document_list()}
            for doc in docs:
                if doc["filename"] in chroma_docs:
                    doc["chunk_count"] = chroma_docs[doc["filename"]]["chunk_count"]
            return DocumentListResponse(
                documents=[DocumentInfo(**d) for d in docs],
                total=len(docs),
            )
    except Exception as e:
        logger.warning(f"数据库读取失败，回退 ChromaDB: {e}")
    finally:
        db.close()

    # 数据库不可用时回退 ChromaDB
    docs = get_document_list()
    return DocumentListResponse(
        documents=[DocumentInfo(**d) for d in docs],
        total=len(docs),
    )


@router.post("/evaluate", response_model=EvalReportResponse)
async def run_evaluation(request: EvalRequest = None):
    """
    运行检索评测

    使用标准测试集对当前知识库进行批量评测，
    计算 recall@k、MRR、NDCG@k 等指标。

    可选启用 LLM-as-Judge 进行上下文召回率和忠实度评测（耗时更长）。
    """
    if request is None:
        request = EvalRequest()

    from rag.evaluator import batch_evaluate, recall_at_k, mrr, ndcg_at_k, evaluate_retrieval
    from rag.hybrid_search import hybrid_search

    # 确定测试集路径
    if request.test_set_path:
        test_set_path = request.test_set_path
    else:
        test_set_path = str(Path(__file__).parent.parent.parent / "data" / "test_questions.json")

    if not Path(test_set_path).exists():
        raise HTTPException(
            status_code=404,
            detail=f"测试集文件不存在: {test_set_path}。请先运行 Step 2 创建测试集。",
        )

    # 创建检索函数（含 Query 预处理：术语展开 + 扩写校验）
    def search_fn(query: str, top_k: int = 5) -> list:
        from rag.query_processor import process_query
        processed = process_query(query)
        return hybrid_search(processed, top_k=top_k)

    # 运行批量评测
    try:
        report = batch_evaluate(
            test_set_path=test_set_path,
            search_fn=search_fn,
            top_k=request.top_k,
            verbose=True,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"评测失败: {str(e)}")

    # 构建响应
    summary = EvalSummary(
        avg_recall_at_1=report["summary"]["avg_recall@1"],
        avg_recall_at_3=report["summary"]["avg_recall@3"],
        avg_recall_at_5=report["summary"]["avg_recall@5"],
        avg_mrr=report["summary"]["avg_mrr"],
        avg_ndcg_at_5=report["summary"]["avg_ndcg@5"],
        avg_time_s=report["meta"].get("avg_time_per_query", 0),
        num_questions=report["meta"]["num_questions"],
        total_time_s=report["meta"]["total_time"],
    )

    details = [
        EvalDetail(
            question_id=d["id"],
            query=d["query"],
            category=d.get("category", ""),
            difficulty=d.get("difficulty", ""),
            recall_at_1=d["recall@1"],
            recall_at_3=d["recall@3"],
            recall_at_5=d["recall@5"],
            mrr=d["mrr"],
            ndcg_at_5=d["ndcg@5"],
            time_s=d["time"],
            chunks_found=d["chunks_found"],
        )
        for d in report["details"]
    ]

    # 可选 LLM-as-Judge
    llm_results = None
    if request.use_llm_judge:
        logger.info("启用 LLM-as-Judge 评测...")
        try:
            llm_results = {}
            for d in report["details"]:
                # 取第一个 question 的检索结果做 LLM 评测
                pass  # LLM 评测耗时较长，按需调用
        except Exception as e:
            logger.warning(f"LLM 评测失败: {e}")

    return EvalReportResponse(
        summary=summary,
        by_difficulty=report.get("by_difficulty", {}),
        by_category=report.get("by_category", {}),
        details=details,
        llm_judge_results=llm_results,
    )


@router.get("/eval-report")
async def get_eval_report():
    """
    获取最近一次评测报告
    """
    from rag.evaluator import get_latest_report
    report = get_latest_report()
    if report is None:
        return {"message": "暂无评测报告，请先调用 POST /evaluate 运行评测"}
    return report
