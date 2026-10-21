# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

`hotelml`: reference MLOps platform that predicts hotel booking cancellations (training, MLflow registry, FastAPI serving, Azure infra via Terraform). Docs, comments and commit/ADR text are written in Portuguese; keep new prose in Portuguese to match. Phases 3–6 (PySpark, monitoring, LLMOps) are not implemented yet; see the table in [README.md](README.md).

## Commands

```bash
make install            # pip install -r requirements-dev.lock + pip install --no-deps -e .
make check              # ruff check + mypy src + pytest (with coverage)
make lint / typecheck / test
make format             # ruff format src tests scripts (CI runs `ruff format --check`)
pytest tests/test_api.py::test_name        # single test
make train-synthetic    # offline training on synthetic data (what CI and tests use)
make train-real         # downloads gemuchu/hotel_bookings from Hugging Face
make status | rollback  # inspect / swap champion aliases
make export             # hotelml export --output model-bundle (required before docker build)
make serve              # uvicorn on 127.0.0.1:8000
```

- Dependencies are pinned in `requirements.lock` (runtime, used by the Dockerfile) and `requirements-dev.lock` (dev/CI). CI enforces `--cov-fail-under=80`.
- Config comes from env vars (`MLFLOW_TRACKING_URI`, `MLFLOW_ARTIFACT_ROOT`, `MLFLOW_EXPERIMENT`, `MODEL_NAME`, `MODEL_BUNDLE`); `.env` is loaded without overriding existing env. Default tracking store is a local SQLite `mlflow.db`.
- The Dockerfile `COPY`s `model-bundle/`, so `hotelml train` + `hotelml export` must run before `docker build` (CI does this with synthetic data, then runs `scripts/smoke_api.py` against the container).

## Architecture

Package in `src/hotelml/`. The flow spans several modules:

- **Contract**: `config.py` holds `INPUT_COLUMNS` (the exact request payload), model feature lists, `LEAKAGE_COLUMNS`, and `Settings`. `schema.py::validate_raw` checks training data; `api.py::Booking` (pydantic, `extra="forbid"`) validates inference input. Changing a column means touching all three plus `synthetic.py`.
- **Train/serve parity**: `features.py::add_features` is stateless and lives *inside* the sklearn pipeline, so the registered model accepts raw `INPUT_COLUMNS` directly. Row filtering (`clean_training_data`) is training-only. Evaluation uses a temporal split (`time_split`: train on past, test on future), not random.
- **Registry by aliases** (`registry.py`, ADR 0002): new models get `challenger`; `promote_if_better` re-evaluates the current `champion` on the *same* test set and promotes only if ROC AUC improves, saving the old one as `previous_champion`. Rollback only swaps aliases (running it twice undoes it).
- **Serving** (`api.py`, `bundle.py`, ADR 0003): `hotelml export` resolves `champion` once to an explicit version and copies it plus `manifest.json` into a bundle. With `MODEL_BUNDLE` set, the API loads that snapshot and never touches the registry; otherwise it resolves `champion` from MLflow at startup. The model is loaded in the app lifespan and startup fails if it can't load. Alias changes require restarting/redeploying the API. `api.py` ends with a module-level `app = create_app()`; tests inject a fake loader via `create_app(loader)`.
- **skops allowlist**: MLflow serializes sklearn models with skops, which refuses unknown types on load. `config.SKOPS_TRUSTED_TYPES` is an explicit allowlist passed to `log_model`; add to it when a new model/transformer type fails to load, never trust-all.
- **Infra/CD**: `infra/` (Terraform, azurerm: Container Apps, ACR, AcrPull identity, logs, budget). `.github/workflows/ci.yml` (quality + terraform fmt/validate, also `workflow_call`) gates the manual `deploy.yml` (OIDC, digest-based deploy, smoke tests). Runbooks and ADRs are in `docs/`.

## Testing notes

Tests use synthetic data (`make_synthetic`) and a per-test temporary SQLite MLflow via the `settings` fixture in `tests/conftest.py`, so they need no network. Ruff rules: E, F, I, UP, B, SIM, line length 100, Python ≥3.11 (CI uses 3.12).
