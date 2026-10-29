import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error


FEATURES = ["last_enrollment", "registrations", "unmet"]
INTEREST_STATUSES = {"INTERESTED", "REGISTERED", "WAITLISTED"}


def forecast_demand(
    history,
    target_term=None,
    course_ids=None,
    registration_interests=None,
):
    required = {"course_id", "term_id", "enrolled", "registrations", "unmet_demand"}
    missing = required - set(history.columns)
    if missing:
        raise ValueError(f"Historical enrollments missing columns: {sorted(missing)}")

    history = history.copy()
    season_order = {"SPRING": 0, "SUMMER": 1, "FALL": 2, "WINTER": 3}

    def term_key(term):
        parts = str(term).split("-")
        year = int(parts[0]) if parts and parts[0].isdigit() else 0
        season = season_order.get(parts[1].upper(), 9) if len(parts) > 1 else 9
        return year * 10 + season

    history["_term_order"] = history.term_id.map(term_key)
    history = history.sort_values("_term_order")
    terms = list(dict.fromkeys(history.term_id.tolist()))
    train_rows = []
    test_rows = []
    for _, group in history.groupby("course_id"):
        group = group.sort_values("_term_order")
        for index in range(1, len(group)):
            row = {
                "last_enrollment": float(group.enrolled.iloc[index - 1]),
                "registrations": float(group.registrations.iloc[index - 1]),
                "unmet": float(group.unmet_demand.iloc[index - 1]),
                "target": float(group.enrolled.iloc[index]),
            }
            if group.term_id.iloc[index] == terms[-1]:
                test_rows.append(row)
            else:
                train_rows.append(row)

    model = None
    train = pd.DataFrame(train_rows)
    test = pd.DataFrame(test_rows)
    if not train.empty:
        model = RandomForestRegressor(
            n_estimators=80,
            random_state=20261022,
            min_samples_leaf=2,
        )
        model.fit(train[FEATURES], train.target)

    if test.empty:
        mae = rmse = baseline_mae = baseline_rmse = None
    else:
        baseline_prediction = np.maximum(0, test.last_enrollment.to_numpy())
        prediction = (
            np.maximum(0, model.predict(test[FEATURES]))
            if model is not None
            else baseline_prediction
        )
        mae = float(mean_absolute_error(test.target, prediction))
        rmse = float(np.sqrt(mean_squared_error(test.target, prediction)))
        baseline_mae = float(
            mean_absolute_error(test.target, baseline_prediction)
        )
        baseline_rmse = float(
            np.sqrt(mean_squared_error(test.target, baseline_prediction))
        )

    latest = []
    for course_id, group in history.groupby("course_id"):
        row = group.sort_values("_term_order").iloc[-1]
        latest.append({
            "course_id": course_id,
            "source_term_id": row.term_id,
            "history_count": len(group),
            "last_enrollment": float(row.enrolled),
            "registrations": float(row.registrations),
            "unmet": float(row.unmet_demand),
        })

    latest_by_course = {
        row["course_id"]: row for row in latest
    }
    all_course_ids = list(latest_by_course)
    if course_ids is not None:
        all_course_ids.extend(course_ids)
    all_course_ids = list(dict.fromkeys(all_course_ids))

    interest_counts = {}
    if registration_interests is not None and not registration_interests.empty:
        interest_columns = {"course_id", "eligible", "interest_status"}
        missing = interest_columns - set(registration_interests.columns)
        if missing:
            raise ValueError(
                f"Registration interests missing columns: {sorted(missing)}"
            )
        eligible = registration_interests.eligible.fillna(False).astype(bool)
        relevant = registration_interests.loc[
            eligible
            & registration_interests.interest_status.isin(INTEREST_STATUSES)
        ]
        interest_counts = relevant.groupby("course_id").size().to_dict()

    rows = []
    for course_id in all_course_ids:
        historical = latest_by_course.get(course_id)
        interest_count = int(interest_counts.get(course_id, 0))
        has_history = historical is not None
        source_term_id = historical["source_term_id"] if has_history else None
        last_enrollment = historical["last_enrollment"] if has_history else None
        registrations = historical["registrations"] if has_history else None
        unmet = historical["unmet"] if has_history else None
        history_count = historical["history_count"] if has_history else 0

        fallback_applied = False
        fallback_reason = ""
        if history_count < 2:
            fallback_applied = True
            if interest_count > 0:
                forecast = interest_count
                method = "ELIGIBLE_REGISTRATION_INTEREST_FALLBACK"
                fallback_reason = "INSUFFICIENT_HISTORY_USE_ELIGIBLE_INTEREST_COUNT"
            elif has_history:
                forecast = last_enrollment
                method = "LAST_OBSERVATION_FALLBACK"
                fallback_reason = "INSUFFICIENT_HISTORY_USE_LAST_ENROLLMENT"
            else:
                forecast = 0
                method = "ZERO_FALLBACK"
                fallback_reason = "NO_HISTORY_OR_ELIGIBLE_INTEREST"
        elif model is not None:
            features = pd.DataFrame([{
                "last_enrollment": last_enrollment,
                "registrations": registrations,
                "unmet": unmet,
            }])
            forecast = float(model.predict(features[FEATURES])[0])
            method = "RandomForestRegressor"
        else:
            forecast = last_enrollment
            method = "LAST_OBSERVATION_FALLBACK"
            fallback_applied = True
            fallback_reason = "NO_TRAINING_TRANSITIONS_USE_LAST_ENROLLMENT"

        rows.append({
            "course_id": course_id,
            "target_term": target_term,
            "source_term_id": source_term_id,
            "forecast_enrollment": int(max(0, np.rint(forecast))),
            "baseline_forecast": (
                int(np.rint(last_enrollment)) if has_history else interest_count
            ),
            "model_name": method,
            "last_enrollment": last_enrollment,
            "registrations": registrations,
            "unmet_demand_input": unmet,
            "eligible_interest_count": interest_count,
            "fallback_applied": fallback_applied,
            "fallback_reason": fallback_reason,
        })

    out = pd.DataFrame(rows, columns=[
        "course_id",
        "target_term",
        "source_term_id",
        "forecast_enrollment",
        "baseline_forecast",
        "model_name",
        "last_enrollment",
        "registrations",
        "unmet_demand_input",
        "eligible_interest_count",
        "fallback_applied",
        "fallback_reason",
    ])
    return out, {
        "evaluation_term": terms[-1] if len(terms) > 1 else None,
        "evaluation_observations": len(test),
        "mae": mae,
        "rmse": rmse,
        "baseline_mae": baseline_mae,
        "baseline_rmse": baseline_rmse,
        "courses_forecasted": len(out),
    }
