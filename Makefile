UV ?= uv
NPM ?= npm
PYTHON ?= $(UV) run python
API_HOST ?= 127.0.0.1
API_PORT ?= 8000
WEB_HOST ?= 127.0.0.1
WEB_PORT ?= 5173
OUTPUT_ROOT ?= runs/real_model_pipeline
TORCH_CUDA_INDEX ?= https://download.pytorch.org/whl/cu128

.PHONY: help install setup setup-dev setup-ml setup-cuda web-install api web dev \
	check-web test lint examples check kg-import noise app lock real-pipeline \
	adapter-mvtec adapter-wm811k clean-web

help:
	@echo "KGTraceVis developer targets"
	@echo ""
	@echo "Setup:"
	@echo "  make install      Install all Python extras and web deps"
	@echo "  make setup        Install Python dev deps and web deps"
	@echo "  make setup-ml     Install dev + vision + ml extras"
	@echo "  make setup-cuda   Install ml extras, then force torch/torchvision from TORCH_CUDA_INDEX"
	@echo ""
	@echo "Run:"
	@echo "  make api          Start FastAPI on API_HOST:API_PORT"
	@echo "  make web          Start Vite on WEB_HOST:WEB_PORT"
	@echo "  make dev          Start API and web together via make -j2"
	@echo ""
	@echo "Verify:"
	@echo "  make check-web    Type-check and build React app"
	@echo "  make test         Run pytest"
	@echo "  make lint         Run ruff"
	@echo "  make examples     Run checked-in examples"
	@echo "  make check        Run test + examples + web checks"
	@echo ""
	@echo "Pipelines:"
	@echo "  make real-pipeline   Download/run real MVTec + WM811K model pipeline"
	@echo "  make adapter-mvtec   Run adapter pipeline on checked-in MVTec records"
	@echo "  make adapter-wm811k  Run adapter pipeline on checked-in WM811K records"

setup: setup-dev web-install

install:
	$(UV) sync --all-extras
	$(MAKE) web-install

setup-dev:
	$(UV) sync --extra dev

setup-ml:
	$(UV) sync --extra dev --extra vision --extra ml

setup-cuda: setup-ml
	$(UV) pip install --index-url $(TORCH_CUDA_INDEX) torch torchvision

web-install:
	$(NPM) --prefix web ci

api:
	$(UV) run uvicorn kgtracevis.service.api:app --host $(API_HOST) --port $(API_PORT)

web:
	$(NPM) --prefix web run dev -- --host $(WEB_HOST) --port $(WEB_PORT)

dev:
	$(MAKE) -j2 api web

check-web:
	$(NPM) --prefix web run typecheck
	$(NPM) --prefix web run build

test:
	$(UV) run --extra dev pytest

lint:
	$(UV) run --extra dev ruff check .

examples:
	$(PYTHON) scripts/run_examples.py

check: test examples check-web

kg-import:
	$(PYTHON) scripts/import_kg.py

noise:
	$(PYTHON) scripts/run_noise_experiment.py

app:
	$(UV) run streamlit run src/kgtracevis/app/streamlit_app.py

lock:
	$(UV) lock

real-pipeline:
	$(PYTHON) scripts/run_real_model_pipeline.py --output-root $(OUTPUT_ROOT)

adapter-mvtec:
	$(PYTHON) scripts/run_adapter_pipeline.py \
		--input data/examples/records/mvtec_records.jsonl \
		--dataset mvtec \
		--output-dir outputs/adapter_pipeline_v0/mvtec \
		--overwrite

adapter-wm811k:
	$(PYTHON) scripts/run_adapter_pipeline.py \
		--input data/examples/records/wm811k_records.jsonl \
		--dataset wafer \
		--output-dir outputs/adapter_pipeline_v0/wm811k \
		--overwrite

clean-web:
	$(PYTHON) -c "import shutil; shutil.rmtree('web/dist', ignore_errors=True)"
