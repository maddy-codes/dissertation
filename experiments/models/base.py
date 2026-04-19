from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Dict

from experiments.types import GenerationResult, Technique


class ModelClient(ABC):
    @abstractmethod
    def generate_review_notes(
        self, *, context: str, prompt: str, technique: Technique
    ) -> GenerationResult:
        raise NotImplementedError

