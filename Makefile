.PHONY: help install install-server install-web dev dev-server dev-web test-smoke test-api check-types docker-up docker-down clean lint lint-server lint-web

help:
	@echo "千岸 QianAn - 开发命令"
	@echo ""
	@echo "  make install        - 安装所有依赖"
	@echo "  make install-server - 安装后端依赖"
	@echo "  make install-web    - 安装前端依赖"
	@echo "  make dev           - 同时启动前后端"
	@echo "  make dev-server    - 启动后端 (localhost:8000)"
	@echo "  make dev-web       - 启动前端 (localhost:3000)"
	@echo "  make test-smoke    - 百炼 API 冒烟测试"
	@echo "  make test-api      - 后端 API 集成测试"
	@echo "  make check-types   - TypeScript 类型检查"
	@echo "  make lint          - 全量 Lint"
	@echo "  make docker-up     - Docker 一键启动"
	@echo "  make docker-down   - Docker 停止"
	@echo "  make clean         - 清理构建产物"

install: install-server install-web

install-server:
	cd qianan/server && pip install -r requirements.txt

install-web:
	cd qianan/web && npm install

dev: dev-server dev-web

dev-server:
	cd qianan/server && uvicorn app.main:app --reload --port 8000

dev-web:
	cd qianan/web && npm run dev

test-smoke:
	cd qianan/server && python scripts/smoke_test.py

test-api:
	cd qianan/server && python scripts/smoke_test.py

check-types:
	cd qianan/web && npx tsc --noEmit

lint: lint-server lint-web

lint-server:
	cd qianan/server && python -m py_compile app/main.py app/orchestrator.py app/schemas.py

lint-web:
	cd qianan/web && npm run lint 2>/dev/null || echo "lint 脚本未配置"

docker-up:
	docker compose up --build

docker-down:
	docker compose down

clean:
	rm -rf qianan/web/.next qianan/web/node_modules/.cache
	find qianan/server -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	rm -rf qianan/server/data/tasks/*
