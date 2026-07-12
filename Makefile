.PHONY: format lint typecheck dashboard-check unit integration contract e2e performance coverage check contract-generate contract-check

format:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff format --check .
	uv run ruff check .

typecheck:
	uv run mypy

dashboard-check:
	cd dashboard && npm run lint && npm test && npm run build

unit:
	uv run pytest tests/unit

integration:
	uv run pytest -m integration

contract:
	uv run pytest tests/contract

e2e:
	uv run pytest -m e2e

performance:
	uv run pytest -m performance -s

coverage:
	uv run pytest tests/unit tests/integration tests/contract --cov=global_memory --cov-report=term --cov-fail-under=85

contract-generate:
	uv run python scripts/generate_contract.py

contract-check:
	@tmp=$$(mktemp); cp contracts/mcp/v1/discovery.json $$tmp; \
	uv run python scripts/generate_contract.py; cmp $$tmp contracts/mcp/v1/discovery.json; rm $$tmp

check: lint typecheck dashboard-check unit integration contract e2e coverage contract-check
