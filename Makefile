UV ?= uv
PYTHON ?= $(UV) run python
API_HOST ?= 127.0.0.1
API_PORT ?= 8000
OUTPUT_ROOT ?= runs/real_model_pipeline
TORCH_CUDA_INDEX ?= https://download.pytorch.org/whl/cu128

.PHONY: help install setup setup-dev setup-ml setup-cuda api dev \
	test lint examples check kg-import noise lock real-pipeline \
	download-model-assets download-patchcore download-stfpm adapter-mvtec adapter-wm811k

help:
	@echo "KGTraceVis developer targets"
	@echo ""
	@echo "Setup:"
	@echo "  make install      Install all Python extras"
	@echo "  make setup        Install Python dev deps"
	@echo "  make setup-ml     Install dev + vision + ml extras"
	@echo "  make setup-cuda   Install ml extras, then force torch/torchvision from TORCH_CUDA_INDEX"
	@echo ""
	@echo "Run:"
	@echo "  make api          Start FastAPI on API_HOST:API_PORT"
	@echo "  make dev          Start the FastAPI development service"
	@echo ""
	@echo "Verify:"
	@echo "  make test         Run pytest"
	@echo "  make lint         Run ruff"
	@echo "  make examples     Run checked-in examples"
	@echo "  make check        Run test + examples"
	@echo ""
	@echo "Pipelines:"
	@echo "  make download-model-assets  Download default trusted model assets"
	@echo "  make download-patchcore     Download default MVTec PatchCore checkpoint"
	@echo "  make download-stfpm         Download default MVTec STFPM OpenVINO checkpoint"
	@echo "  make real-pipeline   Download/run real MVTec + WM811K model pipeline"
	@echo "  make adapter-mvtec   Run adapter pipeline on checked-in MVTec records"
	@echo "  make adapter-wm811k  Run adapter pipeline on checked-in WM811K records"

setup: setup-dev

install:
	$(UV) sync --all-extras

setup-dev:
	$(UV) sync --extra dev

setup-ml:
	$(UV) sync --extra dev --extra vision --extra ml

setup-cuda: setup-ml
	$(UV) pip install --index-url $(TORCH_CUDA_INDEX) torch torchvision

api:
	$(UV) run uvicorn kgtracevis.service.api:app --host $(API_HOST) --port $(API_PORT)

dev: api

test:
	$(UV) run --extra dev pytest

lint:
	$(UV) run --extra dev ruff check .

examples:
	$(PYTHON) scripts/run_examples.py

check: test examples

kg-import:
	$(PYTHON) scripts/import_kg.py

noise:
	$(PYTHON) scripts/run_noise_experiment.py

lock:
	$(UV) lock

real-pipeline:
	$(PYTHON) scripts/run_real_model_pipeline.py --output-root $(OUTPUT_ROOT)

download-model-assets:
	$(PYTHON) scripts/download_model_assets.py --output-root $(OUTPUT_ROOT)

download-patchcore:
	$(PYTHON) scripts/download_model_assets.py --output-root $(OUTPUT_ROOT) --model mvtec-patchcore

download-stfpm:
	$(PYTHON) scripts/download_model_assets.py --output-root $(OUTPUT_ROOT) --model mvtec-stfpm

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
