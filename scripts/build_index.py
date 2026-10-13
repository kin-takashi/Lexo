"""Dựng chỉ mục tìm kiếm (Bước 4): chia đoạn -> FTS5 -> vector (Ollama). CHẠY LẠI ĐƯỢC TỪ CHỖ DỪNG.

  python scripts/build_index.py --xem 8          # chỉ in thống kê và 8 đoạn mẫu, KHÔNG ghi gì, KHÔNG gọi Ollama
  python scripts/build_index.py --thu 200        # thử: tính vector cho 200 đoạn đầu chưa có
  python scripts/build_index.py                  # chạy đủ (khoảng 1 giờ trên CPU), Ctrl+C lúc nào cũng được, chạy lại sẽ làm tiếp
  python scripts/build_index.py --don-dep        # xoá vector của chữ không còn dùng

Đọc CSDL luật ở chế độ chỉ-đọc; ghi vào file chỉ mục riêng (config.yaml: paths.index). Vector được lưu theo MÃ BĂM CHỮ,
nên sau khi duyệt hiệu đính chỉ những đoạn đổi chữ phải tính lại.
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import db_path, index_path, load_config  # noqa: E402
from src.index.chunks import build_chunks  # noqa: E402
from src.index.embedder import EmbedError, HashEmbedder, tu_config  # noqa: E402
from src.index.store import don_dep, luu_vector, open_index, sync_chunks, thieu_vector, thong_ke  # noqa: E402


def mo_chi_doc(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def phut(giay: float) -> str:
    return f"{giay / 60:.0f} phút" if giay >= 90 else f"{giay:.0f} giây"


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--van-ban", default="100/2015/QH13", help="số hiệu văn bản gốc (mặc định BLHS 2015)")
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument("--index", type=Path, default=None)
    ap.add_argument("--model", default=None, help="tên model Ollama (mặc định lấy từ config.yaml, bge-m3)")
    ap.add_argument("--endpoint", default=None)
    ap.add_argument("--batch", type=int, default=None)
    ap.add_argument("--xem", type=int, metavar="N", help="chỉ in thống kê và N đoạn mẫu")
    ap.add_argument("--thu", type=int, metavar="N", help="chỉ tính vector cho N đoạn đầu chưa có")
    ap.add_argument("--don-dep", action="store_true")
    ap.add_argument("--gia", action="store_true", help="dùng vector giả (kiểm thử đường ống, không phản ánh chất lượng)")
    args = ap.parse_args()

    cfg = load_config()
    src_db = args.db or db_path()
    main_conn = mo_chi_doc(src_db)
    vb = main_conn.execute("SELECT id FROM van_ban WHERE so_hieu = ?", (args.van_ban,)).fetchone()
    if not vb:
        sys.exit(f"LỖI: không có văn bản {args.van_ban} trong {src_db}")
    chunks = build_chunks(main_conn, vb["id"])
    main_conn.close()
    loai = {}
    for c in chunks:
        loai[c.loai] = loai.get(c.loai, 0) + 1
    n_hash = len({c.hash for c in chunks})
    tb = sum(len(c.text) for c in chunks) / max(len(chunks), 1)
    print(f"{len(chunks)} đoạn ({', '.join(f'{k} {v}' for k, v in sorted(loai.items()))}); {n_hash} chữ khác nhau; "
          f"dài trung bình {tb:.0f} ký tự (đã gồm ngữ cảnh).")

    if args.xem is not None:
        mau = []
        for lo in ("dieu", "khoan", "diem"):                          # lấy đều ba loại
            mau += [c for c in chunks if c.loai == lo and c.hieu_luc_den is None][: max(args.xem // 3, 1)]
        for c in mau[: args.xem]:
            print(f"\n--- {c.key}  [{c.hieu_luc_tu} → {c.hieu_luc_den or 'nay'}]\n{c.text}")
        print("\n(chế độ --xem: chưa ghi gì, chưa gọi Ollama)")
        return 0

    emb = HashEmbedder() if args.gia else tu_config(cfg, model=args.model, endpoint=args.endpoint)
    batch = args.batch or (cfg.get("embedding") or {}).get("batch_size") or 16
    idx = open_index(args.index or index_path())
    sync_chunks(idx, chunks)
    if args.don_dep:
        print(f"Đã xoá {don_dep(idx)} vector không còn dùng.")
    thieu = thieu_vector(idx, emb.name)
    st = thong_ke(idx, emb.name)
    print(f"Chỉ mục: {st['so_doan']} đoạn, {st['so_chu_khac_nhau']} chữ khác nhau, đã có vector {st['da_co_vector']}, còn thiếu {st['chua_co_vector']} (mô hình {emb.name}).")
    if args.thu is not None:
        thieu = thieu[: args.thu]
    if not thieu:
        print("Không còn gì để tính. Xong.")
        return 0

    t0, xong = time.perf_counter(), 0
    try:
        for i in range(0, len(thieu), batch):
            nhom = thieu[i: i + batch]
            vecs = emb.embed([r["text"] for r in nhom])
            luu_vector(idx, emb.name, [r["hash"] for r in nhom], vecs)
            xong += len(nhom)
            dt = time.perf_counter() - t0
            con = (len(thieu) - xong) * dt / xong
            print(f"  [{xong}/{len(thieu)}] {xong / len(thieu):.0%}  đã {phut(dt)}, còn khoảng {phut(con)}", flush=True)
    except KeyboardInterrupt:
        print("\nĐã dừng. Phần đã tính được lưu rồi, chạy lại lệnh này để làm tiếp.")
        return 130
    except EmbedError as e:
        print(f"\nLỖI: {e}\nPhần đã tính được lưu rồi, sửa lỗi rồi chạy lại để làm tiếp.")
        return 1
    st = thong_ke(idx, emb.name)
    print(f"Xong lượt này: đã có vector {st['da_co_vector']}/{st['so_chu_khac_nhau']}, còn thiếu {st['chua_co_vector']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
