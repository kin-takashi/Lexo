"""Tải bge-reranker-v2-m3 (bản ONNX) về thư mục models/bge-reranker-v2-m3. Cần mạng MỘT LẦN, ~2,3 GB; sau đó chạy offline.

  python scripts/tai_xep_lai.py
  pip install onnxruntime tokenizers        # thư viện chạy mô hình
"""
from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOC = "https://huggingface.co/onnx-community/bge-reranker-v2-m3-ONNX/resolve/main/"
TEP = ["config.json", "tokenizer.json", "tokenizer_config.json", "special_tokens_map.json", "onnx/model.onnx", "onnx/model.onnx_data"]


def main() -> int:
    dich = ROOT / "models" / "bge-reranker-v2-m3"
    for t in TEP:
        f = dich / t
        f.parent.mkdir(parents=True, exist_ok=True)
        if f.exists() and f.stat().st_size > 0:
            print(f"có sẵn: {t}")
            continue
        tam = f.with_suffix(f.suffix + ".part")
        print(f"tải {t} ...", flush=True)
        try:
            with urllib.request.urlopen(GOC + t, timeout=60) as r, open(tam, "wb") as o:
                tong, da = int(r.headers.get("Content-Length") or 0), 0
                while True:
                    kh = r.read(1 << 20)
                    if not kh:
                        break
                    o.write(kh)
                    da += len(kh)
                    if tong and (da // (1 << 20)) % 100 == 0:
                        print(f"  {da / tong:.0%}", end="\r", flush=True)
        except OSError as e:
            sys.exit(f"LỖI khi tải {t}: {e}. Chạy lại lệnh này để tải tiếp (các tệp đã xong được giữ).")
        tam.replace(f)
    print("Xong. Thư viện cần: pip install onnxruntime tokenizers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
