import os
import time
import base64
import re
from typing import Any, Dict

from openai import AzureOpenAI

from .base import OCRAdapter


def _to_data_url(mime_type: str, data: bytes) -> str:
    b64 = base64.b64encode(data).decode("utf-8")
    return f"data:{mime_type};base64,{b64}"


def _clean_text(text: str) -> str:
    if not text:
        return ""

    # Convert simple HTML bold tags -> Markdown bold
    text = re.sub(r"<\s*b\s*>", "**", text, flags=re.IGNORECASE)
    text = re.sub(r"<\s*/\s*b\s*>", "**", text, flags=re.IGNORECASE)

    # Remove other HTML tags if they appear
    text = re.sub(r"</?[^>]+>", "", text)

    # Normalize excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text


class GPT52Adapter(OCRAdapter):
    def __init__(self):
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT", "").strip().rstrip("/")
        api_key = os.getenv("AZURE_OPENAI_API_KEY", "").strip()
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-01-01-preview").strip()
        deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT", "").strip()

        if not endpoint:
            raise RuntimeError("AZURE_OPENAI_ENDPOINT missing in backend .env")
        if not api_key:
            raise RuntimeError("AZURE_OPENAI_API_KEY missing in backend .env")
        if not deployment:
            raise RuntimeError("AZURE_OPENAI_DEPLOYMENT missing in backend .env")

        self.client = AzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version,
        )
        self.deployment = deployment

    def run(self, image_bytes: bytes, filename: str, mime_type: str) -> Dict[str, Any]:
        t0 = time.time()

        prompt = (
            "You are a high-accuracy OCR engine.\n"
            "Extract ALL visible text from the document.\n\n"
            "OUTPUT FORMAT (VERY IMPORTANT):\n"
            "- Output MUST be ONLY the extracted content.\n"
            "- Use Markdown to preserve structure.\n"
            "- Use headings for section titles when present.\n"
            "- If there is a table (invoice items, totals, etc.), output it as a proper Markdown table using | pipes.\n"
            "- Preserve line breaks.\n"
            "- Do NOT add commentary, explanations, or analysis.\n"
            "- Do NOT say: 'here is the extracted text'.\n"
            "- Do NOT wrap output in code fences.\n\n"
            "QUALITY RULES:\n"
            "- Keep numbers exactly as seen (including commas and decimals).\n"
            "- Keep labels and values on the same line when they appear that way.\n"
            "- If a field is missing/unclear, omit it (do not hallucinate).\n"
        )

        image_url = _to_data_url(mime_type, image_bytes)

        try:
            resp = self.client.chat.completions.create(
                model=self.deployment,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {"type": "image_url", "image_url": {"url": image_url}},
                        ],
                    }
                ],
                temperature=0,
            )
        except Exception as e:
            raise RuntimeError(f"Azure OpenAI request failed: {e}") from e

        text = ""
        try:
            text = resp.choices[0].message.content or ""
        except Exception:
            text = ""

        text = _clean_text(text)

        latency_ms = int((time.time() - t0) * 1000)

        return {
            "text": text,
            "latency_ms": latency_ms,
            "raw": resp.model_dump() if hasattr(resp, "model_dump") else str(resp),
        }