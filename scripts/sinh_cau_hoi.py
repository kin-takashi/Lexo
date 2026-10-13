"""Sinh sẵn câu hỏi đời thường cho từng Điều bằng LLM local, rồi nhúng bằng bge-m3 (CHẠY LẠI ĐƯỢC TỪ CHỖ DỪNG).

  python scripts/sinh_cau_hoi.py --xem-lenh 173         # chỉ in lời nhắc gửi cho LLM cho Điều 173, không gọi gì
  python scripts/sinh_cau_hoi.py --dieu 173 174 321     # sinh thử vài Điều, IN RA, không ghi (xem chất lượng trước)
  python scripts/sinh_cau_hoi.py --thu 0                # không sinh thêm, chỉ nhúng phần thiếu và chạy lại vòng lọc
  python scripts/sinh_cau_hoi.py --thu 10               # sinh và LƯU cho 10 Điều ĐẦU chưa có (Điều đầu là Phần chung, KHÔNG đại diện cho các tội)
  python scripts/sinh_cau_hoi.py --mau 30               # sinh và lưu 30 Điều trải đều khắp bộ luật (mẫu thử có đại diện)
  python scripts/sinh_cau_hoi.py --theo-bo eval/bo_cau_hoi.json    # sinh đúng các Điều là đáp án của TẬP DEV (chỉ đọc SỐ Điều, không đưa chữ câu hỏi cho LLM)
  python scripts/sinh_cau_hoi.py                        # sinh cho tất cả Điều còn thiếu, rồi nhúng; Ctrl+C an toàn
  python scripts/sinh_cau_hoi.py --khong-nhung          # chỉ sinh chữ, chưa nhúng

Cần đã chạy scripts/build_index.py (đọc chữ Điều từ chỉ mục). Điều đã đổi chữ (sau khi duyệt hiệu đính / áp luật mới)
sẽ được sinh lại; Điều không đổi thì giữ nguyên. --theo-bo chỉ đọc tập dev của eval/bo_cau_hoi.json; tuyệt đối không dùng tập xac_nhan / kiem_tra để sinh.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import index_path, load_config  # noqa: E402
from src.index.cau_hoi import (LLMError, LLMGia, OllamaLLM, PROMPT, can_sinh, chon_mo_hinh, chon_trai_deu, dieu_dap_an, loc_dieu_toi_pham, don_cau_hoi_mo_coi, la_model_nghi,  # noqa: E402
                               gom_dieu, hang_dieu_cua_cau_hoi, lam_moi_theo_phien_ban_lenh, loc_vong, luu_cau_hoi, sinh_mot)
from src.index.bo_cau_hoi import BoCauHoiError, doc_bo  # noqa: E402
from src.index.chan_doan import loc_trung  # noqa: E402
from src.index.embedder import EmbedError, HashEmbedder, tu_config  # noqa: E402
from src.index.store import luu_vector, open_index, thieu_vector_cau_hoi  # noqa: E402


def phut(g: float) -> str:
    return f"{g / 60:.0f} phút" if g >= 90 else f"{g:.0f} giây"


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index", type=Path, default=None)
    ap.add_argument("--llm", default=None, help="model Ollama dùng để viết câu hỏi (mặc định: tự chọn trong số đã cài)")
    ap.add_argument("--endpoint", default=None)
    ap.add_argument("--embed-model", default=None, help="model nhúng (mặc định bge-m3, phải trùng với lúc build_index)")
    ap.add_argument("--so-cau", type=int, default=5)
    ap.add_argument("--xem-lenh", metavar="SO_DIEU", help="in lời nhắc cho một Điều rồi thoát")
    ap.add_argument("--dieu", nargs="+", metavar="SO_DIEU", help="sinh thử cho các Điều này, chỉ in, không ghi")
    ap.add_argument("--thu", type=int, metavar="N", help="chỉ sinh (và lưu) cho N Điều đầu còn thiếu (Điều đầu = Phần chung; muốn mẫu đại diện dùng --mau)")
    ap.add_argument("--mau", type=int, metavar="N", help="chỉ sinh (và lưu) cho N Điều trải đều trong số còn thiếu")
    ap.add_argument("--theo-bo", type=Path, metavar="FILE", help="chỉ sinh cho các Điều là đáp án của TẬP DEV trong file này, ví dụ eval/bo_cau_hoi.json (chỉ đọc số Điều)")
    ap.add_argument("--loc-vong", type=int, default=3, metavar="TOP",
                    help="giữ câu hỏi chỉ khi Điều nguồn đứng trong TOP hạng đầu khi tìm bằng chính câu đó (mặc định 3; 0 = giữ hết)")
    ap.add_argument("--ca-dieu", action="store_true",
                    help="sinh cho cả Điều không phải điều về tội phạm (Phần chung: nguyên tắc, tuổi, hiệu lực…); mặc định bỏ vì chỉ cho câu sai và trùng")
    ap.add_argument("--khong-nhung", action="store_true")
    ap.add_argument("--gia", action="store_true", help="LLM giả + vector giả (thử đường ống)")
    args = ap.parse_args()

    cfg = load_config()
    ip = args.index or index_path()
    if not ip.exists():
        sys.exit(f"LỖI: chưa có {ip}. Chạy trước: python scripts/build_index.py")
    idx = open_index(ip)
    dieu = gom_dieu(idx)
    if not dieu:
        sys.exit("LỖI: chỉ mục chưa có đoạn nào. Chạy scripts/build_index.py trước.")
    print(f"{len(dieu)} Điều đang hiệu lực có chữ riêng.")
    if not args.ca_dieu:
        toi = loc_dieu_toi_pham(dieu)
        print(f"Chỉ sinh cho {len(toi)} Điều về tội phạm (tiêu đề 'Tội …'); bỏ {len(dieu) - len(toi)} Điều Phần chung/khái niệm. Thêm --ca-dieu để sinh cả chúng.")
        dieu = toi

    if args.xem_lenh:
        d = dieu.get(f"dieu {args.xem_lenh}")
        if not d:
            sys.exit(f"Không có Điều {args.xem_lenh} (hoặc không có chữ riêng).")
        print("\n" + PROMPT.format(n=args.so_cau, van_ban=d["van_ban"]))
        return 0

    endpoint = args.endpoint or (cfg.get("llm_local") or {}).get("endpoint") or "http://localhost:11434"
    try:
        if args.gia:
            llm = LLMGia()
        else:
            ten = args.llm or (cfg.get("llm_local") or {}).get("extract_model") or (cfg.get("llm_local") or {}).get("agent_model")
            if not ten:
                ten, da_cai = chon_mo_hinh(endpoint)
                print(f"Tự chọn model {ten} (đã cài: {', '.join(da_cai)}). Đổi bằng --llm.")
            llm = OllamaLLM(ten, endpoint, think=bool((cfg.get("llm_local") or {}).get("think", False)))
            print(f"Mô hình viết: {ten}" + (" (đã TẮT chế độ nghĩ)" if la_model_nghi(ten) else ""))
    except LLMError as e:
        sys.exit(f"LỖI: {e}")

    if args.dieu:                                                    # xem thử, không ghi
        for so in args.dieu:
            d = dieu.get(f"dieu {so}")
            if not d:
                print(f"\nĐiều {so}: không có.")
                continue
            t0 = time.perf_counter()
            try:
                ds = sinh_mot(llm, d, args.so_cau)
            except LLMError as e:
                sys.exit(f"LỖI: {e}")
            print(f"\n{d['tieu_de']}   ({time.perf_counter() - t0:.0f} giây)")
            hang = [None] * len(ds)
            if ds:
                try:                                                  # hạng của Điều đúng khi tìm bằng chính câu đó (cần bge-m3 và chỉ mục đã nhúng)
                    emb = HashEmbedder() if args.gia else tu_config(cfg, model=args.embed_model, endpoint=args.endpoint)
                    hang = hang_dieu_cua_cau_hoi(idx, emb, [f"dieu {so}"] * len(ds), ds)
                except (EmbedError, ValueError):
                    pass
            for c, h in zip(ds, hang):
                print(f"  - {c}" + (f"   [Điều đúng hạng {h}]" if h else ""))
            if not ds:
                print("  (không có câu nào qua bộ lọc)")
        if getattr(llm, "da_thay_think", False):
            print("\nCẢNH BÁO: model vẫn 'nghĩ' dù đã yêu cầu tắt. Cập nhật Ollama (cần bản >= 0.9) rồi chạy lại.")
        print("\n(chế độ --dieu: chưa ghi gì)")
        return 0

    xoa = lam_moi_theo_phien_ban_lenh(idx)
    if xoa:
        print(f"Lời nhắc đã đổi phiên bản: xoá {xoa} câu hỏi sinh bằng lời nhắc cũ để sinh lại.")
    xoa = don_cau_hoi_mo_coi(idx, dieu)
    if xoa:
        print(f"Đã xoá {xoa} câu hỏi của Điều không còn hiệu lực.")
    thieu = can_sinh(idx, dieu, llm.name)
    print(f"Mô hình viết: {llm.name}. Điều cần sinh: {len(thieu)}/{len(dieu)}.")
    if args.theo_bo:
        try:
            chon = dieu_dap_an(doc_bo(args.theo_bo, "dev"))
        except BoCauHoiError as e:
            sys.exit(f"LỖI: {e}")
        thieu = [d for d in thieu if d in chon]
        print(f"Theo {args.theo_bo.name}: {len(thieu)} Điều còn thiếu trong {len(chon)} Điều đáp án.")
    if args.mau is not None:
        thieu = chon_trai_deu(thieu, args.mau)
    if args.thu is not None:
        thieu = thieu[: args.thu]
    t0, xong, loi = time.perf_counter(), 0, 0
    try:
        for d in thieu:
            ds = sinh_mot(llm, dieu[d], args.so_cau)
            if len(ds) < 3:
                loi += 1
                with idx:
                    idx.execute("DELETE FROM cau_hoi_sinh WHERE dieu = ? AND mo_hinh = ?", (d, llm.name))     # không để lại bản cũ kém
                print(f"  ! {dieu[d]['tieu_de'][:60]}: chỉ {len(ds)} câu qua bộ lọc, bỏ qua (chạy lại để thử lần nữa)")
            else:
                luu_cau_hoi(idx, d, dieu[d]["hash"], llm.name, ds)
            xong += 1
            if xong % 5 == 0 or xong == len(thieu):
                dt = time.perf_counter() - t0
                print(f"  [{xong}/{len(thieu)}] đã {phut(dt)}, còn khoảng {phut((len(thieu) - xong) * dt / xong)}", flush=True)
    except KeyboardInterrupt:
        print("\nĐã dừng. Phần đã sinh được lưu rồi, chạy lại để làm tiếp.")
        return 130
    except LLMError as e:
        print(f"\nLỖI: {e}\nPhần đã sinh được lưu rồi, sửa lỗi rồi chạy lại để làm tiếp.")
        return 1
    if getattr(llm, "da_thay_think", False):
        print("CẢNH BÁO: model vẫn 'nghĩ' dù đã yêu cầu tắt (chậm hơn nhiều). Cập nhật Ollama (cần bản >= 0.9).")
    if loi:
        print(f"{loi} Điều chưa đủ 3 câu hợp lệ; chạy lại lệnh này để thử lại các Điều đó.")

    if args.khong_nhung:
        return 0
    emb = HashEmbedder() if args.gia else tu_config(cfg, model=args.embed_model, endpoint=args.endpoint)
    thieu_v = thieu_vector_cau_hoi(idx, emb.name)
    print(f"Nhúng {len(thieu_v)} câu hỏi (mô hình {emb.name}).")
    try:
        for i in range(0, len(thieu_v), 32):
            nhom = thieu_v[i: i + 32]
            luu_vector(idx, emb.name, [r["hash"] for r in nhom], emb.embed([r["text"] for r in nhom]))
    except EmbedError as e:
        print(f"LỖI: {e}\nChạy lại lệnh này để nhúng tiếp.")
        return 1
    lv = loc_vong(idx, emb.name, args.loc_vong)
    if lv["so_cau"]:
        print(f"Vòng lọc: giữ {lv['giu']}/{lv['so_cau']} câu; {lv['hang1']} câu ({lv['hang1'] / lv['so_cau']:.0%}) tìm ra đúng Điều nguồn ở hạng 1 "
              f"(thước đo chất lượng câu sinh, không dùng bộ kiểm tra).")
        lt = loc_trung(idx, emb.name)
        print(f"Lọc trùng: bỏ thêm {lt['loai']} câu trùng hoặc gần trùng câu của Điều khác (câu chép ví dụ, câu chung chung không phân biệt được Điều nào).")
    n = idx.execute("SELECT COUNT(*) FROM cau_hoi_sinh WHERE giu = 1").fetchone()[0]
    nd = idx.execute("SELECT COUNT(DISTINCT dieu) FROM cau_hoi_sinh WHERE mo_hinh = ? AND giu = 1", (llm.name,)).fetchone()[0]
    print(f"Xong: {n} câu hỏi được giữ, phủ {nd}/{len(dieu)} Điều.")
    print("Bước tiếp: python scripts/chan_doan_cau_hoi.py   (chẩn đoán có đáng dùng không; chỉ khi ĐẠT mới quét hệ số bằng danh_gia.py --quet-cau-hoi)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
