from __future__ import annotations

import logging
from typing import Optional

from backend.core.config import settings

logger = logging.getLogger(__name__)


class LocalTaskPlanner:
    def __init__(
        self,
        model_id: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self._model_id = model_id or "microsoft/phi-3-mini-4k-instruct"
        self._base_url = base_url or settings.OLLAMA_BASE_URL
        self._available = False

    async def check_availability(self) -> bool:
        try:
            import httpx
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(f"{self._base_url}/api/tags")
                if resp.status_code != 200:
                    return False
                models = resp.json().get("models", [])
                for m in models:
                    if self._model_id in m.get("name", ""):
                        self._available = True
                        return True
                return False
        except Exception:
            return False

    async def plan(
        self,
        instruction: str,
        tools_description: str,
    ) -> str:
        import httpx

        system_prompt = f"""You are a task planning agent. Given a user instruction, break it down into an ordered list of subtasks.
Each subtask must use exactly one tool from this list:
{tools_description}

Return a JSON array of objects: [{{"description": "...", "tool": "...", "parameters": {{...}}, "order": 1}}]
Return ONLY the JSON array, no other text."""

        body = {
            "model": self._model_id,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": instruction},
            ],
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 2048},
        }

        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                f"{self._base_url}/api/chat",
                json=body,
                headers={"Content-Type": "application/json"},
            )
            resp.raise_for_status()
            data = resp.json()
            return data.get("message", {}).get("content", "")


class CodePatchGenerator:
    def __init__(self, model_id: str | None = None) -> None:
        self._model_id = model_id or "Salesforce/codet5p-220m"
        self._pipeline = None
        self._available = False

    def load(self) -> bool:
        try:
            from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
            self._tokenizer = AutoTokenizer.from_pretrained(self._model_id)
            self._model = AutoModelForSeq2SeqLM.from_pretrained(self._model_id)
            self._available = True
            logger.info("CodePatchGenerator loaded: %s", self._model_id)
            return True
        except Exception as exc:
            logger.warning(
                "CodePatchGenerator model not available: %s. Falling back to LLM.", exc
            )
            self._available = False
            return False

    def generate_patch(
        self,
        original_code: str,
        instruction: str,
        max_length: int = 512,
    ) -> str:
        if not self._available:
            raise RuntimeError("CodePatchGenerator model not loaded")

        prompt = f"Code: {original_code}\n\nInstruction: {instruction}\n\nPatch:"
        inputs = self._tokenizer(prompt, return_tensors="pt", truncation=True, max_length=1024)
        outputs = self._model.generate(
            **inputs,
            max_length=max_length,
            num_beams=3,
            early_stopping=True,
        )
        return self._tokenizer.decode(outputs[0], skip_special_tokens=True)


class FineTuningPipeline:
    def __init__(self, model_id: str = "distilbert-base-uncased") -> None:
        self._model_id = model_id
        self._labels = [
            "read_only",
            "low_risk_write",
            "high_risk_destructive",
            "network_egress",
        ]

    def prepare_dataset(
        self,
        labeled_examples: list[dict],
    ) -> tuple[list[str], list[int]]:
        texts: list[str] = []
        labels: list[int] = []
        for ex in labeled_examples:
            texts.append(ex.get("text", ""))
            label = ex.get("label", "low_risk_write")
            if label in self._labels:
                labels.append(self._labels.index(label))
            else:
                labels.append(1)
        return texts, labels

    def train(
        self,
        texts: list[str],
        labels: list[int],
        output_dir: str = "./data/fine-tuned-classifier",
        epochs: int = 3,
        batch_size: int = 8,
        learning_rate: float = 2e-5,
    ) -> str:
        import numpy as np

        try:
            from transformers import (
                AutoModelForSequenceClassification,
                AutoTokenizer,
                Trainer,
                TrainingArguments,
            )
            from datasets import Dataset
        except ImportError:
            raise ImportError(
                "Fine-tuning requires: pip install transformers datasets accelerate"
            )

        tokenizer = AutoTokenizer.from_pretrained(self._model_id)
        model = AutoModelForSequenceClassification.from_pretrained(
            self._model_id, num_labels=len(self._labels)
        )

        encodings = tokenizer(
            texts, truncation=True, padding=True, max_length=256
        )
        dataset = Dataset.from_dict({**encodings, "label": labels})
        dataset = dataset.train_test_split(test_size=0.1, seed=42)

        training_args = TrainingArguments(
            output_dir=output_dir,
            num_train_epochs=epochs,
            per_device_train_batch_size=batch_size,
            per_device_eval_batch_size=batch_size,
            learning_rate=learning_rate,
            evaluation_strategy="epoch",
            save_strategy="epoch",
            load_best_model_at_end=True,
            metric_for_best_model="accuracy",
        )

        def compute_metrics(eval_pred):
            from sklearn.metrics import accuracy_score, f1_score
            logits, labels = eval_pred
            preds = np.argmax(logits, axis=-1)
            return {
                "accuracy": accuracy_score(labels, preds),
                "f1_macro": f1_score(labels, preds, average="macro"),
            }

        trainer = Trainer(
            model=model,
            args=training_args,
            train_dataset=dataset["train"],
            eval_dataset=dataset["test"],
            tokenizer=tokenizer,
            compute_metrics=compute_metrics,
        )

        trainer.train()
        metrics = trainer.evaluate()
        trainer.save_model(output_dir)
        tokenizer.save_pretrained(output_dir)

        logger.info("Fine-tuning complete: %s", metrics)
        return output_dir


_local_planner: Optional[LocalTaskPlanner] = None
_patch_generator: Optional[CodePatchGenerator] = None
_fine_tuning: Optional[FineTuningPipeline] = None


def get_local_planner() -> LocalTaskPlanner:
    global _local_planner
    if _local_planner is None:
        _local_planner = LocalTaskPlanner()
    return _local_planner


def get_patch_generator() -> CodePatchGenerator:
    global _patch_generator
    if _patch_generator is None:
        _patch_generator = CodePatchGenerator()
    return _patch_generator


def get_fine_tuning_pipeline() -> FineTuningPipeline:
    global _fine_tuning
    if _fine_tuning is None:
        _fine_tuning = FineTuningPipeline()
    return _fine_tuning
