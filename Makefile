.PHONY: test lint demo demo-gif showcase clean-dist build release-check release-metadata readme-metrics

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

showcase:
	bash scripts/showcase.sh

clean-dist:
	rm -f dist/*

build: clean-dist
	uv build

release-metadata:
	uv run python scripts/check_release_version.py

release-check: lint test release-metadata build
	uvx --isolated --from dist/agent_chief-*-py3-none-any.whl chief demo --fast > /dev/null
	@echo "release check passed"
