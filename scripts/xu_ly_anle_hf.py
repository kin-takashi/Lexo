"""Dataset Hugging Face tmquan/anle-toaan-gov-vn -> bản án hình sự có nhãn dùng được, đã che đáp án, chia train / test.

  python scripts/xu_ly_anle_hf.py                                   # tự tìm raw/anle/**/documents-*.parquet
  python scripts/xu_ly_anle_hf.py --parquet FILE.parquet --ti-le-test 0.5 --seed 2026
  python scripts/xu_ly_anle_hf.py --bo-ket-hop                      # bỏ nhóm nguồn nhãn «ket_hop» (nhiều bị cáo, nhãn ghép hai nguồn)

Tải dataset về raw/anle/ (cần: pip install huggingface_hub):
  python -c "from huggingface_hub import snapshot_download; snapshot_download('tmquan/anle-toaan-gov-vn', repo_type='dataset', allow_patterns='*.parquet', local_dir='raw/anle')"
Đầu ra ở inbox/anle_hf/ (đã git-ignore: văn bản công bố vẫn còn thông tin cá nhân sót):
  ban_an_hinh_su.json   mọi văn bản dùng được + tham số + thống kê + sha256 file nguồn
  train.jsonl, test.jsonl
  loai_bo.json          văn bản hình sự bị loại và lý do
Không sửa file nguồn, không ghi vào DB: nhập DB bằng scripts/nhap_du_lieu.py (bo = 'ban_an').
Chạy lại với cùng file parquet và tham số cho ra đúng file cũ (không ghi giờ chạy), nên nhập lại không báo «nguồn đã đổi». Thoát 0 nếu chạy xong và không còn lộ nhãn, 1 nếu có lỗi.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ban_an import anle_hf as hf  # noqa: E402
from src.config import db_path  # noqa: E402

COT_JSONL = ("ma", "tap", "nhom_vu", "dau_vao", "dieu", "toi_danh", "nguon_nhan", "cap", "so_ban_an", "ngay")


def _duong_dan(p: str) -> Path:
    return Path(p) if Path(p).is_absolute() else ROOT / p


def xu_ly_tat_ca(rows: list[dict], ti_le_test: float, seed: int, bo_ket_hop: bool, van_cu: dict[str, str],
                 ten_toi_blhs: list[str] | tuple[str, ...] = ()) -> dict:
    hinh_su = [(i, r) for i, r in enumerate(rows) if hf.la_hinh_su(r)]
    ban_ghi, loai, da_thay = [], [], set()
    for i, r in hinh_su:
        b = hf.xu_ly(r, i, ten_toi_blhs)
        if b["hash_toan_van"] in da_thay:
            b["dung_duoc"], b["ly_do"] = False, "trung_nguyen_van"
        da_thay.add(b["hash_toan_van"])
        if b["dung_duoc"] and bo_ket_hop and b["nguon_nhan"] == "ket_hop":
            b["dung_duoc"], b["ly_do"] = False, "bo_ket_hop"
        (ban_ghi if b["dung_duoc"] else loai).append(b)
    nhom = hf.gom_vu(ban_ghi)
    tap = hf.chia_tap(ban_ghi, nhom, ti_le_test, seed)
    for b in ban_ghi:
        b["nhom_vu"], b["tap"] = nhom[b["ma"]], tap[b["ma"]]
    trung = hf.trung_voi(ban_ghi, van_cu) if van_cu else []
    return {"so_hang": len(rows), "so_hinh_su": len(hinh_su), "ban_ghi": ban_ghi, "loai": loai, "trung_train_cu": trung}


def thong_ke(kq: dict) -> dict:
    bg = kq["ban_ghi"]
    dieu_tap = {t: Counter(d for b in bg if b["tap"] == t for d in b["dieu"]) for t in ("train", "test")}
    tat_ca = Counter(d for b in bg for d in b["dieu"])
    return {
        "so_hang_dataset": kq["so_hang"],
        "so_hinh_su": kq["so_hinh_su"],
        "dung_duoc": len(bg),
        "ly_do_loai": dict(Counter(b["ly_do"] for b in kq["loai"]).most_common()),
        "nguon_nhan": dict(Counter(b["nguon_nhan"] for b in bg).most_common()),
        "cap_bo_tach": dict(Counter(b["cap"] for b in bg).most_common()),
        "cap_dataset_khac_bo_tach": {f"{c}->{b}": n for (c, b), n in Counter(
            (x["cap_dataset"], x["cap"]) for x in bg + kq["loai"] if x["cap_dataset_khop"] is False and x["cap"] != "khong_ro").most_common()},
        "so_toi_moi_van_ban": dict(sorted(Counter(min(len(b["dieu"]), 3) for b in bg).items())),
        "so_dieu_khac_nhau": len(tat_ca),
        "dieu_pho_bien": dict(tat_ca.most_common(10)),
        "dieu_chi_1_van_ban": sorted(d for d, n in tat_ca.items() if n == 1),
        "tap": dict(Counter(b["tap"] for b in bg)),
        "so_nhom_vu": {t: len({b["nhom_vu"] for b in bg if b["tap"] == t}) for t in ("train", "test")},
        "dieu_chi_o_test": sorted(set(dieu_tap["test"]) - set(dieu_tap["train"])),
        "dieu_chi_o_train": sorted(set(dieu_tap["train"]) - set(dieu_tap["test"])),
        "van_ban_con_lo_nhan": sum(1 for b in bg if b["lo_nhan_con_lai"]),
        "van_ban_co_ro_ri_truoc_che": sum(1 for b in bg if b["ro_ri_truoc_che"]),
        "van_ban_con_truy_to_tran": sum(1 for b in bg if b["ro_ri_sau_che"].get("truy_to")),
        "van_ban_nhac_ten_toi_trong_loi_ke": sum(1 for b in bg if b["ten_toi_trong_loi_ke"]),
        "da_che": dict(sum((Counter(b["da_che"]) for b in bg), Counter())),
        "trung_train_cu": len(kq["trung_train_cu"]),
    }


def _ghi_jsonl(path: Path, ds: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for b in ds:
            f.write(json.dumps({k: b[k] for k in COT_JSONL}, ensure_ascii=False) + "\n")


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--parquet", default=None, help="mặc định: file documents-*.parquet đầu tiên trong raw/anle/ (tìm cả thư mục con)")
    ap.add_argument("--ra", default="inbox/anle_hf")
    ap.add_argument("--ti-le-test", type=float, default=0.5)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--bo-ket-hop", action="store_true")
    ap.add_argument("--train-cu", default="train/tinh_huong.json", help="tập huấn luyện cũ để kiểm trùng ('' để bỏ qua)")
    ap.add_argument("--luat", default=None, help="db/luat.sqlite để lấy tên mọi tội của BLHS (mặc định: paths.db trong config.yaml)")
    a = ap.parse_args()

    pq = _duong_dan(a.parquet) if a.parquet else hf.tim_parquet(ROOT / "raw" / "anle")
    if pq is None or not pq.exists():
        print(f"[LỖI] không thấy file parquet ({pq or 'raw/anle/**/documents-*.parquet'}). Tải dataset trước, xem hướng dẫn ở đầu file này.")
        return 1
    van_cu: dict[str, str] = {}
    if a.train_cu:
        d = json.loads(_duong_dan(a.train_cu).read_text(encoding="utf-8"))
        van_cu = {x["id"]: x["tinh_huong"] for x in d["mau"]}

    luat = _duong_dan(a.luat) if a.luat else db_path()
    if not luat.exists():
        print(f"[LỖI] không thấy {luat}: cần kho luật để lấy tên các tội (che tên tội không nằm trong ngoặc kép).")
        return 1
    ten_toi = hf.ten_toi_tu_luat(luat)
    rows = hf.doc_parquet(pq)
    kq = xu_ly_tat_ca(rows, a.ti_le_test, a.seed, a.bo_ket_hop, van_cu, ten_toi)
    tk = thong_ke(kq)
    ra = _duong_dan(a.ra)
    ra.mkdir(parents=True, exist_ok=True)
    bg = sorted(kq["ban_ghi"], key=lambda b: b["ma"])
    goc = {"dataset": hf.DATASET, "file": pq.name, "sha256": hf.sha256_file(pq)}   # không ghi giờ chạy: cùng đầu vào -> cùng file
    tham_so = {"ti_le_test": a.ti_le_test, "seed": a.seed, "bo_ket_hop": a.bo_ket_hop, "so_ten_toi_blhs": len(ten_toi),
               "dieu_toi_pham": [hf.DIEU_TOI_PHAM_DAU, hf.DIEU_TOI_PHAM_CUOI]}
    (ra / "ban_an_hinh_su.json").write_text(json.dumps(
        {"nguon": goc, "tham_so": tham_so, "thong_ke": tk, "trung_train_cu": kq["trung_train_cu"], "mau": bg},
        ensure_ascii=False, indent=1), encoding="utf-8")
    for t in ("train", "test"):
        _ghi_jsonl(ra / f"{t}.jsonl", [b for b in bg if b["tap"] == t])
    (ra / "loai_bo.json").write_text(json.dumps(
        [{k: b[k] for k in ("ma", "so_ban_an", "cap", "cap_dataset", "nguon_nhan", "ly_do", "canh_bao")} for b in kq["loai"]],
        ensure_ascii=False, indent=1), encoding="utf-8")

    print(json.dumps(tk, ensure_ascii=False, indent=1))
    print(f"[OK] {len(bg)} văn bản -> {ra}")
    if tk["van_ban_con_lo_nhan"]:
        print(f"[CẢNH BÁO] {tk['van_ban_con_lo_nhan']} văn bản còn lộ nhãn sau khi che (xem lo_nhan_con_lai trong ban_an_hinh_su.json)")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
