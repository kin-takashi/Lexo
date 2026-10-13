"""Tạo vector từ chữ. Hiện có hai bộ: Ollama (dùng thật) và HashEmbedder (chỉ để kiểm thử, không cần mô hình)."""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
import zlib


class EmbedError(RuntimeError):
    pass


class OllamaEmbedder:
    """Gọi Ollama /api/embed (cần Ollama chạy và đã `ollama pull <model>`)."""

    def __init__(self, model: str = "bge-m3", endpoint: str = "http://localhost:11434", timeout: int = 600, retries: int = 3):
        self.model, self.endpoint, self.timeout, self.retries = model, endpoint.rstrip("/"), timeout, retries

    @property
    def name(self) -> str:
        return f"ollama:{self.model}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        body = json.dumps({"model": self.model, "input": texts}).encode("utf-8")
        loi: Exception | None = None
        for lan in range(self.retries):
            req = urllib.request.Request(self.endpoint + "/api/embed", data=body, headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    out = json.loads(resp.read().decode("utf-8"))["embeddings"]
                if len(out) != len(texts):
                    raise EmbedError(f"Ollama trả {len(out)} vector cho {len(texts)} đoạn")
                return out
            except urllib.error.HTTPError as e:
                chi_tiet = e.read().decode("utf-8", "replace")[:300]
                if e.code == 404:
                    raise EmbedError(f"Ollama chưa có model '{self.model}'. Chạy: ollama pull {self.model} ({chi_tiet})") from e
                loi = EmbedError(f"Ollama báo lỗi HTTP {e.code}: {chi_tiet}")
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                loi = EmbedError(f"không kết nối được Ollama ở {self.endpoint} ({getattr(e, 'reason', e)}). Mở Ollama lên rồi chạy lại")
            if lan < self.retries - 1:
                time.sleep(2 ** (lan + 1))
        raise loi  # type: ignore[misc]


class HashEmbedder:
    """Vector giả bằng băm từ (feature hashing): chữ giống nhau thì vector gần nhau. CHỈ để kiểm thử đường ống,
    không phản ánh chất lượng tìm kiếm thật."""

    def __init__(self, dim: int = 256):
        self.dim = dim

    @property
    def name(self) -> str:
        return f"hash:{self.dim}"

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            v = [0.0] * self.dim
            ws = re.findall(r"\w+", t.lower())
            for tok in ws + [a + "_" + b for a, b in zip(ws, ws[1:])]:
                h = zlib.crc32(tok.encode("utf-8"))
                v[h % self.dim] += 1.0 if (h >> 16) & 1 else -1.0
            out.append(v)
        return out


def tu_config(cfg: dict, *, model: str | None = None, endpoint: str | None = None) -> OllamaEmbedder:
    emb = cfg.get("embedding") or {}
    local = cfg.get("llm_local") or {}
    return OllamaEmbedder(model or emb.get("ollama_model") or "bge-m3", endpoint or local.get("endpoint") or "http://localhost:11434")
