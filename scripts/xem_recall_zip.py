"""In bảng Recall@K và K đã chọn từ gói đo (zip) mà không cần giải nén.

Dùng: python scripts/xem_recall_zip.py lexo_do_ban_an_cbba.zip
"""
import json
import sys
import zipfile

SAN = 0.80  # sàn Recall@30 của kế hoạch V3


def main(duong_dan: str) -> int:
    with zipfile.ZipFile(duong_dan) as z:
        ten = next((n for n in z.namelist() if n.endswith("cau_hinh.json")), None)
        if ten is None:
            sys.exit("Không thấy cau_hinh.json — đây không phải gói đo.")
        ch = json.loads(z.read(ten).decode("utf-8"))
    if ch.get("gia"):
        print("CẢNH BÁO: gói này sinh bằng --gia (truy hồi giả). Số dưới đây KHÔNG dùng được.\n")
    print(f"Mô hình nhúng: {ch.get('mo_hinh_nhung')} | số mẫu: {ch.get('so_mau')}")
    for nhan, khoa in (("học + dev", "recall_hoc_dev"), ("riêng dev", "recall_dev")):
        bang = ch[khoa]
        ks = sorted(next(iter(bang.values())), key=int)
        print(f"\n{nhan}: phần mẫu có ĐỦ đáp án trong top K (ngoặc: phần Điều đáp án trong top K)")
        print("| chế độ | " + " | ".join(f"K={k}" for k in ks) + " |")
        for c, t in bang.items():
            print(f"| {c} | " + " | ".join(f"{t[k]['du']:.0%} ({t[k]['recall']:.0%})" for k in ks) + " |")
    ck = ch["chon_k"]
    print(f"\nChọn: chế độ {ck['che_do']}, K = {ck['k']} ({'đạt' if ck['dat_muc'] else 'KHÔNG đạt'} mức 90%); "
          f"đủ đáp án trong top {ck['k_toi_da']}: {ck['du_tai_k_toi_da']:.0%}")
    if ck["du_tai_k_toi_da"] < SAN:
        print(f"DƯỚI SÀN {SAN:.0%}: sửa truy hồi trước, hoãn học (theo kế hoạch V3, mục 5).")
        return 2
    print(f"Qua sàn {SAN:.0%}.")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
