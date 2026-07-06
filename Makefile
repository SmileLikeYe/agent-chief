.PHONY: test lint demo demo-gif build release-check

test:
	uv run pytest

lint:
	uv run ruff check .

demo:
	uv run chief demo

readme-metrics:
	uv run python scripts/readme_metrics.py --write

demo-gif:
	bash scripts/demo-gif.sh

build:
	uv build

release-check: lint test build
	uvx --isolated --from dist/agent_chief-0.1.0-py3-none-any.whl chief demo --fast > /dev/null
	@echo "release check passed"
