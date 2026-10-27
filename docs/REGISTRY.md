# Model registry

Phase 1 does not use the MLflow Model Registry. MLflow (`./mlruns`) is the experiment log. DVC is the registry. `select_best` is the promotion step between them: it queries MLflow for the lowest `test_rmse`, then writes `models/model.pkl` and `models/model_meta.json`. Those files, plus `models/preprocessor.joblib`, are DVC outputs. Git stores `dvc.lock`, which records their hashes.

## What identifies a model version

A version is the pair:

- a Git tag such as `model-v1`, pointing at the commit that contains the matching `dvc.lock`
- the DVC md5 of `models/model.pkl` inside that lock file

`models/model_meta.json` (itself a DVC output) records the MLflow run id, the model family, the parameters, train and test RMSE / MAE / R², the feature list, the git commit that was checked out while training, the raw-data md5 from `data/raw/retail_price.csv.dvc`, and a UTC timestamp. The raw-data md5 is the dataset version the model was fit on. The git commit inside the metadata is the code revision that was checked out during training. The tag is the rollback handle, because the commit that adds `dvc.lock` is one bookkeeping commit later than the commit that was checked out when the process started.

## Promote

Run the sweep, then record and publish the lockfile. Do this on a clean tree.

```bash
make exp
git add dvc.lock dvc.yaml params.yaml src tests
git commit -m "Promote demand model"
git tag model-v1
dvc push
git push origin HEAD --tags
```

`dvc push` uploads `models/model.pkl`, `models/model_meta.json`, and `models/preprocessor.joblib` to the configured remote. It does not upload `./mlruns`. The promoted pickle is the registry artifact. The MLflow store is how you got there.

## Roll back

```bash
git checkout model-v1
dvc pull
```

`dvc pull` restores the pickle, the metadata, the preprocessor, and the raw CSV that the lockfile points at. Scoring that checkout uses the old model and the old data hash together. To return to current work, check out the branch again and `dvc pull` or `dvc checkout`.

The serving container does the same thing without a rebuild. Set `MODEL_VERSION` to the tag and restart the container. `scripts/fetch_model.sh` clones that revision, copies its `dvc.lock`, and pulls `models/model.pkl`, `models/model_meta.json`, and `models/preprocessor.joblib`. `GET /model-info` then reports that card.

Do not copy `model.pkl` between machines by hand. The hash in `dvc.lock` is what makes the copy the same object.

## Remotes

The committed default remote is a local directory, `../dvc-storage`, so `dvc push` and `dvc pull` work in the lab without cloud credentials. An S3 remote named `s3` is declared but not selected. Credentials never go in `.dvc/config`. `dvc init` gitignores `.dvc/config.local`, and that is the only place `dvc remote modify --local` writes.

Switch the lab remote to S3:

```bash
dvc remote default s3
# either environment variables (preferred on a shared machine)
export AWS_ACCESS_KEY_ID="..."
export AWS_SECRET_ACCESS_KEY="..."
export AWS_DEFAULT_REGION="ap-south-1"
# or a gitignored local config
dvc remote modify --local s3 access_key_id "..."
dvc remote modify --local s3 secret_access_key "..."
dvc push
```

The bucket URL in `.dvc/config` is `s3://priceoptima/priceoptima`. Change it if your bucket name differs:

```bash
dvc remote modify s3 url s3://<your-bucket>/priceoptima
```

Fall back to a local folder (this is already the default):

```bash
dvc remote add -f local /absolute/or/relative/path/dvc-storage
dvc remote default local
dvc push -r local
```

Google Drive, if you cannot use S3. This extra is not installed by `requirements.txt`:

```bash
.venv/bin/pip install dvc-gdrive
dvc remote add -f gdrive gdrive://<folder-id>
dvc remote default gdrive
# OAuth material stays in .dvc/config.local
dvc remote modify --local gdrive gdrive_client_id "<client-id>"
dvc remote modify --local gdrive gdrive_client_secret "<client-secret>"
dvc push
```

Confirm nothing secret is staged before every commit:

```bash
git status
git diff -- .dvc/config
```

`.dvc/config` should contain remote URLs only. If `access_key_id` or `secret_access_key` appears there, remove it and set the value again with `--local`.
