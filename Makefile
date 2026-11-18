# 叩门 · 社工个案面谈 AI 陪练舱 —— 常用命令
#
# 依赖：Python 3.12、Node 20、MySQL 8.0
# 首次使用：make install

.PHONY: help install install-backend install-frontend dev backend frontend build test lint \
        audit audit-all migrate seed clean docker-up docker-down

BACKEND := deliverables/backend
FRONTEND := frontend
PY := python

help:  ## 显示所有可用命令
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ── 安装 ────────────────────────────────────────────────────
install: install-backend install-frontend  ## 安装前后端依赖

install-backend:  ## 安装后端依赖（含测试工具）
	cd $(BACKEND) && $(PY) -m pip install -r requirements-dev.txt

install-frontend:  ## 安装前端依赖
	cd $(FRONTEND) && npm ci

# ── 开发 ────────────────────────────────────────────────────
dev:  ## 同时起后端与前端开发服务器
	@echo "后端 http://127.0.0.1:8000 ｜ 前端 http://localhost:5173"
	@cd $(BACKEND) && $(PY) -m uvicorn app.main:app --reload --port 8000 & \
	 cd $(FRONTEND) && npm run dev; \
	 wait

backend:  ## 只启动后端
	cd $(BACKEND) && $(PY) -m uvicorn app.main:app --reload --port 8000

frontend:  ## 只启动前端开发服务器
	cd $(FRONTEND) && npm run dev

# ── 构建 ────────────────────────────────────────────────────
build:  ## 构建前端产物（由后端同源托管）
	cd $(FRONTEND) && npx tsc --noEmit && npx vite build

# ── 质量 ────────────────────────────────────────────────────
test:  ## 运行后端测试
	cd $(BACKEND) && $(PY) -m pytest -q

lint:  ## 类型检查与静态分析
	cd $(FRONTEND) && npx tsc --noEmit
	cd $(BACKEND) && $(PY) -m ruff check app tests || true

audit:  ## 跑全部端到端审查（需服务已启动）
	@for s in audit_permissions audit_roles_ui audit_role_landing \
	           audit_extended_api audit_workbench_ui audit_mobile audit_confirm; do \
		printf "%-22s " "$$s"; $(PY) work/$$s.py 2>&1 | tail -1; \
	done

# ── 数据库 ──────────────────────────────────────────────────
migrate:  ## 执行数据库迁移
	cd $(BACKEND) && alembic upgrade head

seed:  ## 写入初始数据（12 案例 + 19 技巧卡）
	cd $(BACKEND) && $(PY) scripts/seed.py

# ── 容器 ────────────────────────────────────────────────────
docker-up:  ## 用 Compose 起全栈
	cd deliverables/deploy && docker compose -f docker-compose.prod.yml up -d

docker-down:  ## 停止 Compose 全栈
	cd deliverables/deploy && docker compose -f docker-compose.prod.yml down

# ── 清理 ────────────────────────────────────────────────────
clean:  ## 清理构建产物与缓存
	rm -rf $(FRONTEND)/dist $(FRONTEND)/node_modules/.vite
	find $(BACKEND) -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf $(BACKEND)/.pytest_cache $(BACKEND)/.ruff_cache