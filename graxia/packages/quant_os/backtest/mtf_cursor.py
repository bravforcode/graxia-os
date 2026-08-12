"""
Multi-Timeframe Cursor — prevents look-ahead leakage.

Every timeframe's data is sliced to only include bars with
timestamp <= as_of. Incomplete bars (current forming bar) are excluded.

This is the ONLY safe way to provide multi-TF data to strategies.
"""

from datetime import datetime


class MultiTimeframeCursor:
    """
    Provides point-in-time sliced multi-timeframe data.

    Usage:
        cursor = MultiTimeframeCursor(d1_data, d1_ts, h1_data, h1_ts, m15_data, m15_ts)

        # During engine loop at D1 bar index i:
        sliced = cursor.slice_as_of(d1_ts[i])
        # sliced["H1"]["close"] only contains H1 bars with ts <= d1_ts[i]
        # sliced["M15"]["close"] only contains M15 bars with ts <= d1_ts[i]
    """

    def __init__(
        self,
        d1_data: dict[str, list],
        d1_ts: list[datetime],
        h1_data: dict[str, list] | None = None,
        h1_ts: list[datetime] | None = None,
        m15_data: dict[str, list] | None = None,
        m15_ts: list[datetime] | None = None,
    ):
        self._data = {
            "D1": (d1_data, d1_ts),
        }
        if h1_data is not None and h1_ts is not None:
            self._data["H1"] = (h1_data, h1_ts)
        if m15_data is not None and m15_ts is not None:
            self._data["M15"] = (m15_data, m15_ts)

        # Pre-sort indices by timestamp for binary search
        self._sorted_indices = {}
        for tf, (_, ts_list) in self._data.items():
            self._sorted_indices[tf] = sorted(range(len(ts_list)), key=lambda i: ts_list[i])

    def slice_as_of(self, as_of: datetime) -> dict[str, dict[str, list]]:
        """
        Return multi-TF data sliced to timestamp <= as_of.

        Only complete bars are included (the bar AT as_of is the current
        base bar — lower TF bars at the same timestamp are included since
        they would have closed at or before the base bar's close).
        """
        result = {}

        for tf, (data, ts_list) in self._data.items():
            # Find rightmost index where ts <= as_of via sorted order
            sorted_idx = self._sorted_indices[tf]
            count = 0
            for idx in sorted_idx:
                if ts_list[idx] <= as_of:
                    count += 1
                else:
                    break

            if count == 0:
                # No data available yet for this TF
                result[tf] = {k: [] for k in data.keys()}
            else:
                result[tf] = {k: [data[k][i] for i in sorted_idx[:count]] for k in data.keys()}

        return result

    def slice_as_of_exclusive(self, as_of: datetime) -> dict[str, dict[str, list]]:
        """
        Return multi-TF data sliced to timestamp < as_of (exclusive).
        Used when the base bar itself should not be visible to lower TFs.
        """
        result = {}

        for tf, (data, ts_list) in self._data.items():
            sorted_idx = self._sorted_indices[tf]
            count = 0
            for idx in sorted_idx:
                if ts_list[idx] < as_of:
                    count += 1
                else:
                    break

            if count == 0:
                result[tf] = {k: [] for k in data.keys()}
            else:
                result[tf] = {k: [data[k][i] for i in sorted_idx[:count]] for k in data.keys()}

        return result
