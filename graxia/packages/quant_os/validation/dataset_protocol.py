"""Phase BE-P6 — Dataset protocol: train/validation/holdout."""
from dataclasses import dataclass


@dataclass
class DatasetSplit:
    name: str
    start_date: str
    end_date: str
    purpose: str  # train, validation, holdout
    
    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "purpose": self.purpose,
        }


class DatasetProtocol:
    """Define and enforce train/validation/holdout splits."""
    
    def __init__(self):
        self._splits: list[DatasetSplit] = []
        self._final_holdout_used: bool = False
    
    def add_split(self, split: DatasetSplit) -> None:
        self._splits.append(split)
    
    def get_splits(self) -> list[DatasetSplit]:
        return self._splits.copy()
    
    def get_train_splits(self) -> list[DatasetSplit]:
        return [s for s in self._splits if s.purpose == "train"]
    
    def get_validation_splits(self) -> list[DatasetSplit]:
        return [s for s in self._splits if s.purpose == "validation"]
    
    def get_holdout(self) -> DatasetSplit | None:
        for s in self._splits:
            if s.purpose == "holdout":
                return s
        return None
    
    def mark_holdout_used(self) -> None:
        self._final_holdout_used = True
    
    def is_holdout_used(self) -> bool:
        return self._final_holdout_used
    
    def validate_no_overlap(self) -> tuple[bool, list[str]]:
        """Check that splits don't overlap in time."""
        issues = []
        for i, a in enumerate(self._splits):
            for b in self._splits[i+1:]:
                if a.start_date <= b.end_date and b.start_date <= a.end_date:
                    issues.append(f"overlap: {a.name} and {b.name}")
        return len(issues) == 0, issues
    
    @classmethod
    def default_xauusd(cls) -> "DatasetProtocol":
        """Default protocol for XAUUSD. User must fill actual dates."""
        protocol = cls()
        protocol.add_split(DatasetSplit("train", "2020-01-01", "2024-06-30", "train"))
        protocol.add_split(DatasetSplit("validation", "2024-07-01", "2025-06-30", "validation"))
        protocol.add_split(DatasetSplit("holdout", "2025-07-01", "2026-06-30", "holdout"))
        return protocol
