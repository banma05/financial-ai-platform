#!/bin/bash
# ============================================================
# Docker 健康检查脚本 (V8.2)
#
# 用法: bash scripts/docker-health.sh
#
# 检查三服务的健康状态和连通性
# ============================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

check() {
    local name="$1" url="$2"
    if curl -sf "$url" > /dev/null 2>&1; then
        echo -e "${GREEN}✅${NC} $name: $url"
        return 0
    else
        echo -e "${RED}❌${NC} $name: $url 不可达"
        return 1
    fi
}

echo "=== 智能财务分析平台 — Docker 健康检查 ==="
echo ""

FAILS=0

check "Redis   " "http://localhost:6379" || true  # Redis 用 TCP 不是 HTTP
# Redis ping via redis-cli in container
if docker exec fa-redis redis-cli ping > /dev/null 2>&1; then
    echo -e "${GREEN}✅${NC} Redis PING 正常"
else
    echo -e "${RED}❌${NC} Redis PING 失败"
    FAILS=$((FAILS + 1))
fi

check "Backend " "http://localhost:8001/health" || FAILS=$((FAILS + 1))
check "Frontend" "http://localhost/"                || FAILS=$((FAILS + 1))

echo ""
if [ $FAILS -eq 0 ]; then
    echo -e "${GREEN}全部服务健康 ✅${NC}"
    echo "访问: http://localhost/"
else
    echo -e "${RED}${FAILS} 个服务异常${NC}"
    echo "查看日志: docker-compose logs -f"
fi

exit $FAILS
