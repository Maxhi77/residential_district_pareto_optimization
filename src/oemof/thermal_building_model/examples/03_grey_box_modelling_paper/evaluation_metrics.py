import numpy as np
import pandas as pd


def align_series(reference, prediction):
    """
    Align measured/reference and simulated/predicted time series.

    reference:
        Measurement / reference values r

    prediction:
        Simulation / prediction values p
    """

    data = pd.concat(
        [
            reference.rename("reference"),
            prediction.rename("prediction"),
        ],
        axis=1,
        join="inner",
    ).dropna()

    if data.empty:
        raise ValueError(
            "Reference and prediction have no overlapping valid data."
        )

    # Paper definition:
    # error = reference - prediction
    data["error"] = (
        data["reference"]
        - data["prediction"]
    )

    return data


def rmse(reference, prediction):
    """
    Root Mean Squared Error according to Nouri et al.

    RMSE = sqrt(1/n * sum((r - p)^2))
    """

    data = align_series(reference, prediction)

    return np.sqrt(
        np.mean(data["error"] ** 2)
    )


def mae(reference, prediction):
    """
    Mean Absolute Error.

    Not one of the five indices used in the Nouri et al. paper,
    but included for the requested evaluation matrix.
    """

    data = align_series(reference, prediction)

    return np.mean(
        np.abs(data["error"])
    )


def mbe(reference, prediction):
    """
    Mean Bias Error according to Nouri et al.

    MBE = 1/n * sum(r - p)

    Positive:
        simulation underpredicts the reference on average

    Negative:
        simulation overpredicts the reference on average
    """

    data = align_series(reference, prediction)

    return np.mean(
        data["error"]
    )


def nmbe(reference, prediction):
    """
    Normalized Mean Bias Error according to Nouri et al.

    NMBE = sum(r-p) / (n * mean(r)) * 100
    """

    data = align_series(reference, prediction)

    mean_reference = data["reference"].mean()

    if mean_reference == 0:
        return np.nan

    return (
        data["error"].mean()
        / mean_reference
        * 100
    )


def cvrmse(reference, prediction):
    """
    Coefficient of Variation of RMSE according to Nouri et al.

    CVRMSE = RMSE / mean(reference) * 100
    """

    data = align_series(reference, prediction)

    mean_reference = data["reference"].mean()

    if mean_reference == 0:
        return np.nan

    return (
        np.sqrt(np.mean(data["error"] ** 2))
        / mean_reference
        * 100
    )


def r_squared(reference, prediction):
    """
    Coefficient of determination according to the equation
    used in Nouri et al.

    R² = 1 - sum((r-p)^2) / sum((r-mean(r))^2)
    """

    data = align_series(reference, prediction)

    reference_values = data["reference"]
    prediction_values = data["prediction"]

    ss_res = np.sum(
        (reference_values - prediction_values) ** 2
    )

    ss_tot = np.sum(
        (reference_values - reference_values.mean()) ** 2
    )

    if ss_tot == 0:
        return np.nan

    return 1 - ss_res / ss_tot


def period_rmse(reference, prediction, period="12h"):
    """
    Calculate RMSE separately for each time period.

    Examples
    --------
    period="h"   -> hourly RMSE
    period="12h" -> half-day RMSE
    period="24h" -> daily RMSE
    """

    data = align_series(reference, prediction)

    squared_error = data["error"] ** 2

    return (
        squared_error
        .resample(period)
        .mean()
        .pow(0.5)
        .rename(f"RMSE_{period}")
    )


def peak_error(reference, prediction):
    """
    Compare maximum reference and simulated temperatures.

    Returns both peak magnitude error and peak timing error.
    """

    data = align_series(reference, prediction)

    reference_peak = data["reference"].max()
    prediction_peak = data["prediction"].max()

    reference_peak_time = data["reference"].idxmax()
    prediction_peak_time = data["prediction"].idxmax()

    # Paper sign convention: reference - prediction
    peak_magnitude_error = (
        reference_peak - prediction_peak
    )

    peak_timing_error = (
        prediction_peak_time
        - reference_peak_time
    ).total_seconds() / 3600

    return {
        "Reference peak [°C]": reference_peak,
        "Prediction peak [°C]": prediction_peak,
        "Peak error [K]": peak_magnitude_error,
        "Absolute peak error [K]": abs(
            peak_magnitude_error
        ),
        "Reference peak time": reference_peak_time,
        "Prediction peak time": prediction_peak_time,
        "Peak timing error [h]": peak_timing_error,
    }


def evaluate_temperature(reference, prediction):
    """
    Complete temperature evaluation.
    """

    return {
        "RMSE [K]": rmse(reference, prediction),
        "MAE [K]": mae(reference, prediction),
        "MBE [K]": mbe(reference, prediction),
        "NMBE [%]": nmbe(reference, prediction),
        "CVRMSE [%]": cvrmse(reference, prediction),
        "R2 [-]": r_squared(reference, prediction),
    }