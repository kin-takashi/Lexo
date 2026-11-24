"""Dataset Hugging Face tmquan/cbba-toaan-gov-vn -> bản án hình sự có trích dẫn Bộ luật Hình sự, chia train / test (mặc định 70 / 30).

  python scripts/tai_cbba_blhs.py                       # tải file còn thiếu vào raw/cbba/ -> lọc -> chia -> inbox/cbba_blhs/
  python scripts/tai_cbba_blhs.py --so-shard 2          # chạy thử với 2 file đầu (nhanh, ~35 nghìn văn bản)
  python scripts/tai_cbba_blhs.py --thu-muc-raw D:\\cbba  # dùng file đã tải sẵn ở thư mục khác
  python scripts/tai_cbba_blhs.py --chi-tai             # chỉ tải
  python scripts/tai_cbba_blhs.py --ti-le-test 0.3 --seed 2026
  python scripts/tai_cbba_blhs.py --cap so_tham         # chỉ giữ bản án sơ thẩm (so_tham, phuc_tham, giam_doc_tham, tai_tham; cách nhau bằng dấu phẩy)
  python scripts/tai_cbba_blhs.py --chi-co-dieu-toi-pham   # chỉ giữ văn bản nêu ít nhất một Điều 108-425 (phần các tội phạm)
  python scripts/tai_cbba_blhs.py --loc-lai             # bỏ file lọc trung gian, lọc lại từ đầu

Cần: pip install pyarrow   (không cần huggingface_hub: tải bằng thư viện chuẩn). Dung lượng: raw/cbba ~4,6 GB, inbox/cbba_blhs vài trăm MB đến ~1 GB.
Đầu ra ở inbox/cbba_blhs/ (đã git-ignore: văn bản công bố vẫn còn thông tin cá nhân, KHÔNG gửi lên dịch vụ ngoài khi chưa che):
  train.jsonl.gz, test.jsonl.gz   mỗi dòng một bản án + siêu dữ liệu + toàn văn (cột xem COT_JSONL trong src/ban_an/cbba_blhs.py)
  tom_tat.json                    nguồn (mã commit dataset, sha256 từng file), tham số, số liệu từng bước, kiểm tra rò rỉ, thống kê hai tập
  loai_bo.tsv                     ma <TAB> lý do, cho mọi văn bản hình sự có BLHS nhưng bị loại
  _loc/                           file lọc trung gian (dựng lại được; xóa đi cũng không sao)
Chạy lại với cùng file nguồn và tham số cho ra cùng nội dung (không ghi giờ chạy; gzip không ghi giờ, nhưng file nén có thể lệch byte nếu bản zlib khác).
So hai lần chạy / hai máy bằng ket_qua_sha256_ma trong tom_tat.json (băm tập mã của từng tập, không phụ thuộc cách nén). Không ghi vào DB; không sửa file nguồn.
Thoát 0 nếu chạy xong và mọi kiểm tra đều qua (không rò rỉ cấp trên <-> sơ thẩm đã nối được giữa hai tập, không trùng mã / nguyên văn giữa hai tập), 1 nếu có lỗi.
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

from src.ban_an import cbba_blhs as cb  # noqa: E402

CAP_HOP_LE = ("so_tham", "phuc_tham", "giam_doc_tham", "tai_tham")


def _duong_dan(p: str) -> Path:
    return Path(p) if Path(p).is_absolute() else ROOT / p


def _file_loc(thu_muc_loc: Path, i: int) -> Path:
    return thu_muc_loc / f"loc_{cb.PHIEN_BAN_LOC}_{i:02d}.parquet"


def _loc_con_dung_duoc(f_loc: Path, nguon: Path) -> bool:
    meta = f_loc.with_suffix(".json")
    if not (f_loc.exists() and meta.exists()):
        return False
    try:
        m = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    return m.get("nguon") == nguon.name and m.get("kich_thuoc_nguon") == nguon.stat().st_size and m.get("phien_ban") == cb.PHIEN_BAN_LOC


def doc_nhe(file_loc: list[Path]) -> list[dict]:
    """Mọi cột trừ toàn văn (toàn văn đọc lại lúc ghi, để không giữ vài GB trong bộ nhớ)."""
    import pyarrow.parquet as pq  # noqa: PLC0415
    ra: list[dict] = []
    for f in file_loc:
        cot = [c for c in pq.ParquetFile(str(f)).schema_arrow.names if c != "van_ban"]
        ra.extend(pq.read_table(str(f), columns=cot).to_pylist())
    return ra


def kiem_tra_dau_ra(ra: Path, kq_ghi: dict[str, int], tap: dict[str, str]) -> list[str]:
    """Đọc lại hai file đã ghi: số dòng, mã không trùng giữa hai tập, mỗi dòng đúng tập."""
    loi: list[str] = []
    da_thay: dict[str, str] = {}
    for t in ("train", "test"):
        n = 0
        for d in cb.doc_jsonl_gz(ra / f"{t}.jsonl.gz"):
            n += 1
            if d["tap"] != t or tap.get(d["ma"]) != t:
                loi.append(f"{d['ma']}: nằm trong {t}.jsonl.gz nhưng được chia vào {tap.get(d['ma'])}")
            if d["ma"] in da_thay:
                loi.append(f"{d['ma']}: xuất hiện hai lần ({da_thay[d['ma']]}, {t})")
            da_thay[d["ma"]] = t
        if n != kq_ghi[t]:
            loi.append(f"{t}.jsonl.gz: đọc lại {n} dòng, lúc ghi {kq_ghi[t]} dòng")
    if len(da_thay) != len(tap):
        loi.append(f"đọc lại {len(da_thay)} mã, đã chia {len(tap)} mã")
    return loi


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--thu-muc-raw", default="raw/cbba", help="nơi chứa documents-*.parquet (mặc định raw/cbba)")
    ap.add_argument("--ra", default="inbox/cbba_blhs")
    ap.add_argument("--so-shard", type=int, default=cb.SO_SHARD, help=f"số file đầu tiên dùng (mặc định {cb.SO_SHARD} = cả dataset)")
    ap.add_argument("--ti-le-test", type=float, default=0.3)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--cap", default=None, help="chỉ giữ các cấp xét xử này, vd so_tham,phuc_tham (mặc định: tất cả)")
    ap.add_argument("--chi-co-dieu-toi-pham", action="store_true")
    ap.add_argument("--so-ky-tu-toi-thieu", type=int, default=cb.SO_KY_TU_TOI_THIEU)
    ap.add_argument("--chi-tai", action="store_true")
    ap.add_argument("--khong-tai", action="store_true", help="không tải; thiếu file thì báo lỗi")
    ap.add_argument("--loc-lai", action="store_true")
    a = ap.parse_args()

    if not 0 < a.ti_le_test < 1:
        print("[LỖI] --ti-le-test phải nằm trong (0, 1)")
        return 1
    if not 1 <= a.so_shard <= cb.SO_SHARD:
        print(f"[LỖI] --so-shard phải từ 1 đến {cb.SO_SHARD}")
        return 1
    cap_giu = None
    if a.cap:
        cap_giu = {c.strip() for c in a.cap.split(",") if c.strip()}
        if not cap_giu <= set(CAP_HOP_LE):
            print(f"[LỖI] --cap chỉ nhận {', '.join(CAP_HOP_LE)}")
            return 1
    try:
        import pyarrow  # noqa: F401, PLC0415
    except ImportError:
        print("[LỖI] thiếu pyarrow: pip install pyarrow")
        return 1

    raw = _duong_dan(a.thu_muc_raw)
    nguon: list[Path] = []
    for i in range(a.so_shard):
        f = raw / cb.ten_shard(i)
        if a.khong_tai:
            if not (f.exists() and cb.shard_doc_duoc(f)):
                print(f"[LỖI] thiếu hoặc hỏng {f}")
                return 1
        else:
            print(f"[tải] {cb.ten_shard(i)} ({i + 1}/{a.so_shard})", flush=True)
            f = cb.tai_shard(i, raw)
        nguon.append(f)
    if a.chi_tai:
        print(f"[OK] đã có đủ {len(nguon)} file ở {raw}")
        return 0

    ra = _duong_dan(a.ra)
    thu_muc_loc = ra / "_loc"
    thu_muc_loc.mkdir(parents=True, exist_ok=True)
    file_loc, tk_loc = [], Counter()
    for i, f in enumerate(nguon):
        fl = _file_loc(thu_muc_loc, i)
        meta = fl.with_suffix(".json")
        if a.loc_lai or not _loc_con_dung_duoc(fl, f):
            print(f"[lọc] {f.name} ({i + 1}/{len(nguon)})", flush=True)
            tk = cb.loc_shard(f, fl)
            meta.write_text(json.dumps({"nguon": f.name, "kich_thuoc_nguon": f.stat().st_size, "phien_ban": cb.PHIEN_BAN_LOC, **tk}), encoding="utf-8")
        else:
            print(f"[lọc] {f.name}: dùng lại {fl.name}", flush=True)
        tk_loc.update({k: v for k, v in json.loads(meta.read_text(encoding="utf-8")).items() if k in ("tong", "hinh_su", "co_blhs")})
        file_loc.append(fl)

    ban_ghi = doc_nhe(file_loc)
    giu, bo = cb.loai_bo(ban_ghi, a.so_ky_tu_toi_thieu, cap_giu, a.chi_co_dieu_toi_pham)
    nhom, tk_gom = cb.gom_vu(giu)
    tap = cb.chia_tap(nhom, a.ti_le_test, a.seed)
    ro_ri = cb.kiem_ro_ri(giu, tap)
    tk_tap = cb.thong_ke_tap(giu, tap, nhom)
    kq_ghi = cb.ghi_tap(file_loc, {b["ma"] for b in giu}, tap, nhom, ra)
    loi = kiem_tra_dau_ra(ra, kq_ghi, tap)
    if ro_ri["cap_tren_so_tham_khac_tap"]:
        loi.append(f"{ro_ri['cap_tren_so_tham_khac_tap']} cặp bản án cấp trên - sơ thẩm nằm ở hai tập khác nhau")
    if ro_ri["md5_o_ca_hai_tap"] or ro_ri["ma_o_ca_hai_tap"]:
        loi.append(f"trùng giữa hai tập: {ro_ri['md5_o_ca_hai_tap']} nguyên văn, {ro_ri['ma_o_ca_hai_tap']} mã")

    (ra / "loai_bo.tsv").write_text("".join(f"{m}\t{ly}\n" for m, ly in bo), encoding="utf-8", newline="\n")
    tom_tat = {
        "nguon": {"dataset": cb.DATASET, **cb.phien_ban_dataset(),
                  "file": [{"ten": f.name, "kich_thuoc": f.stat().st_size, "sha256": cb.sha256_file(f)} for f in nguon]},
        "tham_so": {"ti_le_test": a.ti_le_test, "seed": a.seed, "cap_giu": sorted(cap_giu) if cap_giu else "tat_ca",
                    "chi_co_dieu_toi_pham": a.chi_co_dieu_toi_pham, "so_ky_tu_toi_thieu": a.so_ky_tu_toi_thieu, "so_shard": a.so_shard,
                    "phien_ban_loc": cb.PHIEN_BAN_LOC, "dieu_toi_pham": [cb.DIEU_TOI_PHAM_DAU, cb.DIEU_TOI_PHAM_CUOI],
                    "thu_nghiem": a.so_shard < cb.SO_SHARD},
        "thong_ke_loc": {"so_hang_dataset": tk_loc["tong"], "so_hinh_su": tk_loc["hinh_su"], "so_hinh_su_co_blhs": tk_loc["co_blhs"],
                         "ly_do_loai": dict(Counter(ly for _, ly in bo).most_common()), "giu_lai": len(giu),
                         "cap_truoc_khi_loai": dict(Counter(b["cap"] for b in ban_ghi).most_common()),
                         "mau_thuan_cap_xet_xu": sum(b["mau_thuan_cap"] for b in giu)},
        "gom_vu": {"so_nhom": len(set(nhom.values())), **tk_gom},
        "kiem_ro_ri": ro_ri,
        "ket_qua": kq_ghi,
        "ket_qua_sha256_ma": {t: cb.sha256_ma(m for m, x in tap.items() if x == t) for t in ("train", "test")},
        "thong_ke_tap": tk_tap,
        "luu_y": list(cb.LUU_Y),
        "loi": loi,
    }
    (ra / "tom_tat.json").write_text(json.dumps(tom_tat, ensure_ascii=False, indent=1), encoding="utf-8", newline="\n")

    print(json.dumps({k: tom_tat[k] for k in ("thong_ke_loc", "gom_vu", "kiem_ro_ri", "ket_qua")}, ensure_ascii=False, indent=1))
    print(f"[OK] train {kq_ghi['train']} + test {kq_ghi['test']} văn bản (test thực tế {tk_tap['ti_le_test_thuc_te']:.1%}) -> {ra}")
    for x in loi:
        print(f"[LỖI] {x}")
    return 1 if loi else 0


if __name__ == "__main__":
    raise SystemExit(main())
