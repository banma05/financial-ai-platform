"""测试 utils.text — JSON 清理工具函数"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.text import clean_json_response, parse_llm_json


def test_clean_with_code_block():
    """带 ```json 包裹"""
    result = parse_llm_json('```json\n{"a": 1}\n```')
    assert result == {"a": 1}


def test_clean_with_trailing_text():
    """JSON 后跟解释文字"""
    result = parse_llm_json('{"a": 1}以上是提取结果')
    assert result == {"a": 1}


def test_clean_with_trailing_comma():
    """尾部有逗号"""
    result = parse_llm_json('{"a": 1,}')
    assert result == {"a": 1}


def test_clean_plain_json():
    """纯 JSON"""
    result = parse_llm_json('{"a": 1}')
    assert result == {"a": 1}


def test_clean_nested_json():
    """嵌套 JSON"""
    result = parse_llm_json('{"tasks": [{"id": 1}, {"id": 2}]}')
    assert result == {"tasks": [{"id": 1}, {"id": 2}]}


def test_clean_with_incomplete():
    """JSON 被截断但有完整闭合：只取完整部分"""
    result = parse_llm_json('{"a": 1}{"b": 2}')
    assert result == {"a": 1}


if __name__ == "__main__":
    import io, sys as _sys
    if _sys.platform == "win32":
        _sys.stdout = io.TextIOWrapper(_sys.stdout.buffer, encoding="utf-8", errors="replace")

    tests = [
        test_clean_with_code_block,
        test_clean_with_trailing_text,
        test_clean_with_trailing_comma,
        test_clean_plain_json,
        test_clean_nested_json,
        test_clean_with_incomplete,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"[PASS] {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"[FAIL] {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} 通过")
