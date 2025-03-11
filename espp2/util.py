from enum import Enum


class FeatureFlagEnum(Enum):
    # Generate synthetic dividends records from the stocks API
    FEATURE_SYNDIV = "synthetic-dividend"
    # Do not use the taxfree deduction against dividends
    FEATURE_TFD_ACCUMULATE = "taxfree-deduction-accumulate"
