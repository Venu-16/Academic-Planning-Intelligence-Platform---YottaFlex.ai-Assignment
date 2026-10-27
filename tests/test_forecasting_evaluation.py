import numpy as np

from academic_planner.forecasting import forecast_demand
from academic_planner.generator import generate_dataset


def test_model_and_last_observation_baseline_use_same_chronological_holdout():
    history = generate_dataset(20261022)["historical_enrollments"]

    _, report = forecast_demand(history)

    assert report["evaluation_term"] == "2026-FALL"
    assert report["evaluation_observations"] == 100
    assert np.isfinite(report["mae"])
    assert np.isfinite(report["rmse"])
    assert np.isfinite(report["baseline_mae"])
    assert np.isfinite(report["baseline_rmse"])
