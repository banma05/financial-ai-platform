"""
知识库语料管理 — 增量更新 + 统计面板 + 质量检查

提供:
1. get_corpus_stats()      — 文档/分块/向量库统计
2. check_new_documents()   — 检测新增/修改的文档
3. incremental_rebuild()   — 增量索引更新（只处理变化文档）
4. validate_documents()    — 质量检查（空文档/重复/格式问题）
"""

import hashlib
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Set
from loguru import logger
from config import ROOT_DIR


DOCUMENTS_DIR = ROOT_DIR / "data" / "documents"
METADATA_FILE = ROOT_DIR / "data" / "corpus_metadata.json"
SNAPSHOTS_DIR = ROOT_DIR / "data" / "corpus_snapshots"


# ==================== 版本快照（简易版本管理） ====================

def save_snapshot(label: str = "") -> Dict:
    """
    保存当前知识库快照。可用于回滚参考。

    返回: {"snapshot_id", "timestamp", "document_count", "total_chunks", "label"}
    """
    import json as _json
    from rag.vector_store import get_document_list

    SNAPSHOTS_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    snap_id = f"snap_{timestamp}"
    if label:
        snap_id += f"_{label}"

    stats = get_corpus_stats()
    doc_list = get_document_list()

    snapshot = {
        "snapshot_id": snap_id,
        "timestamp": timestamp,
        "label": label or "",
        "document_count": stats["document_count"],
        "total_chunks": stats["total_chunks"],
        "documents": stats.get("documents", []),
        "indexed": [{"source": d.get("source", ""), "chunks": d.get("chunks", 0)} for d in doc_list],
    }

    snap_path = SNAPSHOTS_DIR / f"{snap_id}.json"
    snap_path.write_text(_json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info(f"[Corpus] 快照已保存: {snap_id} ({stats['document_count']}文档, {stats['total_chunks']}chunks)")
    return snapshot


def list_snapshots() -> List[Dict]:
    """列出所有版本快照"""
    if not SNAPSHOTS_DIR.exists():
        return []
    snaps = []
    for f in sorted(SNAPSHOTS_DIR.glob("snap_*.json"), reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            snaps.append({
                "snapshot_id": data.get("snapshot_id", f.stem),
                "timestamp": data.get("timestamp", ""),
                "label": data.get("label", ""),
                "document_count": data.get("document_count", 0),
                "total_chunks": data.get("total_chunks", 0),
            })
        except Exception as e:
            logger.debug(f"快照文件加载跳过: {e}")
    return snaps


def compare_snapshot(snap_id: str) -> Dict:
    """
    对比当前状态与某个快照。

    返回: {"added_docs": [...], "removed_docs": [...], "chunk_diff": N}
    """
    snap_path = SNAPSHOTS_DIR / f"{snap_id}.json"
    if not snap_path.exists():
        return {"error": f"快照不存在: {snap_id}"}

    old = json.loads(snap_path.read_text(encoding="utf-8"))
    current = get_corpus_stats()

    old_names = set(d.get("name", d.get("source", "")) for d in old.get("documents", []))
    cur_names = set(d.get("name", "") for d in current.get("documents", []))

    return {
        "snapshot": snap_id,
        "current_documents": current["document_count"],
        "snapshot_documents": old.get("document_count", 0),
        "chunk_diff": current["total_chunks"] - old.get("total_chunks", 0),
        "added_docs": list(cur_names - old_names),
        "removed_docs": list(old_names - cur_names),
    }


# ==================== 文档统计 ====================

def get_corpus_stats() -> Dict:
    """获取知识库统计信息"""
    from rag.vector_store import get_document_list

    docs_dir = DOCUMENTS_DIR
    if not docs_dir.exists():
        return {"error": "文档目录不存在", "document_count": 0, "total_chunks": 0}

    # 文档文件列表
    files = sorted([f for f in docs_dir.iterdir() if f.is_file() and not f.name.startswith(".")])

    # 向量库信息
    try:
        doc_list = get_document_list()
        total_chunks = sum(d.get("chunks", 0) for d in doc_list)
    except Exception as e:
        logger.warning(f"ChromaDB 信息获取失败, 回退空列表: {e}")
        doc_list = []
        total_chunks = 0

    # 文件统计
    total_size = sum(f.stat().st_size for f in files)
    by_type = {}
    for f in files:
        ext = f.suffix.lower()
        by_type[ext] = by_type.get(ext, 0) + 1

    # 最后更新时间
    last_modified = max((f.stat().st_mtime for f in files), default=0)

    return {
        "document_count": len(files),
        "total_chunks": total_chunks,
        "total_size_mb": round(total_size / 1024 / 1024, 1),
        "by_type": by_type,
        "last_modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(last_modified)),
        "indexed_documents": len(doc_list),
        "documents": [{
            "name": f.name,
            "size_mb": round(f.stat().st_size / 1024 / 1024, 1),
            "modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(f.stat().st_mtime)),
            "hash": _file_hash(str(f)),
        } for f in files],
    }


# ==================== 增量更新 ====================

def check_new_documents() -> Dict:
    """
    检测新增和修改的文档。

    返回:
        {"new": [...], "modified": [...], "deleted": [...], "unchanged": [...]}
    """
    docs_dir = DOCUMENTS_DIR
    if not docs_dir.exists():
        return {"new": [], "modified": [], "deleted": [], "unchanged": []}

    current_files = {f.name: str(f) for f in docs_dir.iterdir()
                     if f.is_file() and not f.name.startswith(".")}
    previous = _load_metadata()

    new_files = []
    modified_files = []
    unchanged_files = []
    deleted_files = []

    # 检测新增和修改
    for name, path in current_files.items():
        file_hash = _file_hash(path)
        if name not in previous:
            new_files.append({"name": name, "path": path, "hash": file_hash})
        elif previous[name] != file_hash:
            modified_files.append({"name": name, "path": path, "hash": file_hash})
        else:
            unchanged_files.append({"name": name, "path": path, "hash": file_hash})

    # 检测删除
    for name in previous:
        if name not in current_files:
            deleted_files.append({"name": name})

    result = {
        "new": new_files,
        "modified": modified_files,
        "deleted": deleted_files,
        "unchanged": unchanged_files,
        "summary": (f"新增 {len(new_files)} | 修改 {len(modified_files)} | "
                    f"删除 {len(deleted_files)} | 不变 {len(unchanged_files)}"),
    }

    # 保存当前快照
    _save_metadata(current_files)

    logger.info(f"[Corpus] {result['summary']}")
    return result


def incremental_rebuild() -> Dict:
    """增量重建索引（只处理变化的文档）"""
    from rag.loader import load_document
    from rag.semantic_splitter import semantic_chunk_per_page
    from rag.vector_store import add_documents, delete_document, get_document_list

    changes = check_new_documents()
    total_processed = 0

    # 删除已移除的文档
    for doc in changes["deleted"]:
        try:
            delete_document(doc["name"])
            logger.info(f"[Corpus] 已删除: {doc['name']}")
        except Exception as e:
            logger.warning(f"[Corpus] 删除失败 {doc['name']}: {e}")

    # 处理新增和修改
    for doc in changes["new"] + changes["modified"]:
        try:
            # 如果是修改，先删旧索引
            if doc in changes["modified"]:
                try:
                    delete_document(doc["name"])
                except Exception as e:
                    logger.warning(f"删除旧文档失败({doc['name']}): {e}")

            # 加载和分块
            file_path = doc["path"]
            pages = load_document(file_path)
            chunks = semantic_chunk_per_page(pages, source_name=doc["name"])
            if chunks:
                add_documents(chunks, source=doc["name"])
                total_processed += len(chunks)
                logger.info(f"[Corpus] 已索引: {doc['name']} → {len(chunks)} chunks")
        except Exception as e:
            logger.error(f"[Corpus] 索引失败 {doc['name']}: {e}")

    return {
        **changes,
        "total_chunks_added": total_processed,
    }


# ==================== 质量检查 ====================

def validate_documents() -> Dict:
    """
    文档质量检查。

    检查项:
    - 空文件（< 100 字节）
    - 文件大小异常（> 50MB 或 < 1KB）
    - 文件名包含特殊字符
    - 未索引文档
    """
    docs_dir = DOCUMENTS_DIR
    if not docs_dir.exists():
        return {"error": "文档目录不存在"}

    from rag.vector_store import get_document_list
    indexed_names = set(d.get("source", "") for d in get_document_list())

    issues = []
    warnings = []

    for f in docs_dir.iterdir():
        if not f.is_file() or f.name.startswith("."):
            continue

        size = f.stat().st_size

        # 空文件检查
        if size < 100:
            issues.append({"file": f.name, "issue": "疑似空文件", "detail": f"大小仅 {size} 字节"})

        # 超大文件检查
        if size > 50 * 1024 * 1024:
            warnings.append({"file": f.name, "issue": "文件过大", "detail": f"{size / 1024 / 1024:.0f}MB，可能影响加载速度"})

        # 文件名检查
        if any(c in f.name for c in ('"', "'", "\\", ":", "?", "<", ">", "|")):
            warnings.append({"file": f.name, "issue": "文件名含特殊字符"})

        # 未索引检查
        if indexed_names and f.name not in indexed_names and f.suffix.lower() != ".gitkeep":
            warnings.append({"file": f.name, "issue": "未被索引", "detail": "运行 scripts/rebuild_index.py 重建索引"})

    return {
        "total_documents": len(list(docs_dir.iterdir())),
        "indexed_documents": len(indexed_names),
        "issues": issues,
        "warnings": warnings,
        "is_healthy": len(issues) == 0,
        "summary": f"已索引 {len(indexed_names)} 份，{len(issues)} 个问题，{len(warnings)} 个警告",
    }


# ==================== 工具函数 ====================

def _file_hash(path: str) -> str:
    """计算文件的 MD5 哈希"""
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _load_metadata() -> Dict[str, str]:
    """加载上次索引快照"""
    if METADATA_FILE.exists():
        try:
            return json.loads(METADATA_FILE.read_text(encoding="utf-8"))
        except Exception as e:
            logger.debug(f"元数据文件读取失败: {e}")
    return {}


def _save_metadata(files: Dict[str, str]):
    """保存当前文件哈希快照"""
    hashes = {name: _file_hash(path) for name, path in files.items()}
    METADATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    METADATA_FILE.write_text(json.dumps(hashes, ensure_ascii=False, indent=2), encoding="utf-8")
