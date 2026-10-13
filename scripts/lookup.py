"""Tra cứu chính xác một Điều tại một ngày: bản CÓ HIỆU LỰC (đã áp các luật sửa đổi đã duyệt), kèm nguồn sửa đổi.

Ví dụ:  python scripts/lookup.py "Điều 173 BLHS 2015"                 # bản hiện hành, ghi rõ khoản nào do luật nào sửa
        python scripts/lookup.py "Điều 173 BLHS" --ngay 2019-06-01    # bản có hiệu lực tại ngày đó
        python scripts/lookup.py "Điều 173 BLHS" --lich-su            # mọi lần sửa đổi của Điều
        python scripts/lookup.py "Điều 173 BLHS" --so-sanh 2017-12-31 2018-01-01
        python scripts/lookup.py "Điều 173 BLHS" --chuyen-tiep        # kèm điều khoản hiệu lực/chuyển tiếp của các luật sửa đổi
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.config import db_path  # noqa: E402
from src.query.lookup import (  # noqa: E402
    dieu_khoan_lien_quan, dieu_status, find_van_ban, fmt_date, get_dieu, hieu_dinh_cho_duyet_dieu, lich_su_dieu, luu_y_hieu_luc,
    parse_reference, render, so_hieu_dinh_cho_duyet, so_lenh_cho_duyet,
    so_sanh, tom_tat_nguon,
)
from src.store import connect  # noqa: E402


def main() -> int:
    for stream in (sys.stdout, sys.stderr):                # cửa sổ/redirect trên Windows có thể không phải UTF-8
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("tham_chieu", help='vd "Điều 173 BLHS 2015"')
    ap.add_argument("--ngay", help="ngày xem, YYYY-MM-DD (mặc định: hôm nay)")
    ap.add_argument("--lich-su", action="store_true", help="liệt kê mọi lần sửa đổi của Điều")
    ap.add_argument("--so-sanh", nargs=2, metavar=("NGAY_A", "NGAY_B"), help="so sánh Điều giữa hai ngày")
    ap.add_argument("--khong-ghi-chu", action="store_true", help="không in nguồn sửa đổi sau từng khoản/điểm")
    ap.add_argument("--nguyen-van", action="store_true", help="văn bản NHƯ LUẬT BAN HÀNH, không kèm hiệu đính kỹ thuật theo văn bản hợp nhất")
    ap.add_argument("--chuyen-tiep", action="store_true", help="in nguyên văn điều khoản hiệu lực/chuyển tiếp của các luật sửa đổi")
    ap.add_argument("--db", type=Path, default=None)
    args = ap.parse_args()
    ref = parse_reference(args.tham_chieu)
    if ref is None:
        print('Không hiểu tham chiếu. Dạng đúng: "Điều 173 BLHS 2015" (năm có thể bỏ).', file=sys.stderr)
        return 2
    ky_hieu, viet_tat, nam = ref
    path = args.db or db_path()
    if not path.exists():
        print(f"Chưa có CSDL {path}. Chạy scripts/init_db.py và nạp văn bản trước.", file=sys.stderr)
        return 2
    conn = connect(path)
    try:
        docs = find_van_ban(conn, viet_tat, nam)
        if not docs:
            print(f"Không có văn bản '{viet_tat}'" + (f" năm {nam}" if nam else "") + " trong CSDL.", file=sys.stderr)
            return 1
        if len(docs) > 1:
            print("Nhiều văn bản trùng tên viết tắt, hãy thêm năm: " + ", ".join(d["so_hieu"] for d in docs), file=sys.stderr)
            return 1
        doc = docs[0]
        ngay = args.ngay or date.today().isoformat()
        print(f"[{doc['so_hieu']} — {doc['ten_day_du']}]")
        cho = so_lenh_cho_duyet(conn, doc["id"])
        if cho:
            print(f"Lưu ý: còn {cho} lệnh sửa đổi đã nạp nhưng CHƯA được duyệt nên chưa áp vào kết quả dưới đây "
                  f"(xem scripts/apply_commands.py tong-quan {doc['so_hieu']}).")
        cho_hd_all = so_hieu_dinh_cho_duyet(conn, doc["id"])
        if cho_hd_all:
            print(f"Lưu ý: còn {cho_hd_all} đề xuất hiệu đính kỹ thuật chưa được duyệt (scripts/doi_chieu_vbhn.py danh-sach).")
        luu_y = luu_y_hieu_luc(conn, doc["id"]) if (args.ngay or args.lich_su or args.so_sanh) else None
        if luu_y:
            print(luu_y)
        if args.so_sanh:
            diff = so_sanh(conn, doc["id"], ky_hieu, *args.so_sanh)
            print(diff or f"Điều {ky_hieu} giống nhau ở hai thời điểm {args.so_sanh[0]} và {args.so_sanh[1]}.")
            return 0
        if args.lich_su:
            print(f"Lịch sử Điều {ky_hieu}:")
            print(f"  {fmt_date(doc['ngay_hieu_luc_theo_van_ban'])}  Ban hành trong {doc['ten_day_du']} (hiệu lực theo văn bản)"
                  if doc["ngay_hieu_luc"] == doc["ngay_hieu_luc_theo_van_ban"] else
                  f"  {fmt_date(doc['ngay_hieu_luc'])}  Bắt đầu hiệu lực (ngày ghi trong văn bản là {fmt_date(doc['ngay_hieu_luc_theo_van_ban'])}, đã được dời)")
            for e in lich_su_dieu(conn, doc["id"], ky_hieu):
                print(f"  {fmt_date(e.ngay)}  {e.mo_ta()}")
            return 0
        unit = get_dieu(conn, doc["id"], ky_hieu, ngay, nguyen_van=args.nguyen_van)
        if unit is None:
            print(dieu_status(conn, doc["id"], ky_hieu, ngay))
            return 1
        print(f"(bản có hiệu lực tại ngày {fmt_date(ngay)}" + (", NGUYÊN VĂN như luật ban hành" if args.nguyen_van else "") + ")")
        print(render(unit, ghi_chu=not args.khong_ghi_chu))
        n_hd = sum(len(u.hieu_dinh) for u in unit.walk())
        if n_hd:
            print(f"\nĐiều này có {n_hd} chỗ đã hiệu đính kỹ thuật theo văn bản hợp nhất (xem nguyên văn bằng --nguyen-van).")
        cho_hd = hieu_dinh_cho_duyet_dieu(conn, doc["id"], ky_hieu)
        if cho_hd:
            print(f"\nLưu ý: có {len(cho_hd)} đề xuất hiệu đính CHƯA duyệt cho Điều này (chưa áp vào văn bản trên): " + "; ".join(
                f"{r['khoa']}: “{r['tu_cu']}” → “{r['thanh_moi']}”" for r in cho_hd))
        sap = [e for e in lich_su_dieu(conn, doc["id"], ky_hieu) if e.ngay > ngay]
        for e in sap:
            print(f"\nLưu ý: sẽ có sửa đổi hiệu lực từ {fmt_date(e.ngay)} (chưa áp dụng tại ngày {fmt_date(ngay)}): {e.mo_ta(4)}")
        srcs = tom_tat_nguon(unit)
        if srcs:
            print("\nĐiều này đã được sửa đổi, bổ sung bởi: " + "; ".join(sorted({f'{n.ten_ngan} (hiệu lực {fmt_date(n.hieu_luc_tu)})' for n in srcs})))
        if args.chuyen_tiep:
            print("\nĐiều khoản hiệu lực / chuyển tiếp của các luật sửa đổi (nguyên văn; hệ thống KHÔNG tự suy ra hồi tố):")
            for r in dieu_khoan_lien_quan(conn, doc["id"]):
                print(f"\n— {r['so_hieu']} {r['vi_tri']} ({'hiệu lực' if r['loai'] == 'hieu_luc' else 'chuyển tiếp'}):\n{r['noi_dung']}")
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
