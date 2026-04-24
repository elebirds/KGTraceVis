.PHONY: install test lint examples app kg-import noise lock

install:
	uv sync --all-extras

test:
	uv run --extra dev pytest

lint:
	uv run --extra dev ruff check .

examples:
	uv run python scripts/run_examples.py

kg-import:
	uv run python scripts/import_kg.py

noise:
	uv run python scripts/run_noise_experiment.py

app:
	uv run streamlit run src/kgtracevis/app/streamlit_app.py

lock:
	uv lock
