#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

DETACH=1
BUILD=1
FOLLOW_API_LOGS=0
WAIT_API=1

usage() {
  cat <<'EOF'
用法：scripts/start_backend_stack.sh [选项]

启动 KGTraceVis 后端全套服务：
- neo4j
- postgres
- postgres-init
- kg-import
- api

选项：
  --no-detach     前台启动（默认后台启动）
  --no-build      不执行 docker build
  --logs          启动后跟随 api 日志
  --no-wait       不等待 /api/health 就绪
  -h, --help      显示帮助
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-detach)
      DETACH=0
      shift
      ;;
    --no-build)
      BUILD=0
      shift
      ;;
    --logs)
      FOLLOW_API_LOGS=1
      shift
      ;;
    --no-wait)
      WAIT_API=0
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "未知参数：$1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
else
  echo "未找到 docker compose / docker-compose。" >&2
  if command -v brew >/dev/null 2>&1; then
    cat >&2 <<'EOF'

你当前可以二选一：

方案 A（最省事，推荐）安装 Docker Desktop：
  brew install --cask docker
  open -a Docker

等待 Docker Desktop 启动完成后，再执行：
  ./run

方案 B（不装 Docker Desktop，走 Colima）：
  brew install docker docker-compose colima
  colima start

然后再执行：
  ./run
EOF
  else
    echo "请先安装 Docker Desktop，或安装 docker compose / docker-compose 后重试。" >&2
  fi
  exit 1
fi

SERVICES=(neo4j postgres postgres-init kg-import api)
UP_ARGS=(up)
if [[ "$BUILD" -eq 1 ]]; then
  UP_ARGS+=(--build)
fi
if [[ "$DETACH" -eq 1 ]]; then
  UP_ARGS+=(-d)
fi
UP_ARGS+=("${SERVICES[@]}")

echo "[KGTraceVis] 项目根目录：$ROOT_DIR"
echo "[KGTraceVis] 启动服务：${SERVICES[*]}"
"${COMPOSE[@]}" "${UP_ARGS[@]}"

if [[ "$DETACH" -eq 0 ]]; then
  exit 0
fi

echo
echo "[KGTraceVis] 当前服务状态："
"${COMPOSE[@]}" ps

if [[ "$WAIT_API" -eq 1 ]]; then
  echo
  echo "[KGTraceVis] 等待 API 就绪：http://127.0.0.1:8000/api/health"
  if command -v curl >/dev/null 2>&1; then
    READY=0
    for _ in $(seq 1 60); do
      if curl -fsS http://127.0.0.1:8000/api/health >/dev/null 2>&1; then
        READY=1
        break
      fi
      sleep 2
    done
    if [[ "$READY" -eq 1 ]]; then
      echo "[KGTraceVis] API 已就绪。"
    else
      echo "[KGTraceVis] API 尚未就绪，可执行下面命令排查：" >&2
      echo "  ${COMPOSE[*]} logs api" >&2
    fi
  else
    echo "[KGTraceVis] 系统未安装 curl，跳过 API 就绪检查。"
  fi
fi

echo
echo "[KGTraceVis] 访问地址："
echo "  API:           http://127.0.0.1:8000"
echo "  Swagger:       http://127.0.0.1:8000/docs"
echo "  Neo4j Browser: http://127.0.0.1:7474"
echo "  Postgres:      localhost:5432"
echo

echo "[KGTraceVis] 常用命令："
echo "  查看日志: ${COMPOSE[*]} logs -f api"
echo "  停止服务: ${COMPOSE[*]} down"

if [[ "$FOLLOW_API_LOGS" -eq 1 ]]; then
  echo
  echo "[KGTraceVis] 跟随 api 日志..."
  "${COMPOSE[@]}" logs -f api
fi
