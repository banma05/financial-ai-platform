"""
MCP Server → 预留（阶段四 Docker 化独立进程）

当前阶段（三）MCP 工具作为 ToolRegistry 的注册类运行在 Agent 进程中。
阶段四将把此文件扩展为独立的 FastAPI/stdio MCP Server，通过 HTTP 与 Agent 通信。

架构预留：
    Agent 进程                      MCP 独立进程
    ┌─────────────┐     HTTP      ┌──────────────┐
    │ ToolRegistry │ ←──────────→ │ MCP Server    │
    │ MCPProxy     │              │ /tools/*      │
    └─────────────┘              └──────────────┘

当前此文件仅作结构占位，所有功能已在 backend/mcp/tools/ 中实现。
"""


def main():
    """MCP Server 入口（阶段四实现）"""
    print("MCP Server — 阶段四 Docker 化后启用")


if __name__ == "__main__":
    main()
