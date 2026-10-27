# PriceOptima

Phase 1 of a demand model for dynamic pricing. The model predicts monthly quantity sold (`qty`) from price and context. Phase 2 (not in this repo yet) will search that model for a revenue-maximising price. The point of this phase is reproducibility: one parameter file, a DVC pipeline, and an MLflow sweep that promotes a single artifact.

The dataset is the Kaggle [Retail Price Optimization](https://www.kaggle.com/datasets/suddharshan/retail-price-optimization) file `retail_price.csv`: 676 product-months, 30 columns, January 2017 through August 2018. The CSV is not in Git. `data/raw/retail_price.csv.dvc` is the pointer.

## Layout

```
data/raw/                retail_price.csv, tracked by DVC
data/processed/          train/test splits and engineered frames
src/                     config, preprocess, features, train, evaluate, select_best
models/                  preprocessor.joblib, model.pkl, model_meta.json
metrics/                 train_runs.json, metrics.json, diagnostic plots
notebooks/eda.ipynb      EDA only, not part of the pipeline
tests/                   schema, leakage, feature fixture, grid size
docs/REGISTRY.md         how a model version is named, promoted, and rolled back
params.yaml              split, seed, features, hyperparameter grid
dvc.yaml                 preprocess -> features -> train -> evaluate -> select_best
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

Inspect the sweep. MLflow 3.17 keeps the directory store behind an opt-in:

```bash
export MLFLOW_ALLOW_FILE_STORE=true
mlflow ui --backend-store-uri ./mlruns
```

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

## What is deliberately not here

No API, Docker, or CI. Those are later phases.
