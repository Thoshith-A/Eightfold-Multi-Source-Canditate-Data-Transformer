# Convenience targets. On Windows without `make`, just run the commands shown.
PY ?= python

.PHONY: install install-all test run serve build-web demo clean

install:            ## Install the deterministic core only (no LLM deps)
	pip install -e ".[dev]"

install-all:        ## Install core + optional LLM and web extras
	pip install -e ".[dev,llm,web]"

test:               ## Run the full test suite
	pytest -q

run:                ## Transform the bundled samples with the default config
	$(PY) -m transformer.cli run -i samples/sources -c default

demo:               ## Show the custom (rename/subset) projection
	$(PY) -m transformer.cli run -i samples/sources -c samples/configs/recruiter_summary.json

serve:              ## Start the optional FastAPI app (needs the [web] extra)
	$(PY) -m uvicorn transformer.web.api:app --reload --port 8000

build-web:          ## Build the React/Vite frontend into web/frontend/dist
	cd web/frontend && npm install && npm run build

clean:              ## Remove caches and build artifacts
	rm -rf .pytest_cache **/__pycache__ web/frontend/dist
