from dataclasses import dataclass


@dataclass
class TrialBudget:
    """Budget for hypothesis experimentation. Exceeded = freeze + selection-bias analysis."""

    max_parameter_trials: int = 12
    max_feature_trials: int = 6
    max_data_transformations: int = 3
    max_model_classes: int = 2
    final_holdout_boundary: str = "locked"

    # Current counts
    parameter_trials_used: int = 0
    feature_trials_used: int = 0
    data_transformations_used: int = 0
    model_classes_used: int = 0

    def remaining(self) -> dict:
        return {
            "parameter_trials": self.max_parameter_trials - self.parameter_trials_used,
            "feature_trials": self.max_feature_trials - self.feature_trials_used,
            "data_transformations": self.max_data_transformations - self.data_transformations_used,
            "model_classes": self.max_model_classes - self.model_classes_used,
        }

    def is_exceeded(self) -> bool:
        return (
            self.parameter_trials_used > self.max_parameter_trials
            or self.feature_trials_used > self.max_feature_trials
            or self.data_transformations_used > self.max_data_transformations
            or self.model_classes_used > self.max_model_classes
        )

    def is_frozen(self) -> bool:
        return self.is_exceeded()

    def increment_parameter(self) -> tuple[bool, str]:
        if self.parameter_trials_used >= self.max_parameter_trials:
            return False, f"BUDGET_EXCEEDED:parameter {self.parameter_trials_used}/{self.max_parameter_trials}"
        self.parameter_trials_used += 1
        return True, f"parameter trial {self.parameter_trials_used}/{self.max_parameter_trials}"

    def increment_feature(self) -> tuple[bool, str]:
        if self.feature_trials_used >= self.max_feature_trials:
            return False, f"BUDGET_EXCEEDED:feature {self.feature_trials_used}/{self.max_feature_trials}"
        self.feature_trials_used += 1
        return True, f"feature trial {self.feature_trials_used}/{self.max_feature_trials}"

    def increment_data_transform(self) -> tuple[bool, str]:
        if self.data_transformations_used >= self.max_data_transformations:
            return (
                False,
                f"BUDGET_EXCEEDED:data_transform {self.data_transformations_used}/{self.max_data_transformations}",
            )
        self.data_transformations_used += 1
        return True, f"data transform {self.data_transformations_used}/{self.max_data_transformations}"

    def increment_model_class(self) -> tuple[bool, str]:
        if self.model_classes_used >= self.max_model_classes:
            return False, f"BUDGET_EXCEEDED:model_class {self.model_classes_used}/{self.max_model_classes}"
        self.model_classes_used += 1
        return True, f"model class {self.model_classes_used}/{self.max_model_classes}"

    def summary(self) -> dict:
        return {
            "remaining": self.remaining(),
            "is_exceeded": self.is_exceeded(),
            "is_frozen": self.is_frozen(),
        }
