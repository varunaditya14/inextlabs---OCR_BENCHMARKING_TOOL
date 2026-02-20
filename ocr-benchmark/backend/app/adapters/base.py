from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict


class OCRAdapter(ABC):
    """
    Standard adapter interface.
    All adapters must implement run() with the same signature.

    NOTE:
    - Many adapters are blocking (CPU / torch) -> called via threadpool.
    - Some adapters can optionally implement run_async() (API calls).
    """

    @abstractmethod
    def run(self, image_bytes: bytes, filename: str, mime_type: str) -> Dict[str, Any]:
        raise NotImplementedError

    async def run_async(self, image_bytes: bytes, filename: str, mime_type: str) -> Dict[str, Any]:
        """
        Optional async version (for API/network adapters).
        Default fallback just calls sync run().
        """
        return self.run(image_bytes=image_bytes, filename=filename, mime_type=mime_type)