"""
HAR (Heterogeneous Autoregressive) model for volatility forecasting.
Corsi (2009): Realized vol is best predicted by daily, weekly, monthly vol.
R² > 0.3 achievable with simple HAR.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class HARResult:
    """HAR model forecast result."""

    forecast: pd.Series
    r_squared: float
    coefficients: dict
    residuals: pd.Series


class HARModel:
    """
    Heterogeneous Autoregressive model.
    Predicts tomorrow's realized vol from:
    - RV_day: daily realized vol
    - RV_week: weekly average vol
    - RV_month: monthly average vol
    """

    def __init__(self):
        self.coefficients: dict | None = None

    def fit(self, realized_vol: pd.Series) -> dict:
        """
        Fit HAR model to realized volatility series.

        Args:
            realized_vol: Daily realized volatility series

        Returns:
            Dict with coefficients and fit statistics
        """
        rv = realized_vol.dropna()
        df = pd.DataFrame(
            {
                "rv_t": rv,
                "rv_t-1": rv.shift(1),
                "rv_week": rv.rolling(5).mean().shift(1),
                "rv_month": rv.rolling(22).mean().shift(1),
            }
        ).dropna()

        X = df[["rv_t-1", "rv_week", "rv_month"]].values
        y = df["rv_t"].values

        X_with_intercept = np.column_stack([np.ones(len(X)), X])

        try:
            beta = np.linalg.lstsq(X_with_intercept, y, rcond=None)[0]
        except np.linalg.LinAlgError:
            return {"b0": 0, "b1": 0, "b2": 0, "b3": 0, "r_squared": 0}

        y_pred = X_with_intercept @ beta

        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

        self.coefficients = {
            "b0": beta[0],
            "b1": beta[1],
            "b2": beta[2],
            "b3": beta[3],
        }

        return {
            **self.coefficients,
            "r_squared": r_squared,
            "n_observations": len(df),
        }

    def predict(self, realized_vol: pd.Series, steps: int = 1) -> pd.Series:
        """
        Forecast future volatility.

        Args:
            realized_vol: Recent realized volatility series
            steps: Number of days to forecast

        Returns:
            Forecasted volatility series
        """
        if self.coefficients is None:
            raise ValueError("Model not fitted. Call fit() first.")

        forecasts = []
        rv_history = realized_vol.dropna().tolist()

        for _ in range(steps):
            rv_day = rv_history[-1] if len(rv_history) >= 1 else 0
            rv_week = np.mean(rv_history[-5:]) if len(rv_history) >= 5 else rv_day
            rv_month = np.mean(rv_history[-22:]) if len(rv_history) >= 22 else rv_week

            forecast = (
                self.coefficients["b0"]
                + self.coefficients["b1"] * rv_day
                + self.coefficients["b2"] * rv_week
                + self.coefficients["b3"] * rv_month
            )

            forecasts.append(max(0, forecast))
            rv_history.append(forecast)

        return pd.Series(
            forecasts,
            index=range(len(realized_vol), len(realized_vol) + steps),
        )

    def evaluate(self, realized_vol: pd.Series, test_size: int = 60) -> HARResult:
        """
        Evaluate HAR model with walk-forward test.

        Args:
            realized_vol: Full realized volatility series
            test_size: Number of periods for out-of-sample test

        Returns:
            HARResult with forecast, R², coefficients, residuals
        """
        train = realized_vol[:-test_size]
        test = realized_vol[-test_size:]

        self.fit(train)

        forecasts = []
        for i in range(test_size):
            history = realized_vol[: len(train) + i]
            pred = self.predict(history, steps=1)
            forecasts.append(pred.iloc[0])

        forecast_series = pd.Series(forecasts, index=test.index)
        residuals = test - forecast_series

        ss_res = np.sum(residuals**2)
        ss_tot = np.sum((test - test.mean()) ** 2)
        oos_r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

        return HARResult(
            forecast=forecast_series,
            r_squared=oos_r_squared,
            coefficients=self.coefficients,
            residuals=residuals,
        )
