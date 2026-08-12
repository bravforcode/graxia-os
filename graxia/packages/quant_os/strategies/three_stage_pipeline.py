"""
3-Stage Trading Pipeline.
Stage 1: Volatility Engine → σ̂ per instrument
Stage 2: Regime Gate → position_scale [0, 1.5]
Stage 3: Factor Signals → signal ∈ {-1, 0, +1}
Final: position = signal × scale × (σ_target/σ̂) × capital
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class PipelineResult:
    """3-stage pipeline result."""
    # Stage 1 outputs
    forecast_vol: float
    realized_vol: float

    # Stage 2 outputs
    regime: str
    regime_scale: float

    # Stage 3 outputs
    factor_signal: float
    factor_confidence: float

    # Final output
    position_size: float
    position_side: str  # LONG/SHORT/FLAT

    # Diagnostics
    vol_target: float
    vol_ratio: float


class ThreeStagePipeline:
    """
    Unified 3-stage trading pipeline.

    Stage 1: Volatility Engine (HAR forecast)
    Stage 2: Regime Gate (vol-ratio classification)
    Stage 3: Factor Signals (TSMOM + Carry + Pairs MR)
    Final:   Position = signal × scale × (σ_target / σ̂) × capital
    """

    def __init__(
        self,
        vol_target: float = 0.10,  # 10% annualized vol target
        capital: float = 100_000,
        max_position_pct: float = 0.20,  # Max 20% of capital per position
    ):
        self.vol_target = vol_target
        self.capital = capital
        self.max_position_pct = max_position_pct

        # Lazy-load components
        self._vol_features = None
        self._har_model = None
        self._regime_classifier = None
        self._factor_signals = None

    def _get_vol_features(self):
        if self._vol_features is None:
            from core.volatility_features import build_volatility_features
            self._vol_features = build_volatility_features
        return self._vol_features

    def _get_har_model(self):
        if self._har_model is None:
            from ml.har_model import HARModel
            self._har_model = HARModel()
        return self._har_model

    def _get_regime_classifier(self):
        if self._regime_classifier is None:
            from ml.regime_classifier import RegimeClassifier
            self._regime_classifier = RegimeClassifier()
        return self._regime_classifier

    def _get_factor_signals(self):
        if self._factor_signals is None:
            from strategies.factor_signals import compute_factor_signals
            self._factor_signals = compute_factor_signals
        return self._factor_signals

    def run(
        self,
        df: pd.DataFrame,
        base_rate: pd.Series | None = None,
        quote_rate: pd.Series | None = None,
        pairs_price: pd.Series | None = None,
    ) -> PipelineResult:
        """
        Run 3-stage pipeline on OHLCV data.

        Args:
            df: DataFrame with columns ['open', 'high', 'low', 'close', 'volume']
            base_rate: Interest rate for base currency (optional)
            quote_rate: Interest rate for quote currency (optional)
            pairs_price: Price of paired asset (optional)

        Returns:
            PipelineResult with all stage outputs and final position
        """
        close = df['close']

        # Stage 1: Volatility Engine
        vol_features = self._get_vol_features()(df)
        realized_vol = vol_features.realized_vol.iloc[-1]

        # HAR forecast (fit on history, predict next)
        har = self._get_har_model()
        har.fit(vol_features.realized_vol.dropna())
        forecast_vol = har.predict(vol_features.realized_vol.dropna(), steps=1).iloc[0]

        # Stage 2: Regime Gate
        regime_result = self._get_regime_classifier().classify(close, df.get('high'), df.get('low'))

        # Stage 3: Factor Signals
        factor_result = self._get_factor_signals()(
            close,
            base_rate=base_rate,
            quote_rate=quote_rate,
            pairs_price=pairs_price,
        )

        # Final: Position Sizing
        signal = factor_result.combined_signal.iloc[-1]
        scale = regime_result.position_scale
        vol_ratio = self.vol_target / max(forecast_vol, 0.01)

        # Cap vol ratio at 2x to avoid excessive leverage
        vol_ratio = min(vol_ratio, 2.0)

        # Position = signal × scale × vol_ratio × capital × max_position_pct
        position_value = signal * scale * vol_ratio * self.capital * self.max_position_pct

        # Cap at max_position_pct of capital
        position_value = np.clip(
            position_value,
            -self.capital * self.max_position_pct,
            self.capital * self.max_position_pct,
        )

        # Determine side
        if position_value > 0:
            side = "LONG"
        elif position_value < 0:
            side = "SHORT"
        else:
            side = "FLAT"

        return PipelineResult(
            forecast_vol=forecast_vol,
            realized_vol=realized_vol,
            regime=regime_result.regime.value,
            regime_scale=scale,
            factor_signal=signal,
            factor_confidence=factor_result.confidence.iloc[-1],
            position_size=abs(position_value),
            position_side=side,
            vol_target=self.vol_target,
            vol_ratio=vol_ratio,
        )

    def run_walk_forward(
        self,
        df: pd.DataFrame,
        train_pct: float = 0.7,
        **kwargs,
    ) -> pd.DataFrame:
        """
        Walk-forward test of 3-stage pipeline.

        Returns:
            DataFrame with daily results
        """
        n_train = int(len(df) * train_pct)
        results = []

        for i in range(n_train, len(df)):
            # Use expanding window
            train_df = df.iloc[:i + 1]

            try:
                result = self.run(train_df, **kwargs)
                results.append({
                    "timestamp": df.index[i] if hasattr(df.index, '__getitem__') else i,
                    "regime": result.regime,
                    "regime_scale": result.regime_scale,
                    "factor_signal": result.factor_signal,
                    "position_size": result.position_size,
                    "position_side": result.position_side,
                    "forecast_vol": result.forecast_vol,
                    "realized_vol": result.realized_vol,
                    "vol_ratio": result.vol_ratio,
                })
            except Exception:
                continue

        return pd.DataFrame(results)
