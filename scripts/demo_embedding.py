"""Thử embedding bằng Ollama trên dữ liệu thật của Lexo (chỉ ĐỌC CSDL, không ghi gì).

Chạy:
    ollama pull bge-m3
    python scripts/demo_embedding.py                 # mặc định model bge-m3, Ollama ở localhost:11434
    python scripts/demo_embedding.py --model bge-m3 --endpoint http://localhost:11434

In ra: (1) với mỗi câu hỏi đời thường, 3 Điều gần nhất kèm điểm cosine; (2) tốc độ embedding trên máy bạn
để ước lượng thời gian dựng chỉ mục cho toàn bộ BLHS. Không cần numpy (tính cosine bằng Python thuần).
"""
from __future__ import annotations

import argparse
import json
import math
import shutil
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import db_path  # noqa: E402
from src.store import connect  # noqa: E402
from src.validate.vbhn import items_from_db  # noqa: E402

DIEU_THU = [173, 174, 168, 171, 123, 134, 249, 317]   # trộm cắp, lừa đảo, cướp, cướp giật, giết người, gây thương tích, ma túy, an toàn thực phẩm
CAU_HOI = [
    "mượn tiền rồi bỏ trốn không trả",
    "lén lấy xe máy của người khác",
    "dùng dao uy hiếp để lấy tài sản",
    "đánh người gây thương tích nặng",
    "bán thực phẩm bẩn làm người ăn bị ngộ độc",
    "cất giữ ma túy trong nhà",
]


def embed(endpoint: str, model: str, texts: list[str]) -> list[list[float]]:
    body = json.dumps({"model": model, "input": texts}).encode("utf-8")
    req = urllib.request.Request(endpoint.rstrip("/") + "/api/embed", data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=600) as resp:
            return json.loads(resp.read().decode("utf-8"))["embeddings"]
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        if e.code == 404:
            sys.exit(f"LỖI: Ollama chưa có model '{model}'. Chạy: ollama pull {model}\n({detail})")
        sys.exit(f"LỖI từ Ollama (HTTP {e.code}): {detail}")
    except urllib.error.URLError as e:
        sys.exit(f"LỖI: không kết nối được Ollama ở {endpoint} ({e.reason}). Mở Ollama lên rồi chạy lại.")


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default="bge-m3")
    ap.add_argument("--endpoint", default="http://localhost:11434")
    ap.add_argument("--mau", type=int, default=32, help="số đoạn lấy để đo tốc độ")
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp()) / "luat_copy.sqlite"
    shutil.copyfile(db_path(), tmp)
    conn = connect(tmp)
    vb = conn.execute("SELECT id FROM van_ban WHERE so_hieu = ?", ("100/2015/QH13",)).fetchone()["id"]
    items = items_from_db(conn, vb, date.today().isoformat())

    docs: list[tuple[str, str]] = []
    for n in DIEU_THU:
        d = items.get(f"dieu {n}")
        k1 = items.get(f"dieu {n}/khoan 1")
        if not d:
            print(f"(bỏ qua Điều {n}: không có trong CSDL)")
            continue
        tieu_de = d.tieu_de or ""
        text = f"Điều {n}. {tieu_de}\n{(k1.noi_dung if k1 else d.noi_dung) or ''}".strip()
        docs.append((f"Điều {n}. {tieu_de}", text))

    t0 = time.perf_counter()
    doc_vecs = embed(args.endpoint, args.model, [t for _, t in docs])
    t_docs = time.perf_counter() - t0
    q_vecs = embed(args.endpoint, args.model, CAU_HOI)
    print(f"Model {args.model}: vector {len(doc_vecs[0])} chiều.\n")

    for q, qv in zip(CAU_HOI, q_vecs):
        scored = sorted(((cosine(qv, dv), name) for (name, _), dv in zip(docs, doc_vecs)), reverse=True)
        print(f"Hỏi: {q}")
        for s, name in scored[:3]:
            print(f"   {s:.3f}  {name}")
        print()

    mau = [it for it in items.values() if (it.noi_dung or "").strip()][: args.mau]
    texts = [it.noi_dung for it in mau]
    t0 = time.perf_counter()
    embed(args.endpoint, args.model, texts)
    dt = time.perf_counter() - t0
    per = dt / max(len(texts), 1)
    tong = 5952
    print(f"Tốc độ: {len(texts)} đoạn trong {dt:.1f}s ({per:.2f}s/đoạn; lần gọi đầu có thể chậm hơn vì nạp model).")
    print(f"Ước lượng dựng chỉ mục cho ~{tong} đoạn: khoảng {per * tong / 60:.0f} phút (chỉ là ước lượng thô từ mẫu {len(texts)} đoạn).")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
