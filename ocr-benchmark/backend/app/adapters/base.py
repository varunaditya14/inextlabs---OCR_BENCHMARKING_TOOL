from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class OCRAdapter(ABC):
    @abstractmethod
    def run(self, filename: str, file_bytes: bytes) -> Dict[str, Any]:
        raise NotImplementedError
