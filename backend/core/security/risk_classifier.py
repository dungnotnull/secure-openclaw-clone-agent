from __future__ import annotations

import asyncio
import logging
from typing import Optional

from backend.core.config import settings
from backend.core.models.action import ActionRecord, RiskTier

logger = logging.getLogger(__name__)

_classifier_instance: Optional["RiskClassifier"] = None


class RiskClassifier:
    def __init__(self, model_id: str | None = None) -> None:
        self._model_id = model_id or "facebook/bart-large-mnli"
        self._pipeline = None
        self._labels = [
            "read-only file or data access",
            "low-risk file modification or creation",
            "high-risk destructive operation or deletion",
            "network access or external API call",
        ]
        self._local_model = None

    def _ensure_pipeline(self):
        if self._pipeline is None:
            try:
                from transformers import pipeline
                self._pipeline = pipeline(
                    "zero-shot-classification",
                    model=self._model_id,
                    device=-1,
                )
            except Exception as exc:
                logger.warning(
                    "Risk classifier model not available: %s. Using heuristic fallback.", exc
                )
                self._pipeline = False

    def classify(self, action: ActionRecord) -> RiskTier:
        description = action.action_type
        if action.parameters:
            description += " " + str(action.parameters)

        if self._pipeline is None:
            self._ensure_pipeline()

        if self._pipeline and self._pipeline is not False:
            return self._ml_classify(description)
        return self._heuristic_classify(action)

    def _ml_classify(self, description: str) -> RiskTier:
        try:
            result = self._pipeline(description, self._labels, multi_label=False)
            label = result["labels"][0]
            mapping = {
                self._labels[0]: RiskTier.READ_ONLY,
                self._labels[1]: RiskTier.LOW_RISK_WRITE,
                self._labels[2]: RiskTier.HIGH_RISK_DESTRUCTIVE,
                self._labels[3]: RiskTier.NETWORK_EGRESS,
            }
            return mapping.get(label, RiskTier.READ_ONLY)
        except Exception as exc:
            logger.warning("ML classification failed: %s", exc)
            return RiskTier.LOW_RISK_WRITE

    def _heuristic_classify(self, action: ActionRecord) -> RiskTier:
        action_type = action.action_type.lower()
        params_str = str(action.parameters).lower() if action.parameters else ""

        if "api_call" in action_type or "fetch" in action_type or "http" in params_str:
            return RiskTier.NETWORK_EGRESS
        if any(kw in params_str for kw in ["rm ", "delete", "drop ", "truncate",
                                              "format", "mkfs", "dd if="]):
            return RiskTier.HIGH_RISK_DESTRUCTIVE
        if "file_read" in action_type or "read" in action_type or "cat " in params_str:
            return RiskTier.READ_ONLY
        return RiskTier.LOW_RISK_WRITE


def get_risk_classifier() -> RiskClassifier:
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = RiskClassifier()
    return _classifier_instance
