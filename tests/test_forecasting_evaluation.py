import numpy as np
import pandas as pd

from academic_planner.forecasting import forecast_demand
from academic_planner.generator import generate_dataset


def test_model_and_last_observation_baseline_use_same_chronological_holdout():
    history = generate_dataset(20261022)["historical_enrollments"]

    _, report = forecast_demand(history, target_term="2027-SPRING")

    assert report["evaluation_term"] == "2026-FALL"
    assert report["evaluation_observations"] == 100
    assert np.isfinite(report["mae"])
    assert np.isfinite(report["rmse"])
    assert np.isfinite(report["baseline_mae"])
    assert np.isfinite(report["baseline_rmse"])


def test_forecast_exports_target_period_method_and_source_inputs():
    frames = generate_dataset(20261022)
    forecasts, _ = forecast_demand(
        frames["historical_enrollments"],
        target_term="2027-SPRING",
        course_ids=frames["courses"]["course_id"],
        registration_interests=frames["registration_interests"],
    )

    row = forecasts.set_index("course_id").loc["CRS-000001"]
    history = frames["historical_enrollments"]
    latest = history.loc[history.course_id == "CRS-000001"].iloc[-1]
    interest_count = frames["registration_interests"].loc[
        (frames["registration_interests"].course_id == "CRS-000001")
        & frames["registration_interests"].eligible
        & frames["registration_interests"].interest_status.isin(
            ["INTERESTED", "REGISTERED", "WAITLISTED"]
        )
    ].shape[0]

    assert row.target_term == "2027-SPRING"
    assert row.source_term_id == "2026-FALL"
    assert row.model_name == "RandomForestRegressor"
    assert row.last_enrollment == latest.enrolled
    assert row.registrations == latest.registrations
    assert row.unmet_demand_input == latest.unmet_demand
    assert row.eligible_interest_count == interest_count
    assert not row.fallback_applied
    assert row.fallback_reason == ""


def test_sparse_and_new_courses_use_explicit_interest_fallbacks():
    history = generate_dataset(20261022)["historical_enrollments"]
    history = history.loc[
        (history.course_id == "CRS-000001")
        & history.term_id.isin(["2025-FALL", "2026-SPRING"])
    ]
    interests = pd.DataFrame([
        {
            "course_id": "CRS-NEW",
            "eligible": True,
            "interest_status": "REGISTERED",
        },
        {
            "course_id": "CRS-NEW",
            "eligible": True,
            "interest_status": "INTERESTED",
        },
    ])

    forecasts, report = forecast_demand(
        history,
        target_term="2027-SPRING",
        course_ids=["CRS-000001", "CRS-NEW", "CRS-NO-INTEREST"],
        registration_interests=interests,
    )
    rows = forecasts.set_index("course_id")

    assert rows.loc["CRS-000001", "model_name"] == "LAST_OBSERVATION_FALLBACK"
    assert rows.loc["CRS-000001", "fallback_reason"] == (
        "NO_TRAINING_TRANSITIONS_USE_LAST_ENROLLMENT"
    )
    expected_last_enrollment = int(
        history.sort_values("term_id").iloc[-1].enrolled
    )
    assert rows.loc["CRS-000001", "forecast_enrollment"] == (
        expected_last_enrollment
    )
    assert rows.loc["CRS-NEW", "forecast_enrollment"] == 2
    assert rows.loc["CRS-NEW", "model_name"] == (
        "ELIGIBLE_REGISTRATION_INTEREST_FALLBACK"
    )
    assert rows.loc["CRS-NEW", "fallback_applied"]
    assert rows.loc["CRS-NO-INTEREST", "forecast_enrollment"] == 0
    assert rows.loc["CRS-NO-INTEREST", "fallback_reason"] == (
        "NO_HISTORY_OR_ELIGIBLE_INTEREST"
    )
    assert report["evaluation_observations"] == 1
