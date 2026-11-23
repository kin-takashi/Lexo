"""Bản án cbba đã lọc + chia (scripts/tai_cbba_blhs.py) -> gán nhãn Điều BLHS + che đáp án, giữ nguyên chia train / test.

  python scripts/xu_ly_cbba_blhs.py --gioi-han 2000        # THỬ TRƯỚC: tối đa 2.000 văn bản mỗi tập (chọn cố định theo băm), ~0,12 giây CPU/văn bản
  python scripts/xu_ly_cbba_blhs.py --so-tien-trinh 4      # cả bộ: ~250.000 văn bản ≈ 8 giờ CPU, chia cho số tiến trình; giữ kết quả trong RAM (vài GB)
  python scripts/xu_ly_cbba_blhs.py --cap so_tham          # chỉ giữ bản án sơ thẩm; nhận so_tham, phuc_tham, giam_doc_tham, tai_tham, khong_ro (cách nhau dấu phẩy)
  python scripts/xu_ly_cbba_blhs.py --kiem-trung-train-cu  # kèm kiểm trùng đầu vào với train/tinh_huong.json (chậm: số văn bản × 450)

Mỗi văn bản đi qua đúng src/ban_an/anle_hf.xu_ly: tách bốn phần -> nhãn là Điều tòa án đã áp dụng (phần QUYẾT ĐỊNH) -> loại nếu không đủ phần /
không có Điều tội phạm / nhắc BLHS 1999 ở phần nhãn -> che tội danh, dẫn chiếu Điều luật và ngày sinh / dãy số dài trong phần sự việc.
Đầu vào chỉ giữ phần DIỄN BIẾN VỤ VIỆC: cắt tại mốc đầu tiên của phần Viện kiểm sát truy tố / đề nghị mức án («Tại bản cáo trạng số ...», «Tại phiên tòa ...»).
Bản án xét xử trước năm 2018 bị loại (`--tu-nam`): số Điều của chúng là số Điều BLHS 1999, nhãn sẽ sai so với BLHS 2015.
Văn bản mà sau đó vẫn còn dấu hiệu lộ nhãn (tên tội, Điều luật) bị LOẠI khỏi train / test với lý do `lo_nhan_con_lai` (xem loai_bo.tsv và
`bi_loai_vi_lo_nhan_theo_kieu` trong tóm tắt). Chi tiết các bước: docstring của src/ban_an/cbba_nhan.py.
Dữ liệu cá nhân KHÔNG được che hết: nơi thường trú, năm sinh, tên cha mẹ / vợ chồng vẫn còn (tóm tắt đếm số văn bản còn dấu hiệu).
Tập train / test lấy từ cột `tap` của cbba_blhs (cả nhóm vụ nằm trọn một tập); script này KHÔNG chia lại.
Đầu ra ở inbox/cbba_blhs/nhan/ (đã git-ignore):
  train.jsonl, test.jsonl   cùng cột với scripts/xu_ly_anle_hf.py
  tom_tat_nhan.json         tham số, số liệu, lý do loại, rò rỉ còn lại; mã băm tập mã vào / ra
  loai_bo.tsv               ma <TAB> lý do, cho văn bản bị loại
Chạy lại với cùng đầu vào và tham số cho cùng nội dung. Không ghi vào DB (nhập DB là việc của scripts/nhap_du_lieu.py, hiện chỉ nhận nguồn anle_hf).
Thoát 0 nếu chạy xong và không còn văn bản lộ nhãn sau khi che, 1 nếu có lỗi.
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import sys
import tempfile
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ban_an import anle_hf as hf  # noqa: E402
from src.ban_an import cbba_blhs as cb  # noqa: E402
from src.ban_an import cbba_nhan as nh  # noqa: E402
from src.config import db_path  # noqa: E402

CAP_HOP_LE = ("so_tham", "phuc_tham", "giam_doc_tham", "tai_tham", "khong_ro")


def _duong_dan(p: str) -> Path:
    return Path(p) if Path(p).is_absolute() else ROOT / p


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vao", default="inbox/cbba_blhs", help="thư mục có train.jsonl.gz, test.jsonl.gz (đầu ra của tai_cbba_blhs.py)")
    ap.add_argument("--ra", default=None, help="mặc định: <vao>/nhan")
    ap.add_argument("--gioi-han", type=int, default=None, help="tối đa bấy nhiêu văn bản MỖI TẬP (mặc định: tất cả)")
    ap.add_argument("--seed", type=int, default=2026, help="hạt chọn mẫu khi có --gioi-han")
    ap.add_argument("--cap", default=None, help="chỉ giữ cấp (theo bộ tách) trong danh sách, cách nhau dấu phẩy")
    ap.add_argument("--tu-nam", type=int, default=nh.NAM_AP_DUNG_BLHS_2015,
                    help="bỏ bản án xét xử trước năm này (mặc định 2018: trước đó số Điều là của BLHS 1999); 0 = không bỏ")
    ap.add_argument("--so-tien-trinh", type=int, default=1, help=f"số tiến trình song song (máy này có {os.cpu_count()} lõi)")
    ap.add_argument("--luat", default=None, help="db/luat.sqlite để lấy tên mọi tội của BLHS (mặc định: paths.db trong config.yaml)")
    ap.add_argument("--kiem-trung-train-cu", action="store_true")
    ap.add_argument("--train-cu", default="train/tinh_huong.json")
    a = ap.parse_args()

    vao = _duong_dan(a.vao)
    ra = _duong_dan(a.ra) if a.ra else vao / "nhan"
    f_vao = {t: vao / f"{t}.jsonl.gz" for t in nh.TEN_TAP}
    for p in f_vao.values():
        if not p.exists():
            print(f"[LỖI] không thấy {p}. Chạy scripts/tai_cbba_blhs.py trước.")
            return 1
    cap_giu = None
    if a.cap:
        cap_giu = {c.strip() for c in a.cap.split(",") if c.strip()}
        if not cap_giu <= set(CAP_HOP_LE):
            print(f"[LỖI] --cap chỉ nhận {', '.join(CAP_HOP_LE)}")
            return 1
    if a.so_tien_trinh < 1:
        print("[LỖI] --so-tien-trinh phải >= 1")
        return 1

    luat = _duong_dan(a.luat) if a.luat else db_path()
    if not luat.exists():
        print(f"[LỖI] không thấy {luat}: cần kho luật để lấy tên các tội (che tên tội không nằm trong ngoặc kép).")
        return 1
    # SQLite không mở được trực tiếp trên một số ổ đồng bộ / ổ gắn ngoài: chép ra thư mục tạm rồi đọc
    with tempfile.TemporaryDirectory() as tam:
        ban_sao = Path(tam) / "luat.sqlite"
        shutil.copyfile(luat, ban_sao)
        ten_toi = tuple(hf.ten_toi_tu_luat(ban_sao))

    chon: dict[str, set[str] | None] = {}
    dau_vao: dict[str, int] = {}
    for t, p in f_vao.items():
        cac_ma = nh.liet_ke_ma(p)
        chon[t] = nh.chon_ma(cac_ma, a.gioi_han, a.seed)
        dau_vao[t] = len(cac_ma) if chon[t] is None else len(chon[t])
        print(f"[đọc] {p.name}: {len(cac_ma)} văn bản -> xử lý {dau_vao[t]}", flush=True)

    def kho():
        stt = 0
        for t in nh.TEN_TAP:
            for d in nh.doc_tap(f_vao[t], chon[t]):
                yield stt, d
                stt += 1

    ket_qua = []
    tong = sum(dau_vao.values())
    if a.so_tien_trinh == 1:
        nh.khoi_tao(ten_toi)
        it = map(nh.xu_ly_mot, kho())
        pool = None
    else:
        pool = mp.Pool(a.so_tien_trinh, initializer=nh.khoi_tao, initargs=(ten_toi,))
        it = pool.imap(nh.xu_ly_mot, kho(), chunksize=16)
    try:
        for i, b in enumerate(it, 1):
            ket_qua.append(b)
            if i % 2000 == 0 or i == tong:
                print(f"[xử lý] {i}/{tong}", flush=True)
    finally:
        if pool:
            pool.close()
            pool.join()

    for b in ket_qua:
        nh.loai_truoc_nam(b, a.tu_nam)
    if cap_giu is not None:
        for b in ket_qua:
            if b["dung_duoc"] and b["cap"] not in cap_giu:
                b["dung_duoc"], b["ly_do"] = False, "cap_khong_giu"
    ban_ghi = sorted((b for b in ket_qua if b["dung_duoc"]), key=lambda b: b["ma"])
    loai = sorted((b for b in ket_qua if not b["dung_duoc"]), key=lambda b: b["ma"])
    tk = nh.thong_ke(ban_ghi, loai, dau_vao)

    trung = []
    if a.kiem_trung_train_cu and a.train_cu:
        van_cu = {x["id"]: x["tinh_huong"] for x in json.loads(_duong_dan(a.train_cu).read_text(encoding="utf-8"))["mau"]}
        trung = hf.trung_voi(ban_ghi, van_cu)
        tk["trung_train_cu"] = len(trung)

    ra.mkdir(parents=True, exist_ok=True)
    for t in nh.TEN_TAP:
        nh.ghi_jsonl(ra / f"{t}.jsonl", [b for b in ban_ghi if b["tap"] == t])
    (ra / "loai_bo.tsv").write_text("".join(f"{b['ma']}\t{b['ly_do']}\n" for b in loai), encoding="utf-8", newline="\n")
    tom_tat = {
        "nguon": {"thu_muc": a.vao, "sha256_ma_vao": {t: cb.sha256_ma(nh.liet_ke_ma(f_vao[t]) if chon[t] is None else chon[t]) for t in nh.TEN_TAP}},
        "tham_so": {"gioi_han_moi_tap": a.gioi_han, "seed": a.seed, "cap_giu": sorted(cap_giu) if cap_giu else "tat_ca", "tu_nam": a.tu_nam,
                    "so_ten_toi_blhs": len(ten_toi), "dieu_toi_pham": [hf.DIEU_TOI_PHAM_DAU, hf.DIEU_TOI_PHAM_CUOI]},
        "thong_ke": tk,
        "sha256_ma_ra": {t: cb.sha256_ma(b["ma"] for b in ban_ghi if b["tap"] == t) for t in nh.TEN_TAP},
    }
    (ra / "tom_tat_nhan.json").write_text(json.dumps(tom_tat, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")

    print(json.dumps({k: tk[k] for k in ("da_xu_ly", "dung_duoc", "ti_le_dung_duoc", "dung_duoc_theo_tap", "ly_do_loai", "bi_loai_vi_lo_nhan_theo_kieu",
                                         "van_ban_da_cat_phan_vks", "ti_le_giu_lai_sau_cat_trung_vi", "cap_bo_tach", "van_ban_con_lo_nhan", "van_ban_con_du_lieu_ca_nhan")}, ensure_ascii=False, indent=1))
    print(f"[OK] {len(ban_ghi)}/{len(ket_qua)} văn bản dùng được -> {ra}")
    if tk["van_ban_con_lo_nhan"]:
        print(f"[CẢNH BÁO] {tk['van_ban_con_lo_nhan']} văn bản còn lộ nhãn sau khi che (xem lo_nhan_con_lai)")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
