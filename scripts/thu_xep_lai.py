"""Thí nghiệm: xếp lại top-N Điều bằng mô hình đọc (câu hỏi, chữ Điều) cùng lúc. Chạy offline, không ghi vào chỉ mục.

  python scripts/tai_xep_lai.py                                  # (một lần) tải bge-reranker-v2-m3, ~2,3 GB
  python scripts/thu_xep_lai.py                                  # bge-reranker trên bộ dev, quét trọng số w
  python scripts/thu_xep_lai.py --xep-lai llm --llm qwen3:8b     # Qwen3-8B qua Ollama chấm điểm (không cần tải thêm)
  python scripts/thu_xep_lai.py --tap xac_nhan --chi-w 0.25      # xác nhận độc lập: CHỈ một w đã chốt trên dev
  python scripts/thu_xep_lai.py --tap kiem_tra --chi-w 0.25      # xác nhận cuối trên tập kiểm tra (đóng băng)

Câu hỏi nằm trong MỘT file duy nhất eval/bo_cau_hoi.json, chọn tập bằng --tap (mặc định dev).

Điểm cuối = z(điểm xếp lại) + w * z(điểm vector) trong N ứng viên; w = 0 là chỉ tin mô hình xếp lại.
Kết luận theo dải ổn định (>= 2 giá trị w liền kề cùng hơn baseline), không chọn ô cao nhất. Kèm kiểm định dấu cho số câu cứu / phá:
trên ~70 câu, chênh 2-4 câu rất dễ chỉ là ngẫu nhiên.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import index_path, load_config  # noqa: E402
from src.index.cau_hoi import LLMError, OllamaLLM, gom_dieu  # noqa: E402
from src.index.bo_cau_hoi import MAC_DINH, TAP, TAP_DONG_BANG, BoCauHoiError, doc_bo  # noqa: E402
from src.index.embedder import EmbedError, HashEmbedder, tu_config  # noqa: E402
from src.index.search import gop_theo_dieu, tim  # noqa: E402
from src.index.store import open_index  # noqa: E402
from src.index.xep_lai import (BgeReranker, LLMXepLai, XepLaiError, hang_dap_an, ket_luan_xep_lai, quet_w)  # noqa: E402

WS = (0, 0.25, 0.5, 1, 2, 4)


def ung_vien(idx, emb, bo, ngay, top, van_ban_dieu):
    items = []
    for c in bo:
        kq = tim(idx, c["cau_hoi"], embedder=emb, ngay=ngay, k=2000, che_do="vector", n_ung_vien=300)
        ds = gop_theo_dieu(kq.hits, max(top, 10))
        items.append({"id": c.get("id"), "cau_hoi": c["cau_hoi"], "dap_an": {f"dieu {d}" for d in c["dieu"]},
                      "cand": [{"dieu": d.dieu, "vec": float(d.tot_nhat.cosine or 0.0)} for d in ds],
                      "van_ban": [van_ban_dieu.get(d.dieu) or d.tot_nhat.text for d in ds[:top]]})
    return items


def cham_tat_ca(items, may, top, tep_nho: Path):
    try:
        nho = json.loads(tep_nho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        nho = {}
    loi = 0
    for n, it in enumerate(items, 1):
        khoa = hashlib.sha1(json.dumps([may.name, top, it["cau_hoi"], [c["dieu"] for c in it["cand"][:top]],
                                        [hashlib.sha1(v.encode()).hexdigest()[:8] for v in it["van_ban"]]]).encode()).hexdigest()
        if khoa not in nho:
            try:
                nho[khoa] = may.cham(it["cau_hoi"], it["van_ban"])
            except XepLaiError as e:
                loi += 1
                print(f"  ! câu {n}: {e}", file=sys.stderr)
                nho[khoa] = None
            if n % 5 == 0:
                tep_nho.parent.mkdir(parents=True, exist_ok=True)
                tep_nho.write_text(json.dumps(nho), encoding="utf-8")
                print(f"  đã chấm {n}/{len(items)} câu", flush=True)
        it["diem_xl"] = nho[khoa] if nho[khoa] is not None else [0.0] * len(it["van_ban"])
    tep_nho.parent.mkdir(parents=True, exist_ok=True)
    tep_nho.write_text(json.dumps(nho), encoding="utf-8")
    return loi


def in_bang(base, dong):
    print("| w (trọng số điểm vector) | Hit@1 | Hit@3 | MRR | cứu | phá | p (kiểm định dấu) |\n|---|---|---|---|---|---|---|")
    for d in dong:
        print(f"| {d['w']} | {d['hit1']:.1%} | {d['hit3']:.1%} | {d['mrr']:.3f} | {d['cuu']} | {d['pha']} | {d['p']:.2f} |")


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index", type=Path, default=None)
    ap.add_argument("--bo-cau-hoi", type=Path, default=MAC_DINH)
    ap.add_argument("--tap", choices=TAP, default="dev", help="tập câu hỏi (xac_nhan / kiem_tra bắt buộc kèm --chi-w)")
    ap.add_argument("--xep-lai", choices=("bge", "llm"), default="bge")
    ap.add_argument("--mo-hinh-bge", type=Path, default=ROOT / "models" / "bge-reranker-v2-m3")
    ap.add_argument("--llm", default="qwen3:8b")
    ap.add_argument("--top", type=int, default=5)
    ap.add_argument("--chi-w", type=float, default=None, help="chỉ đo một w (bắt buộc với tập xac_nhan / kiem_tra)")
    ap.add_argument("--ngay", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--endpoint", default=None)
    ap.add_argument("--gia", action="store_true", help="vector giả cho tìm kiếm (chỉ thử đường ống)")
    args = ap.parse_args()

    if args.tap in TAP_DONG_BANG and args.chi_w is None:
        sys.exit(f"Tập {args.tap} chỉ dùng để XÁC NHẬN với w đã chốt trên tập dev: thêm --chi-w <w>. Không quét w trên tập này.")
    ip = args.index or index_path()
    if not ip.exists():
        sys.exit(f"LỖI: chưa có {ip}. Chạy trước: python scripts/build_index.py")
    cfg = load_config()
    try:
        if args.xep_lai == "bge":
            may = BgeReranker(args.mo_hinh_bge)
        else:
            may = LLMXepLai(OllamaLLM(args.llm, (cfg.get("llm_local") or {}).get("endpoint") or "http://localhost:11434", nhiet_do=0.0))
    except XepLaiError as e:
        sys.exit(f"LỖI: {e}")
    idx = open_index(ip)
    emb = HashEmbedder() if args.gia else tu_config(cfg, model=args.model, endpoint=args.endpoint)
    try:
        bo = doc_bo(args.bo_cau_hoi, args.tap)
    except BoCauHoiError as e:
        sys.exit(f"LỖI: {e}")
    van_ban_dieu = {d: v["van_ban"] for d, v in gom_dieu(idx).items()}
    print(f"Tìm top {args.top} Điều cho {len(bo)} câu của {args.bo_cau_hoi.name}[{args.tap}] (vector, như tìm kiếm mặc định)...")
    try:
        items = ung_vien(idx, emb, bo, args.ngay, args.top, van_ban_dieu)
    except EmbedError as e:
        sys.exit(f"LỖI: {e}")
    print(f"Chấm lại bằng {may.name} ...")
    try:
        loi = cham_tat_ca(items, may, args.top, ROOT / "db" / f"xep_lai_{args.xep_lai}.json")
    except (LLMError, KeyboardInterrupt) as e:
        sys.exit(f"Dừng: {e}. Chạy lại lệnh này để tiếp tục (điểm đã chấm được giữ).")
    if loi > len(bo) // 5:
        sys.exit(f"LỖI: {loi}/{len(bo)} câu không chấm được, kết quả không đáng tin. Kiểm tra model/Ollama rồi chạy lại.")
    if loi:
        print(f"Lưu ý: {loi} câu không chấm được, giữ thứ tự vector cho các câu đó.")

    n = len(items)
    goc = [hang_dap_an([c["dieu"] for c in it["cand"]], it["dap_an"]) for it in items]
    tran = sum(1 for r in goc if r and r <= args.top) / n
    ws = (args.chi_w,) if args.chi_w is not None else WS
    for top in sorted({3, args.top} if args.top > 3 and args.chi_w is None else {args.top}):
        base, dong = quet_w(items, ws, top)
        print(f"\n== Xếp lại top {top} ==  baseline (vector): Hit@1 {base['hit1']:.1%} ({round(base['hit1'] * n)}/{n}), "
              f"Hit@3 {base['hit3']:.1%}, MRR {base['mrr']:.3f}; trần (đáp án nằm trong top {top}) {sum(1 for r in goc if r and r <= top) / n:.1%}")
        in_bang(base, dong)
        if args.chi_w is None and top == args.top:
            co, ly = ket_luan_xep_lai(base, dong)
            print(f"\nKẾT LUẬN: {'CÓ LỢI' if co else 'CHƯA CHỨNG MINH ĐƯỢC LỢI'} — {ly}")
            pmin = min(d["p"] for d in dong)
            if co and pmin > 0.05:
                print(f"  ⚠ Chưa có ý nghĩa thống kê (p nhỏ nhất = {pmin:.2f} > 0,05): hướng tích cực và ổn định, nhưng với cỡ mẫu này vẫn có thể chỉ là ngẫu nhiên.\n"
                      f"    Cần bộ câu hỏi lớn hơn và đã được người duyệt nhãn trước khi coi là bằng chứng.")
            print("  (nhiễu: chênh dưới 3 điểm phần trăm ≈ 2 câu.)")
    if args.chi_w is not None:
        print("\nĐây là xác nhận một w cố định đã chốt trên bộ dev; không chỉnh gì thêm theo kết quả này.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
