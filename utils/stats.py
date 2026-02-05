"""Statistical helpers — LOWESS smoothing, projections, confidence intervals."""

import numpy as np


def lowess_smooth(x, y, smoothing=5):
    """Apply LOWESS smoothing.

    Args:
        x: array-like of x values (numeric or datetime ordinals)
        y: array-like of y values
        smoothing: slider value 0-10, mapped to frac 0.01-0.50

    Returns:
        numpy array of smoothed y values
    """
    from statsmodels.nonparametric.smoothers_lowess import lowess

    x_numeric = np.asarray(x, dtype=float)
    y_numeric = np.asarray(y, dtype=float)

    mask = ~(np.isnan(x_numeric) | np.isnan(y_numeric))
    if mask.sum() < 3:
        return y_numeric

    frac = 0.01 + (smoothing / 10) * 0.49
    result = lowess(y_numeric[mask], x_numeric[mask], frac=frac, return_sorted=False)

    out = np.full_like(y_numeric, np.nan)
    out[mask] = result
    return out


def year_end_projection(last_value, days_elapsed, days_in_year=365):
    """Simple linear year-end projection."""
    if days_elapsed <= 0:
        return None
    return last_value * (days_in_year / days_elapsed)


def confidence_interval_95(values):
    """Calculate 95% CI as mean +/- 1.96*std."""
    arr = np.asarray(values, dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) < 2:
        return None, None, None
    mean = np.mean(arr)
    std = np.std(arr, ddof=1)
    return mean, mean - 1.96 * std, mean + 1.96 * std


def normalize_leap_year(day_of_year, is_leap):
    """Shift days after Feb 29 back by 1 in leap years for YoY comparison."""
    if is_leap:
        adjusted = day_of_year.copy()
        adjusted[adjusted > 60] -= 1
        return adjusted
    return day_of_year
