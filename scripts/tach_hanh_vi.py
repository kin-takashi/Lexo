"""Tách các tình huống nhiều Điều của bộ đo thành từng hành vi bằng qwen3:4b (Ollama), CHỈ bằng lời nhắc; ghi file để chấm bằng danh_gia_nhieu.py.

  python scripts/tach_hanh_vi.py --gia                                  # thử đường ống, không cần Ollama (KHÔNG phản ánh chất lượng thật)
  python scripts/tach_hanh_vi.py --tap dev --kieu ten_toi --vi-du 3     # tách 14 câu dev, ghi eval/tach_dev_qwen3-4b_ten_toi_3vd.json
  python scripts/tach_hanh_vi.py --tap dev --kieu thuan --vi-du 0       # không tiền tố tên tội, không ví dụ mẫu
  python scripts/danh_gia_nhieu.py --tap dev --du-doan eval/tach_dev_qwen3-4b_ten_toi_3vd.json   # rồi chấm

Chọn kiểu lời nhắc (--kieu, --vi-du, --quy-tac) bằng tập dev. Tập đóng băng (kiem_tra...) chỉ chạy MỘT lần với lời nhắc đã chốt, cần --da-chot,
và không ghi đè kết quả cũ. Kết quả cạnh tên file: <ra>.json là {id: [hành vi...]}, <ra>.log.jsonl là câu trả lời thô, số lần thử, thời gian.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import load_config  # noqa: E402
from src.index.bo_cau_hoi import MAC_DINH, TAP, TAP_DONG_BANG, BoCauHoiError, doc_bo  # noqa: E402
from src.index.cau_hoi import LLMError  # noqa: E402
from src.index.tach_hanh_vi import KIEU, LLMGiaTach, TachLLM, chon_vi_du, dung_tin_nhan, tach_mot  # noqa: E402
from src.index.tap_train import MAC_DINH as TRAIN_MAC_DINH, TapTrainError, doc_train  # noqa: E402


def ghi_nguyen_tu(duong_dan: Path, noi_dung: str) -> None:
    duong_dan.parent.mkdir(parents=True, exist_ok=True)
    tam = duong_dan.with_name(duong_dan.name + ".tmp")
    tam.write_text(noi_dung, encoding="utf-8", newline="\n")
    os.replace(tam, duong_dan)


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bo-cau-hoi", type=Path, default=MAC_DINH)
    ap.add_argument("--train", type=Path, default=TRAIN_MAC_DINH, help="nguồn ví dụ mẫu (few-shot)")
    ap.add_argument("--tap", choices=(*TAP, "tat_ca"), default="dev", help="tập có câu nhieu_dieu để tách (mặc định dev)")
    ap.add_argument("--model", default="qwen3:4b")
    ap.add_argument("--endpoint", default=None, help="mặc định: llm_local.endpoint trong config.yaml")
    ap.add_argument("--kieu", choices=KIEU, default="ten_toi", help="ten_toi: mỗi hành vi mở đầu bằng tên tội; thuan: như tập train gốc, không yêu cầu")
    ap.add_argument("--vi-du", type=int, default=3, help="số ví dụ mẫu lấy từ tập train (0 = không có)")
    ap.add_argument("--quy-tac", action="store_true", help="thêm đoạn quy tắc tách vào lời nhắc hệ thống")
    ap.add_argument("--dinh-dang", choices=("schema", "json"), default="schema", help="ép đầu ra theo schema (mặc định) hay chỉ yêu cầu JSON")
    ap.add_argument("--khong-no-think", action="store_true",
                    help="chỉ gửi think=false, không thêm «/no_think» vào câu hỏi (dùng khi đo mô hình đã tinh chỉnh; cần Ollama >= 0.9)")
    ap.add_argument("--chi-id", default=None, help="chỉ tách các id này, cách nhau dấu phẩy")
    ap.add_argument("--ra", type=Path, default=None)
    ap.add_argument("--da-chot", action="store_true", help="xác nhận lời nhắc đã chốt trên dev (bắt buộc với tập đóng băng)")
    ap.add_argument("--ghi-de", action="store_true", help="cho phép ghi đè file kết quả của tập đóng băng")
    ap.add_argument("--gia", action="store_true", help="LLM giả: chỉ thử đường ống")
    ap.add_argument("--xem-loi-nhac", action="store_true", help="in lời nhắc của câu đầu tiên rồi thoát, không gọi mô hình")
    args = ap.parse_args()
    if args.vi_du < 0:
        sys.exit("LỖI: --vi-du phải >= 0")

    dong_bang = args.tap in TAP_DONG_BANG or args.tap == "tat_ca"
    if dong_bang and not (args.da_chot or args.xem_loi_nhac or args.gia):
        sys.exit(f"LỖI: tập {args.tap!r} là tập đóng băng. Chỉ chạy một lần với lời nhắc đã chốt trên dev, thêm --da-chot để xác nhận. "
                 "Không chỉnh lời nhắc theo kết quả của tập này.")
    try:
        bo = doc_bo(args.bo_cau_hoi, args.tap, "nhieu_dieu")
        tat_ca_nhieu = doc_bo(args.bo_cau_hoi, None, "nhieu_dieu")
        mau = doc_train(args.train)
    except (BoCauHoiError, TapTrainError) as e:
        sys.exit(f"LỖI: {e}")
    if args.chi_id:
        ids = [s.strip() for s in args.chi_id.split(",") if s.strip()]
        bo = [c for c in bo if c["id"] in ids]
        if not bo:
            sys.exit(f"LỖI: không có id nào trong {ids} thuộc tập {args.tap}")

    cam_dieu = {d for c in tat_ca_nhieu for d in c["dieu"]}                  # loại mọi mẫu train trùng Điều với đáp án của bất kỳ câu nhieu_dieu nào
    vi_du = chon_vi_du(mau, args.vi_du, cam_dieu, args.kieu) if args.vi_du else []
    if args.vi_du and len(vi_du) < args.vi_du:
        sys.exit(f"LỖI: chỉ chọn được {len(vi_du)}/{args.vi_du} ví dụ mẫu không trùng Điều với bộ đo")

    if args.xem_loi_nhac:
        for m in dung_tin_nhan(bo[0]["cau_hoi"], args.kieu, vi_du, args.quy_tac):
            print(f"--- {m['role']} ---\n{m['content']}\n")
        print(f"(ví dụ mẫu: {', '.join(x['id'] for x in vi_du) or 'không có'})")
        return 0

    endpoint = args.endpoint or (load_config().get("llm_local") or {}).get("endpoint") or "http://localhost:11434"
    llm = LLMGiaTach() if args.gia else TachLLM(args.model, endpoint, dinh_dang=args.dinh_dang, no_think_mem=not args.khong_no_think)
    ten_mo_hinh = "gia" if args.gia else re.sub(r"[^\w.-]+", "-", args.model)
    ra = args.ra or ROOT / "eval" / f"tach_{args.tap}_{ten_mo_hinh}_{args.kieu}_{args.vi_du}vd{'_qt' if args.quy_tac else ''}{'_chon' if args.chi_id else ''}.json"
    log = ra.with_name(ra.stem + ".log.jsonl")
    if dong_bang and ra.exists() and not args.ghi_de:
        sys.exit(f"LỖI: {ra} đã có. Tập đóng băng chỉ chạy một lần; thêm --ghi-de nếu thật sự muốn ghi đè (và nói rõ trong báo cáo).")

    print(f"Tách {len(bo)} tình huống [{args.tap}] bằng {llm.name if hasattr(llm, 'name') else args.model}, kiểu {args.kieu}, "
          f"{len(vi_du)} ví dụ mẫu ({', '.join(x['id'] for x in vi_du) or '-'}){', có quy tắc' if args.quy_tac else ''}")
    ket_qua: dict[str, list[str]] = {}
    nhat_ky: list[str] = []
    loi_dinh_dang = 0
    try:
        for i, c in enumerate(bo, 1):
            r = tach_mot(llm, c["cau_hoi"], args.kieu, vi_du, args.quy_tac)
            ket_qua[c["id"]] = r["hanh_vi"]
            loi_dinh_dang += bool(r["loi"])
            nhat_ky.append(json.dumps({"id": c["id"], "so_hanh_vi": len(r["hanh_vi"]), "so_dieu_dap_an": len(c["dieu"]), "so_lan": r["so_lan"],
                                       "giay": r["giay"], "loi": r["loi"], "tho": r["tho"]}, ensure_ascii=False))
            print(f"  [{i}/{len(bo)}] {c['id']}: {len(r['hanh_vi'])} hành vi (đáp án {len(c['dieu'])} Điều), {r['giay']}s"
                  f"{', lần thử ' + str(r['so_lan']) if r['so_lan'] > 1 else ''}{'  !! LỖI: ' + r['loi'] if r['loi'] else ''}")
    except LLMError as e:
        sys.exit(f"LỖI: {e}")
    except KeyboardInterrupt:
        print("\nĐã dừng; không ghi gì.")
        return 130
    if getattr(llm, "da_thay_think", False):
        print("CẢNH BÁO: mô hình vẫn 'nghĩ' dù đã tắt; cập nhật Ollama (>= 0.9) để chạy nhanh và ổn định hơn.")

    ghi_nguyen_tu(ra, json.dumps(ket_qua, ensure_ascii=False, indent=1) + "\n")
    ghi_nguyen_tu(log, "\n".join(nhat_ky) + "\n")
    n = len(bo)
    dung = sum(1 for c in bo if len(ket_qua[c["id"]]) == len(c["dieu"]))
    print(f"\nĐã ghi {ra} và {log.name}")
    print(f"Số hành vi trung bình {sum(len(v) for v in ket_qua.values()) / n:.1f} (đáp án {sum(len(c['dieu']) for c in bo) / n:.1f} Điều); "
          f"tách đúng số hành vi {dung}/{n}; câu trả lời hỏng không đọc được {loi_dinh_dang}/{n}")
    print(f"Chấm: python scripts/danh_gia_nhieu.py --tap {args.tap} --du-doan {ra.as_posix()}" + (" --chi-tiet" if not dong_bang else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
