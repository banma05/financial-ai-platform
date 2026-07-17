"""
重建向量索引 — 加载 data/documents 下所有年报并重建 ChromaDB

用法:
    python scripts/rebuild_index.py  # 全量重建（删除旧库再建新的）
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from loguru import logger
from config import ROOT_DIR
from rag.loader import load_document
from rag.semantic_splitter import semantic_chunk_per_page
from rag.vector_store import add_documents, reset_database, get_document_list, wait_for_compaction

DOCUMENTS_DIR = ROOT_DIR / "data" / "documents"


def main():
    # 1. 重置数据库
    logger.info("=== 第一步：重置向量数据库 ===")
    reset_database()
    logger.success("数据库已清空")

    # 2. 扫描所有文档
    allowed_exts = {".pdf", ".docx", ".md", ".txt"}
    all_files = sorted(set(
        f.resolve() for f in DOCUMENTS_DIR.iterdir()
        if f.suffix.lower() in allowed_exts and f.name != ".gitkeep"
    ))

    logger.info(f"=== 第二步：发现 {len(all_files)} 个文档 ===")
    for f in all_files:
        logger.info(f"  📄 {f.name} ({f.stat().st_size / 1024 / 1024:.1f}MB)")

    # 3. 逐个加载 + 切分 + 入库
    total_chunks = 0
    for file_path in all_files:
        logger.info(f"\n--- 处理: {file_path.name} ---")
        try:
            pages = load_document(str(file_path))
            logger.info(f"  加载 {len(pages)} 页")
            chunks = semantic_chunk_per_page(pages)
            logger.info(f"  语义切分 {len(chunks)} 块")
            n = add_documents(chunks)
            total_chunks += n
            logger.success(f"  ✅ 入库 {n} 块")
        except Exception as e:
            logger.error(f"  ❌ 失败: {e}")

    # 4. 验证
    logger.info(f"\n=== 第三步：验证 ===")
    docs = get_document_list()
    for d in docs:
        logger.info(f"  📚 {d['filename']}: {d['chunk_count']} chunks, {d['page_count']} pages")
    logger.success(f"总计 {total_chunks} 个文本块，{len(docs)} 个文档")

    # 5. 确认 HNSW 索引落盘后再退出（防止退出打断 compaction 留下残缺 segment）
    logger.info("\n=== 第四步：确认索引落盘 ===")
    wait_for_compaction()


if __name__ == "__main__":
    main()
