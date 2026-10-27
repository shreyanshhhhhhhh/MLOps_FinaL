"""PriceOptima demand model pipeline."""

import os

# MLflow 3 prints an agent hint the first time it is imported. Silence it
# before any stage imports mlflow. Tracking itself is unchanged.
os.environ.setdefault("MLFLOW_DISABLE_AGENT_HINT", "1")
os.environ.setdefault("MPLBACKEND", "Agg")
# MLflow 3.17 refuses ./mlruns unless this opt-in is set. The lab store is
# the directory backend, so the pipeline turns the maintenance-mode gate off.
os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
