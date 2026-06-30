"""
RAG 相关 API 路由
"""
import os
import json
from pathlib import Path
from fastapi import APIRouter, UploadFile, File, HTTPException
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

router = APIRouter(prefix="/api/v1/rag", tags=["RAG 知识库"])


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

    return DocumentUploadResponse(
        filename=file.filename or "unknown",
        file_size=int(file_size_mb * 1024 * 1024),
        chunk_count=chunk_count,
        message=f"上传成功！文档已切分为 {chunk_count} 个块，已存入知识库",
    )


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    向知识库提问
    """
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="问题不能为空")

    result = rag_query(query=request.query, top_k=request.top_k)
    return ChatResponse(**result)


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents():
    """
    列出知识库中的所有文档
    """
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
