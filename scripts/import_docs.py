"""
增量导入脚本 — 仅处理新增/修改的文档，不动已有索引

用法:
    python scripts/import_docs.py            # 增量导入新文档
    python scripts/import_docs.py --dry-run  # 仅检测，不导入
    python scripts/import_docs.py --force    # 强制重新索引所有文档
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from loguru import logger
from rag.corpus_manager import check_new_documents, incremental_rebuild
from config import ROOT_DIR

DOCUMENTS_DIR = ROOT_DIR / "data" / "documents"


def main():
    args = set(sys.argv[1:])

    # 1. 检测变化
    logger.info("=== 扫描文档变化 ===")
    changes = check_new_documents()
    logger.info(f"结果: {changes['summary']}")

    if changes["new"]:
        logger.info("新增文件:")
        for d in changes["new"]:
            size_mb = Path(d["path"]).stat().st_size / 1024 / 1024
            logger.info(f"  📄 {d['name']} ({size_mb:.1f}MB)")

    if changes["modified"]:
        logger.info("修改文件:")
        for d in changes["modified"]:
            logger.info(f"  ✏️ {d['name']}")

    if changes["deleted"]:
        logger.info("已删除文件:")
        for d in changes["deleted"]:
            logger.info(f"  🗑️ {d['name']}")

    if "--dry-run" in args:
        logger.info("Dry-run 模式，不执行导入")
        return

    # 2. 导入
    if not changes["new"] and not changes["modified"] and not changes["deleted"]:
        logger.info("无变化，跳过")
        return

    if "--force" in args:
        logger.info("强制模式：重置后全量重建")
        from rag.vector_store import reset_database
        reset_database()
        # 清空元数据让所有文件被检测为新文件
        from rag.corpus_manager import _save_metadata
        _save_metadata({})
        changes = check_new_documents()

    logger.info("=== 开始增量导入 ===")
    result = incremental_rebuild()

    # 3. 输出结果
    logger.success(f"导入完成: {result.get('total_chunks_added', 0)} 个新 chunks")
    if result.get("new"):
        logger.success(f"新增文档: {[d['name'] for d in result['new']]}")

    # 4. 确认 HNSW 索引落盘后再退出（防止退出打断 compaction 留下残缺 segment）
    from rag.vector_store import wait_for_compaction
    wait_for_compaction()


if __name__ == "__main__":
    main()
