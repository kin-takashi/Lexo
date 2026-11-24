"""Nhập tập huấn luyện, bộ đo, nhật ký sửa nhãn và bộ bản án thật vào db/du_lieu.sqlite (nguồn gốc + lịch sử duyệt nhãn).

  python scripts/nhap_du_lieu.py                 # nhập mọi nguồn vào db/du_lieu.sqlite (chạy lại cùng file: không đổi gì)
                                                 # bộ bản án: inbox/anle_hf/ban_an_hinh_su.json nếu có (scripts/xu_ly_anle_hf.py)
  python scripts/nhap_du_lieu.py --khong-nhap-ban-an   # bỏ qua bộ bản án
  python scripts/nhap_du_lieu.py --reset         # nguồn đã đổi: đổi tên DB cũ thành bản sao lưu rồi nhập lại từ đầu
  python scripts/nhap_du_lieu.py --thong-ke      # chỉ in thống kê của DB hiện có
  python scripts/nhap_du_lieu.py --db X.sqlite   # chỉ định file khác

Sau khi nhập tự đối chiếu: xuất ngược từ DB phải KHỚP TỪNG MẪU với file JSON nguồn. Thoát 0 nếu ổn, 1 nếu có lỗi.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import du_lieu_path  # noqa: E402
from src.dulieu import kho, nhap  # noqa: E402
from src.index import bo_cau_hoi, tap_train  # noqa: E402
from src.store import backup_and_remove  # noqa: E402


def _in_thong_ke(conn) -> None:
    tk = nhap.thong_ke(conn)
    print("Số mẫu theo bộ / tập:")
    for (bo, tap), n in tk["mau"].items():
        print(f"  {bo:5s} {tap:9s} {n}")
    print("Tầng tin cậy (quy ước: tranh_chap > vang > bac > nhap):")
    for (bo, t), n in tk["tang"].items():
        print(f"  {bo:5s} {t:10s} {n}")
    print("Nguồn soạn: " + ", ".join(f"{bo}/{n}: {v}" for (bo, n), v in tk["nguon"].items()))
    if tk["sua_nhan"]:
        print("Sửa nhãn: " + ", ".join(f"{k} {v}" for k, v in tk["sua_nhan"].items())
              + "  |  mức chắc của người soạn bản vá: " + ", ".join(f"{k} {v}" for k, v in sorted(tk["muc_chac"].items(), key=lambda kv: str(kv[0]))))


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=None)
    ap.add_argument("--train", type=Path, default=nhap.TRAIN_MAC_DINH)
    ap.add_argument("--do", type=Path, default=nhap.DO_MAC_DINH)
    ap.add_argument("--nhat-ky", type=Path, default=nhap.NHAT_KY_MAC_DINH)
    ap.add_argument("--ban-va", type=Path, default=nhap.BAN_VA_MAC_DINH)
    ap.add_argument("--khong-nhap-sua-nhan", action="store_true", help="bỏ qua nhật ký sửa nhãn")
    ap.add_argument("--ban-an", type=Path, default=nhap.BAN_AN_MAC_DINH, help="file bộ bản án (bỏ qua nếu không có)")
    ap.add_argument("--khong-nhap-ban-an", action="store_true", help="bỏ qua bộ bản án")
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--thong-ke", action="store_true")
    args = ap.parse_args()

    path = args.db or du_lieu_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    if args.thong_ke:
        if not path.exists():
            print(f"[LỖI] chưa có {path}")
            return 1
        conn = kho.connect(path)
        _in_thong_ke(conn)
        return 0
    if args.reset:
        bak = backup_and_remove(path)
        if bak:
            print(f"[OK] DB cũ đã đổi tên thành {bak.name}")
    conn = kho.connect(path)
    try:
        kho.init_db(conn)
        ban_an = None if args.khong_nhap_ban_an or not args.ban_an.exists() else args.ban_an
        if ban_an is None and not args.khong_nhap_ban_an:
            print(f"[--] không thấy {args.ban_an}: bỏ qua bộ bản án (tạo bằng scripts/xu_ly_anle_hf.py)")
        kq = nhap.nhap_tat_ca(conn, args.train, args.do, None if args.khong_nhap_sua_nhan else args.nhat_ky,
                              None if args.khong_nhap_sua_nhan else args.ban_va, ban_an)
    except (RuntimeError, nhap.NhapError, tap_train.TapTrainError, bo_cau_hoi.BoCauHoiError) as e:
        print(f"[LỖI] {e}")
        return 1
    print(f"[OK] {path}")
    print(f"  mới nhập: {kq['train']} mẫu huấn luyện, {kq['do']} câu đo, {kq['sua_nhan']} mục sửa nhãn, {kq.get('ban_an', 0)} bản án"
          if any(kq.values())
          else "  không có gì mới (các file nguồn không đổi so với lần nhập trước)")

    loi = nhap.kiem_tra_toan_ven(conn)
    # Đối chiếu ngược: DB xuất ra phải bằng đúng file nguồn, từng mẫu một.
    if nhap.xuat_train(conn) != tap_train.doc_train(args.train):
        loi.append("xuất ngược tập huấn luyện KHÔNG khớp file nguồn")
    if nhap.xuat_do(conn) != bo_cau_hoi.doc_tho(args.do)["cau_hoi"]:
        loi.append("xuất ngược bộ đo KHÔNG khớp file nguồn")
    if ban_an is not None and nhap.xuat_ban_an(conn) != nhap.doc_ban_an_de_doi_chieu(ban_an):
        loi.append("xuất ngược bộ bản án KHÔNG khớp file nguồn")
    _in_thong_ke(conn)
    for x in loi:
        print(f"  ! {x}")
    print("TOÀN VẸN" if not loi else f"CÓ {len(loi)} LỖI")
    return 0 if not loi else 1


if __name__ == "__main__":
    sys.exit(main())
