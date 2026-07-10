.PHONY: format lint typecheck unit integration contract e2e check contract-generate contract-check

format:
	uv run ruff format .
	uv run ruff check --fix .

lint:
	uv run ruff format --check .
	uv run ruff check .

typecheck:
	uv run mypy

unit:
	uv run pytest tests/unit

integration:
	uv run pytest -m integration

contract:
	uv run pytest tests/contract

e2e:
	uv run pytest -m e2e

contract-generate:
	uv run python scripts/generate_contract.py

contract-check:
	@tmp=$$(mktemp); cp contracts/mcp/v1/discovery.json $$tmp; \
	uv run python scripts/generate_contract.py; cmp $$tmp contracts/mcp/v1/discovery.json; rm $$tmp

check: lint typecheck unit integration contract e2e contract-check

