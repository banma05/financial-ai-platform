"""
RAG 相关 API 路由
"""
import os
from fastapi import APIRouter, UploadFile, File, HTTPException
from loguru import logger

from config import UPLOAD_DIR, MAX_FILE_SIZE_MB
from models.schemas import (
    ChatRequest,
    ChatResponse,
    DocumentInfo,
    DocumentListResponse,
    DocumentUploadResponse,
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
