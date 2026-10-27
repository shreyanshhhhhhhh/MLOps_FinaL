# PriceOptima

PriceOptima predicts monthly quantity sold (`qty`) from price and context, then recommends a revenue-maximising price by scoring that model across a price grid.

Phase 1 is the training system: one parameter file, a DVC pipeline, and an MLflow sweep that promotes a single artifact. Phase 2 is the serving system: a FastAPI process in a container that pulls `models/model.pkl` from the DVC remote at start. The image does not contain the pickle.

The dataset is the Kaggle [Retail Price Optimization](https://www.kaggle.com/datasets/suddharshan/retail-price-optimization) file `retail_price.csv`: 676 product-months, 30 columns, January 2017 through August 2018. The CSV is not in Git. `data/raw/retail_price.csv.dvc` is the pointer.

## Layout

```
data/raw/                retail_price.csv, tracked by DVC
data/processed/          train/test splits and engineered frames
src/                     config, preprocess, features, train, evaluate, select_best
app/                     FastAPI service (health, ready, predict, optimize, metrics)
models/                  preprocessor.joblib, model.pkl, model_meta.json
metrics/                 train_runs.json, metrics.json, diagnostic plots
notebooks/eda.ipynb      EDA only, not part of the pipeline
tests/                   schema, leakage, feature fixture, API
scripts/                 container entrypoint, model fetch, smoke test
docs/REGISTRY.md         how a model version is named, promoted, and rolled back
params.yaml              split, seed, features, hyperparameter grid
dvc.yaml                 preprocess -> features -> train -> evaluate -> select_best
Dockerfile               multi-stage image, no model binary
docker-compose.yml       local run against the DVC remote
```

`src/scoring.py` is the only definition of RMSE, MAE, and R². `src/provenance.py` reads the git commit and the raw-data DVC hash so train and select_best stamp the same identity.

## Commands from a clean clone

```bash
make setup
source .venv/bin/activate
dvc pull
dvc repro
make exp
dvc push
```

`make setup` creates `.venv` and installs `requirements.txt`. Activate it before the raw `dvc` commands so they use that environment. `make exp`, `make test`, and `make lint` call `.venv/bin` themselves.

| Target | What it does |
| --- | --- |
| `make setup` | Create the venv and install pinned dependencies |
| `make repro` | `dvc repro`. The second run skips stages whose deps and params did not change |
| `make exp` | Force `train`, `evaluate`, and `select_best`, so the sweep always logs new MLflow runs |
| `make test` | `pytest` |
| `make lint` | `ruff check src tests` |
| `make dag` | `dvc dag` |
| `make push` | `dvc push` to the default remote |

Inspect the sweep. MLflow 3.17 keeps the directory store behind an opt-in, and the UI opens on the Traces tab:

```bash
export MLFLOW_ALLOW_FILE_STORE=true
mlflow ui --backend-store-uri ./mlruns
```

Open experiment `priceoptima-demand`, switch the top toggle to **Model training**, then **Training runs**. Sort by `test_rmse`. The metric is logged on every run; the default column set is created-time, so add `test_rmse` from the Columns menu if it is not already on screen.

Open the `priceoptima-demand` experiment and sort by `test_rmse`. The grid in `params.yaml` is 14 runs (linear regression, ridge, random forest, gradient boosting, lightgbm). `make exp` appends another 14 because MLflow keeps history.

If `dvc pull` cannot see the remote (a fresh machine whose sibling `dvc-storage` directory is empty), put the Kaggle CSV at `data/raw/retail_price.csv`. The md5 in `data/raw/retail_price.csv.dvc` must match. A public copy of the same file is `https://raw.githubusercontent.com/suddhasheel333/retail-price-optimization/main/data/retail_price.csv`.

## DVC remote

`.dvc/config` declares two remotes:

- `local` (default), the directory `dvc-storage` next to the clone. DVC stores paths relative to `.dvc/config`, so the file contains `../../dvc-storage`. This is the default so `dvc push` works in the lab without cloud keys.
- `s3`, URL `s3://priceoptima/priceoptima`, ready to become the default.

Credentials never go in `.dvc/config`. Use environment variables or `dvc remote modify --local`, which writes `.dvc/config.local` (gitignored). Switching to S3 or Google Drive is written out in `docs/REGISTRY.md`.

## Decisions worth defending

- The split is the last 20% of distinct months (May–August 2018 on this file), not a random row split. A pricing model is used on future months, and a random split puts those months into training. The seed does not shuffle the cut. It only seeds estimators that use randomness. `n_jobs` is fixed at 1 for the same reason.
- `01-05-2017` is parsed with `%d-%m-%Y`. Every raw date is the first of a month, so month-first parsing would still sort, but it would label May as 5 January.
- Outlier fences are Tukey IQRs fit on the training months only, then applied to both splits. Rows are clipped, not dropped, so the product-month panel stays complete. Thresholds live in `data/processed/preprocess_meta.json`.
- `total_price` is revenue and tracks `qty` (correlation about 0.75). `customers` is the buyer count from the same product-month. Both stay in the processed CSV for audit and are listed under `excluded_from_model`. `log_qty` is written for Phase 2 elasticity work and is also excluded, because it is a transform of the target.
- `product_id` is not one-hot encoded. There are 52 ids in 676 rows. Category (9 levels) is the grouping the linear model can estimate. `s` is constant inside each product and calendar month and repeats a year later, so it behaves as a seasonal index rather than a copy of `qty`. It stays in the model. `volume` is constant per product.
- The price ratio is `unit_price / mean(comp_1, comp_2, comp_3)`. The individual competitor prices stay too. Phase 1 is ranking predictive models, not reading coefficients, so the correlation between price, log price, and the ratio is acceptable. A non-positive denominator becomes missing and is median-imputed from train.
- The preprocessor (median impute, standard scale, one-hot with `handle_unknown="ignore"`) is fit inside the features stage on train only and saved as `models/preprocessor.joblib`. Train and evaluate only call `transform`. One matrix is shared by linear and tree models. Trees are invariant to a monotonic scaling, so the scaler does not change their splits in a way that matters here, and the linear models need it.
- Metrics are always on the clipped `qty` the model was trained to predict, not on `log_qty`. RMSE is the selection metric. MAE and R² are logged beside it.
- `make repro` is allowed to skip. `make exp` forces the three modelling stages so a warm cache cannot hide an empty MLflow store. `./mlruns` is gitignored and is not a DVC output. The registry artifact is the pickle DVC pushes. MLflow 3.17 treats that directory store as maintenance-only, so the process sets `MLFLOW_ALLOW_FILE_STORE=true` rather than switching the lab to a database. The same release saves sklearn models with skops and rejects tree and LightGBM types unless the caller names them. `SKOPS_TRUSTED_TYPES` is that allow-list, limited to estimators this process just fit.
- `select_best` asks MLflow for finished runs and sorts by `test_rmse`. Ties keep the later run. It does not trust a hand-picked filename. Evaluate writes the same ranking for the current sweep to `metrics/metrics.json` and the plots. If the two disagree, the MLflow run is the one that is promoted, and the metadata records both ids.
- LightGBM runs with `num_leaves` 31 and 63 land on the same test RMSE. The training panel is 516 rows and LightGBM's default `min_child_samples` is 20, so the trees stop before they can use 63 leaves. Both settings are still logged, because the grid is the experiment record, not a claim that every cell changes the score.

## Tests

```bash
make lint
make test
```

`tests/test_preprocess.py` checks the output columns, dtypes, and that `01-05-2017` is May. `tests/test_leakage.py` checks the year-boundary split, that a test-only qty of 10000 does not widen the train fence, and that the scaler mean is the train price rather than the pooled price. `tests/test_features.py` checks the ratio, the lag change, and the logs on a one-row fixture.

## Serving

```mermaid
flowchart LR
  client[Client] --> api[FastAPI in the container]
  api --> features["src.features.add_engineered_features"]
  features --> model[model.pkl]
  entry[entrypoint.sh] --> fetch["dvc pull models/"]
  fetch --> remote[(DVC remote)]
  gitTag["MODEL_VERSION git tag"] --> entry
  remote --> model
```

The container starts `scripts/fetch_model.sh` and uvicorn together. The fetch retries with backoff. `/health` is 200 as soon as the process is up. `/ready` is 503 until `model.pkl`, `preprocessor.joblib`, and `model_meta.json` have been loaded. A failed pull does not kill the process.

Training and serving call the same functions in `src/features.py`. `add_engineered_features` builds `price_vs_comp`, `price_change`, and the logs. `transform_frame` applies the preprocessor that the features stage fitted on the training months. Serving passes `target_column=None` because quantity is unknown. That skips `log_qty`, which the model never sees anyway. There is no second feature implementation in `app/`.

`MODEL_VERSION` is a git tag or commit (`model-v1`, `model-v2`). When it is set, the entrypoint clones that revision and copies its `dvc.lock` over the one baked into the image, then pulls those hashes. The image is not rebuilt. `.dvc/config` stays the image copy, so the remote URL is not whatever the old commit happened to commit. The pipeline outputs live in `dvc.lock` rather than a second `models/model.pkl.dvc`, because DVC rejects two trackers for the same path.

### Run the container

```bash
docker build -t priceoptima:phase2 .
MODEL_VERSION=model-v2 docker compose up -d --no-build
scripts/smoke_test.sh
```

`docker compose` publishes port 8000, reads `.env` when that file exists, mounts the DVC remote at `/dvc-storage`, and mounts this repo (including `.git`) at `/opt/src` so `GIT_REPO_URL=file:///opt/src` can see the tags. The mount is not on `/app`, so a host `model.pkl` is not the file the process loads.

Roll the model back without a rebuild:

```bash
MODEL_VERSION=model-v1 docker compose up -d --no-build --force-recreate
curl -s http://127.0.0.1:8000/model-info
```

`docker restart` keeps the environment from the previous create, so a version change has to recreate the container. The image stays `priceoptima:phase2`.

Two tags are published so that recreate is a real rollback:

| Tag | Model | Test RMSE |
| --- | --- | --- |
| `model-v1` | gradient boosting, `n_estimators=100`, `learning_rate=0.05`, `max_depth=3` | 7.5348 |
| `model-v2` | ridge, `alpha=10` | 10.7582 |

Both pickle hashes stay in the DVC remote. The image is built with the `model-v2` lock inside it. `MODEL_VERSION=model-v1` replaces that lock at start and pulls the boosting artifact. `/model-info` reports `model_name` and the metrics from the card that was pulled.

Stop the process and let the restart policy bring it back:

```bash
docker kill priceoptima
```

`restart: unless-stopped` starts it again. `docker compose restart` does the same if you want to force it.

### Example requests

Sample product: `bed1`, bed_bath_table, May 2018. The recorded price was 39.99 and the recorded quantity was 19.

```bash
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/ready
curl -s http://127.0.0.1:8000/model-info
```

```bash
curl -s http://127.0.0.1:8000/predict-demand \
  -H 'content-type: application/json' \
  -d '{
    "product_category_name": "bed_bath_table",
    "unit_price": 39.99,
    "freight_price": 10.25631579,
    "product_weight_g": 350,
    "product_score": 4.0,
    "weekday": 23,
    "weekend": 8,
    "holiday": 3,
    "month": 5,
    "year": 2018,
    "volume": 3800,
    "s": 10.26739356,
    "comp_1": 83.64961538,
    "comp_2": 39.99,
    "comp_3": 39.99,
    "ps1": 3.9,
    "ps2": 4.0,
    "ps3": 4.0,
    "fp1": 16.78038462,
    "fp2": 10.25631579,
    "fp3": 10.25631579,
    "lag_price": 39.99,
    "product_name_lenght": 39,
    "product_description_lenght": 161,
    "product_photos_qty": 2
  }'
```

On the promoted gradient boosting model this product returns about 7.91, against a recorded quantity of 19:

```json
{"predicted_qty": 7.9119, "model_output": 7.9119, "unit_price": 39.99}
```

`predicted_qty` is the model output floored at zero. `model_output` is the raw value. The same call against `model-v2` (ridge) returns a different quantity. That difference is the rollback check.

```bash
curl -s http://127.0.0.1:8000/optimize-price \
  -H 'content-type: application/json' \
  -d '{
    "product_category_name": "bed_bath_table",
    "freight_price": 10.25631579,
    "product_weight_g": 350,
    "product_score": 4.0,
    "weekday": 23,
    "weekend": 8,
    "holiday": 3,
    "month": 5,
    "year": 2018,
    "volume": 3800,
    "s": 10.26739356,
    "comp_1": 83.64961538,
    "comp_2": 39.99,
    "comp_3": 39.99,
    "ps1": 3.9,
    "ps2": 4.0,
    "ps3": 4.0,
    "fp1": 16.78038462,
    "fp2": 10.25631579,
    "fp3": 10.25631579,
    "lag_price": 39.99,
    "product_name_lenght": 39,
    "product_description_lenght": 161,
    "product_photos_qty": 2,
    "min_price": 20,
    "max_price": 80,
    "step": 5,
    "unit_cost": 15
  }'
```

The response includes `best_price` inside `[min_price, max_price]`, `expected_demand`, `expected_revenue`, `expected_profit` when `unit_cost` was sent, `elasticity` (arc elasticity around the chosen price), `log_log_slope`, and `curve` (one point per price). Omit `unit_cost` to maximise revenue instead of profit. A non-positive price, a range with `min_price >= max_price`, or a grid above 500 points returns 422.

`GET /metrics` is Prometheus text: `priceoptima_requests_total`, `priceoptima_request_latency_seconds`, and `priceoptima_predictions_total`. Each request also writes one JSON log line with `request_id`, `endpoint`, `status`, and `latency_ms`.

### Environment

| Variable | Role |
| --- | --- |
| `DVC_REMOTE` | Remote name from `.dvc/config`. `local` (default) or `s3` |
| `DVC_STORAGE_DIR` | Host path compose mounts at `/dvc-storage`. Default `../dvc-storage` |
| `DVC_STORAGE_URL` | Optional override of the `local` remote URL inside the container |
| `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_DEFAULT_REGION` | Used only when `DVC_REMOTE=s3`. Leave unset on an instance with an IAM role. Never copied into the image |
| `MODEL_VERSION` | Git tag or commit whose `dvc.lock` is pulled. Empty uses the lock baked into the image |
| `GIT_REPO_URL` | Where that revision is cloned from. Compose defaults to `file:///opt/src` |
| `PORT` | Uvicorn port. Default 8000 |
| `MODEL_AUTOLOAD` | `1` in the container. Tests set `0` and inject a dummy model |

Copy `.env.example` to `.env` for compose. `.env` is gitignored.

### Image

The Dockerfile is two stages, both `python:3.11-slim`. The builder installs `requirements-serve.txt` into a venv. The runtime stage copies that venv, the app, `src/`, `params.yaml`, `dvc.lock`, `.dvc/config`, and the scripts. It installs `git` because a version pin is a `git clone` of a tag. It does not install a compiler, and it does not copy `data/`, `mlruns/`, tests, notebooks, or anything under `models/` except an empty directory. The process runs as `appuser` (uid 1000). The healthcheck calls `/health`, not `/ready`, so a slow pull is not a dead container.

`requirements-serve.txt` is the serving subset of `requirements.txt`: the training pins for pandas, numpy, scikit-learn, lightgbm, and joblib, plus FastAPI, uvicorn, and `dvc[s3]`. MLflow, pytest, and matplotlib stay out of the image. The sklearn and lightgbm pins match the versions that wrote the pickle.

## What is deliberately not here

No GitHub Actions workflow and no EC2 user-data. `scripts/smoke_test.sh` is the check those later phases can call.
