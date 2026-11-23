"""Tách bản án / quyết định hình sự thành bốn phần (đầu / nội dung vụ án / nhận định / quyết định) + nhãn thô, in bảng kiểm tra.

  python scripts/tach_ban_an.py                         # mặc định: inbox/ho_so_vu_an_txt/*.txt -> inbox/ho_so_vu_an_json/*.json
  python scripts/tach_ban_an.py --vao inbox/ho_so_vu_an # đọc thẳng PDF (cần pdfplumber; bản quét ảnh sẽ báo "cần OCR")
  python scripts/tach_ban_an.py --vao FILE.txt --xem    # in chi tiết một file

Không sửa file gốc. Đầu ra nằm trong inbox/ (đã git-ignore: văn bản công bố vẫn còn thông tin cá nhân sót).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.ban_an.tach import doc_file, tach  # noqa: E402

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:  # noqa: BLE001
        pass


def _danh_sach(vao: Path) -> list[Path]:
    if vao.is_file():
        return [vao]
    ds = sorted(vao.glob("*.txt")) or sorted(vao.glob("*.pdf"))
    return ds


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vao", default="inbox/ho_so_vu_an_txt", help="thư mục chứa .txt/.pdf, hoặc một file")
    ap.add_argument("--ra", default="inbox/ho_so_vu_an_json", help="thư mục ghi JSON (bỏ qua nếu --xem)")
    ap.add_argument("--xem", action="store_true", help="in chi tiết thay vì ghi file")
    a = ap.parse_args()

    vao = (ROOT / a.vao) if not Path(a.vao).is_absolute() else Path(a.vao)
    files = _danh_sach(vao)
    if not files:
        print(f"Không thấy .txt/.pdf trong {vao}", file=sys.stderr)
        return 1
    ra = (ROOT / a.ra) if not Path(a.ra).is_absolute() else Path(a.ra)
    if not a.xem:
        ra.mkdir(parents=True, exist_ok=True)

    dong_bang = []
    for f in files:
        van, canh_doc = doc_file(f)
        kq = tach(van)
        kq["canh_bao"] = canh_doc + kq["canh_bao"]
        kq["tep"] = f.name
        if a.xem:
            print(json.dumps({k: v for k, v in kq.items() if k != "phan"}, ensure_ascii=False, indent=2))
            for ten, nd in kq["phan"].items():
                print(f"\n--- {ten} ({len(nd)} ký tự) ---\n{nd[:600]}{' ...' if len(nd) > 600 else ''}")
        else:
            (ra / (f.stem + ".json")).write_text(json.dumps(kq, ensure_ascii=False, indent=2), encoding="utf-8")
        p = kq["phan"]
        m = kq["meta"]
        dong_bang.append((
            f.stem, kq["kieu"][:12], m["cap"][:9], f"{m['so'] or '?'}/{m['nam'] or '?'}", m["ngay"] or "?",
            len(p["dau"]), len(p["noi_dung"]), len(p["nhan_dinh"]), len(p["quyet_dinh"]),
            "ĐỦ" if kq["dat"] else "THIẾU", len(kq["nhan_quyet_dinh"]["toi_danh"]),
            len({(x["dieu"], x["chu"], x["khoan"], x["diem"]) for d in kq["nhan_quyet_dinh"]["dan_chieu"] + kq["nhan_so_tham_trich"]["dan_chieu"] if d["bo_luat"] == "hinh_su" for x in d["dieu"]}),
            sum(kq["ro_ri_trong_su_viec"].values()), len(kq["canh_bao"]), kq["nguon_nhan_de_xuat"],
            "; ".join(kq["nhan_so_tham_trich"]["toi_danh"] or kq["nhan_quyet_dinh"]["toi_danh"])[:40],
        ))

    tieu_de = ("tệp", "kiểu", "cấp", "số", "ngày", "đầu", "nd", "nđ", "qđ", "4 phần", "tội", "Điều", "rò rỉ", "c.báo", "nguồn nhãn", "tội danh (trích)")
    rong = [max(len(str(x)) for x in col) for col in zip(tieu_de, *dong_bang)]
    for hang in (tieu_de, *dong_bang):
        print("  ".join(str(x).ljust(w) for x, w in zip(hang, rong)))
    dat = sum(1 for h in dong_bang if h[9] == "ĐỦ")
    print(f"\nĐủ bốn phần: {dat}/{len(dong_bang)}" + ("" if a.xem else f"  -> JSON ở {ra}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
