"""Chẩn đoán câu hỏi sinh sẵn: chúng có đáng dùng không? Chạy offline trên chỉ mục, không gọi LLM.

  python scripts/chan_doan_cau_hoi.py                     # thống kê câu sinh + so phiếu trên bộ dev (cần Ollama chỉ để nhúng ~70 câu dev)
  python scripts/chan_doan_cau_hoi.py --chi-thong-ke      # chỉ thống kê bản thân câu sinh, KHÔNG cần Ollama
  python scripts/chan_doan_cau_hoi.py --tap kiem_tra       # xác nhận cuối trên tập kiểm tra (đừng chỉnh tham số theo nó)

Số đo:
  - vòng khứ hồi: tìm bằng chính câu sinh, Điều nguồn đứng hạng 1 / trong top 3 (câu lạc đề, câu chép ví dụ sẽ rớt);
  - trùng: câu trùng hoặc gần trùng (cosine >= 0,95) câu của Điều khác;
  - so phiếu: trên bộ có đáp án, khi "chữ luật" và "câu sinh" chọn khác Điều hạng 1 thì bên nào đúng hơn.
Kết luận ĐẠT chỉ khi cả ba qua ngưỡng VÀ câu sinh đã phủ >= 90% Điều về tội phạm (ngưỡng ở src/index/chan_doan.py, có giải thích);\nĐẠT SƠ BỘ = qua ngưỡng nhưng mới phủ một phần: sinh nốt rồi chạy lại. CHƯA ĐẠT: đừng quét hệ số, sinh lại câu (đổi model/lời nhắc).\nSo phiếu làm trong THẾ GIỚI ĐÓNG (cả chữ luật lẫn câu sinh chỉ chọn trong các Điều đã có câu sinh), nếu không bên câu sinh được ưu ái.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import index_path, load_config  # noqa: E402
from src.index.cau_hoi import PHIEN_BAN_LENH, gom_dieu, loc_dieu_toi_pham  # noqa: E402
from src.index.bo_cau_hoi import MAC_DINH, TAP, TAP_DONG_BANG, BoCauHoiError, doc_bo  # noqa: E402
from src.index.chan_doan import (MIN_PHIEU, NGUONG_CUU_PHA, NGUONG_PHU, NGUONG_TOP3, NGUONG_TRUNG, ket_luan, so_phieu,  # noqa: E402
                                 thong_ke_cau_hoi, ti_le_cuu_pha)
from src.index.embedder import EmbedError, HashEmbedder, tu_config  # noqa: E402
from src.index.store import open_index  # noqa: E402


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index", type=Path, default=None)
    ap.add_argument("--bo-cau-hoi", type=Path, default=MAC_DINH)
    ap.add_argument("--tap", choices=TAP, default="dev", help="tập câu hỏi dùng để so phiếu (mặc định dev)")
    ap.add_argument("--ngay", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--endpoint", default=None)
    ap.add_argument("--gia", action="store_true")
    ap.add_argument("--chi-thong-ke", action="store_true", help="bỏ phần so phiếu (không cần Ollama)")
    args = ap.parse_args()

    ip = args.index or index_path()
    if not ip.exists():
        sys.exit(f"LỖI: chưa có {ip}. Chạy trước: python scripts/build_index.py")
    idx = open_index(ip)
    emb = HashEmbedder() if args.gia else tu_config(load_config(), model=args.model, endpoint=args.endpoint)

    tk = thong_ke_cau_hoi(idx, emb.name)
    if not tk["tong"]:
        sys.exit("Chưa có câu hỏi sinh sẵn nào. Chạy: python scripts/sinh_cau_hoi.py")
    mh = [r[0] for r in idx.execute("SELECT DISTINCT mo_hinh FROM cau_hoi_sinh")]
    ban = idx.execute("SELECT v FROM meta WHERE k = 'cau_hoi_lenh'").fetchone()
    co_chu = len(loc_dieu_toi_pham(gom_dieu(idx)))
    print(f"Câu hỏi sinh sẵn: {tk['tong']} câu ({tk['co_vec']} có vector {emb.name}), {tk['so_dieu']} Điều (có {co_chu} Điều về tội phạm); model viết: {', '.join(mh)}")
    if ban is None or ban["v"] != PHIEN_BAN_LENH:
        print(f"!! Viết bằng lời nhắc CŨ hoặc không rõ phiên bản (hiện hành {PHIEN_BAN_LENH}): tìm kiếm sẽ KHÔNG dùng chúng. "
              f"Chạy lại python scripts/sinh_cau_hoi.py (sẽ tự xoá câu cũ).")
    if not tk["co_vec"]:
        sys.exit("Chưa nhúng câu nào: chạy python scripts/sinh_cau_hoi.py --thu 0")
    print(f"- Vòng khứ hồi: Điều nguồn hạng 1: {tk['ti_hang1']:.0%}, trong top 3: {tk['ti_top3']:.0%}   (cần top 3 ≥ {NGUONG_TOP3:.0%}; hạng 1 chỉ để tham khảo)")
    print(f"- Trùng/gần trùng câu của Điều khác: {tk['trung']} câu ({tk['ti_trung']:.1%})   (cần ≤ {NGUONG_TRUNG:.0%})")
    print(f"- Còn chữ nước ngoài: {tk['chu_ngoai']} câu")
    toi = set(loc_dieu_toi_pham(gom_dieu(idx)))
    da_giu = {r[0] for r in idx.execute("SELECT DISTINCT dieu FROM cau_hoi_sinh WHERE giu = 1")}
    phu = (len(toi & da_giu), len(toi))
    print(f"- Được giữ (giu = 1): {tk['giu']} câu; {tk['dieu_du_3']} Điều có ≥ 3 câu được giữ; phủ {phu[0]}/{phu[1]} Điều về tội phạm "
          f"({(phu[0] / phu[1]) if phu[1] else 0:.0%}; cần ≥ {NGUONG_PHU:.0%} mới quét hệ số)")

    ph = None
    tk_xet = tk
    bo, ten_bo = None, f"{args.bo_cau_hoi.name}[{args.tap}]"
    try:
        bo = doc_bo(args.bo_cau_hoi, args.tap)
    except BoCauHoiError as e:
        print(f"\n(không đọc được bộ câu hỏi: {e})")
    if bo is not None:
        dieu_bo = {f"dieu {d}" for c in bo for d in c["dieu"]}
        tk_bo = thong_ke_cau_hoi(idx, emb.name, chi_dieu=dieu_bo)
        if tk_bo["co_vec"]:
            print(f"- Riêng {tk_bo['so_dieu']} Điều là đáp án của {ten_bo} ({tk_bo['co_vec']} câu): khứ hồi hạng 1 {tk_bo['ti_hang1']:.0%}, "
                  f"top 3 {tk_bo['ti_top3']:.0%}, trùng {tk_bo['ti_trung']:.1%}")
            if tk_bo["so_dieu"] >= 10:
                tk_xet = tk_bo                                   # đây là mẫu về tội phạm: dùng nó để kết luận, không dùng cả Phần chung
    if not args.chi_thong_ke:
        if bo is None:
            print("\n(bỏ phần so phiếu: không có bộ câu hỏi)")
        else:
            try:
                ph = so_phieu(idx, emb, bo, args.ngay)
            except (EmbedError, ValueError) as e:
                print(f"\nKhông so phiếu được: {e}")
            if ph:
                print(f"\nSo phiếu trên {ten_bo}: {ph['n']}/{ph['n_tong']} câu có đáp án thuộc Điều đã sinh câu hỏi "
                      f"(chỉ tính các câu này; cần ≥ {MIN_PHIEU}).")
                print(f"THẾ GIỚI ĐÓNG: cả hai bên chỉ chọn trong {ph['n_ung_vien']} Điều đã có câu sinh (so công bằng; xem so_phieu). "
                      f"Vì bỏ hết các Điều chưa sinh nên số Hit@1 ở đây LẠC QUAN hơn thực tế: chỉ dùng để so hai bên với nhau, "
                      f"không phải để báo độ chính xác của công cụ.")
                if ph["n"]:
                    print("| xếp hạng bằng | Hit@1 | Hit@3 | Hit@5 | MRR |\n|---|---|---|---|---|")
                    for ten, k in (("chỉ chữ luật", ph["chu"]), ("chỉ câu sinh", ph["cau_hoi"])):
                        print(f"| {ten} | {k['hit1']:.0%} | {k['hit3']:.0%} | {k['hit5']:.0%} | {k['mrr']:.3f} |")
                    print(f"Đồng ý Điều hạng 1: {ph['dong_y']} câu. Bất đồng: {ph['bat_dong']} câu — chữ luật đúng {ph['chu_dung_khi_bat_dong']}, "
                          f"câu sinh đúng {ph['cau_hoi_dung_khi_bat_dong']}.")
                    r = ti_le_cuu_pha(ph)
                    print(f"Cứu {ph['cuu']} (chữ luật sai, câu sinh đúng) / phá {ph['pha']} (chữ luật đúng, câu sinh sai) = "
                          f"{'—' if r is None else ('∞' if r == float('inf') else f'{r:.2f}')}   (cần ≥ {NGUONG_CUU_PHA})")

    trang_thai, ly = ket_luan(tk_xet, ph, phu)
    ten_tt = {"DAT": "ĐẠT", "DAT_SO_BO": "ĐẠT SƠ BỘ (mới phủ một phần luật)", "CHUA_DAT": "CHƯA ĐẠT",
              "THIEU": "CHƯA ĐỦ DỮ LIỆU để kết luận"}[trang_thai]
    print("\nKẾT LUẬN: " + ten_tt + (" — đáng quét hệ số: python scripts/danh_gia.py --quet-cau-hoi --tap dev"
                                   if trang_thai == "DAT" else ""))
    for x in ly:
        print(f"  - {x}")
    if trang_thai == "CHUA_DAT":
        print("  => chưa nên dùng câu sinh sẵn (giữ --dung-cau-hoi 0). Sinh lại bằng model/lời nhắc tốt hơn.")
    elif trang_thai == "DAT_SO_BO":
        print("  => chưa quét hệ số vội (Điều chưa sinh không bị gây nhiễu nên bảng quét sẽ lạc quan). Sinh nốt các Điều về tội phạm, rồi chạy lại lệnh này:\n"
              "     python scripts/sinh_cau_hoi.py --llm <model đã dùng>      (Ctrl+C lúc nào cũng được, chạy lại sẽ tiếp tục)")
    elif trang_thai == "THIEU" and ph is None and args.chi_thong_ke:
        print("  => chạy lại KHÔNG kèm --chi-thong-ke để so phiếu với chữ luật.")
    elif trang_thai == "THIEU":
        print("  => sinh thử đúng các Điều của bộ dev (Điều về tội phạm, không phải Phần chung) rồi chạy lại lệnh này:\n"
              "     python scripts/sinh_cau_hoi.py --theo-bo eval/bo_cau_hoi.json")
    return 0 if trang_thai in ("DAT", "DAT_SO_BO") else 2


if __name__ == "__main__":
    raise SystemExit(main())
