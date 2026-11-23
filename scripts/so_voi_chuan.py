"""So cách tách hành vi của mô hình với cách tách «chuẩn» của Claude (làm mù, nhiều lần). Đo xem mô hình «gần chuẩn» tới đâu.

  python scripts/xuat_chuan_mu.py                       # 1) xuất câu hỏi mù (không đáp án) + lời nhắc; dán vào phiên Claude MỚI, lặp 3 lần
  # lưu 3 câu trả lời thành eval/chuan_mu/claude_1.json, claude_2.json, claude_3.json
  python scripts/so_voi_chuan.py --chuan eval/chuan_mu/claude_*.json --du-doan eval/tach_dev_qwen3-8b-lexo-sach-n368_thuan_0vd.json
  python scripts/so_voi_chuan.py --chuan eval/chuan_mu/claude_*.json --du-doan a.json b.json --sim bge --tim-du --luu eval/so_voi_chuan.md

--sim chu   (mặc định) độ tương đồng chữ, chạy offline, không cần Ollama.
--sim bge   cosine bge-m3 qua Ollama (đúng mô hình đang dùng để tìm Điều); nên dùng cho số đo chính.
--sim gia   vector băm, chỉ thử đường ống.
--tim-du    thêm số đo cuối: «tìm đủ» khi dùng cách tách của mô hình so với của từng bản chuẩn (cùng đường truy hồi; cần chỉ mục và, với bge, Ollama).

Ngưỡng ghép --tau (mặc định 0.40 với chu, 0.70 với bge) CHƯA hiệu chỉnh; vì vậy số đo chính là `đồng số hành vi` và `ghép` (không ngưỡng),
F1 chỉ để tham khảo (báo kèm F1 ở tau ± 0.1). Chuẩn là Claude, KHÔNG phải luật: số này đo độ giống Claude, không đo đúng-sai pháp lý.
Cần >= 2 bản chuẩn để có TRẦN (Claude với Claude); với 1 bản chỉ có số đo tuyệt đối. Tập đóng băng cần --da-chot như các script khác.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import index_path, load_config  # noqa: E402
from src.index.bo_cau_hoi import MAC_DINH, TAP, TAP_DONG_BANG, BoCauHoiError, doc_bo, loc_theo_id  # noqa: E402
from src.index.embedder import EmbedError, HashEmbedder, tu_config  # noqa: E402
from src.index.so_voi_chuan import (boot_hieu, doc_tach, so_voi_cac_chuan, tong_hop, tran_chuan, tuong_dong_chu,  # noqa: E402
                                    tuong_dong_vec)
from src.index.tim_du import cham  # noqa: E402

TAU_MAC_DINH = {"chu": 0.40, "bge": 0.70, "gia": 0.50}


def nap_danh_gia_nhieu():
    spec = importlib.util.spec_from_file_location("danh_gia_nhieu_mod", ROOT / "scripts" / "danh_gia_nhieu.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def doc_file(p: Path) -> dict[str, list[str]]:
    try:
        return doc_tach(json.loads(p.read_text(encoding="utf-8")))
    except (OSError, ValueError) as e:
        raise SystemExit(f"LỖI: {p}: {e}")


def pc(x: float) -> str:
    return f"{x:.0%}"


def diem(x: float) -> str:
    return f"{x * 100:+.0f}"


def main(argv: list[str] | None = None) -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bo-cau-hoi", type=Path, default=MAC_DINH)
    ap.add_argument("--tap", choices=TAP, default="dev")
    ap.add_argument("--chi-id", default=None, help="chỉ các id này (cho phép khoảng như dn01-dn14)")
    ap.add_argument("--chuan", type=Path, nargs="+", required=True, help="các bản tách chuẩn (Claude mù), từ 2 bản trở lên để có trần")
    ap.add_argument("--du-doan", type=Path, nargs="+", required=True, help="các bản tách của mô hình cần đo")
    ap.add_argument("--sim", choices=tuple(TAU_MAC_DINH), default="chu")
    ap.add_argument("--tau", type=float, default=None)
    ap.add_argument("--bien", type=float, default=0.15, help="biên «không kém trần quá ...» (mặc định 0.15 = 15 điểm phần trăm)")
    ap.add_argument("--tim-du", action="store_true", help="thêm số đo «tìm đủ» (cần chỉ mục)")
    ap.add_argument("--m", type=int, default=3)
    ap.add_argument("--index", type=Path, default=None)
    ap.add_argument("--model", default=None, help="mô hình nhúng khi --sim bge / --tim-du")
    ap.add_argument("--endpoint", default=None)
    ap.add_argument("--hat", type=int, default=42, help="hạt cho bootstrap")
    ap.add_argument("--chi-tiet", action="store_true")
    ap.add_argument("--da-chot", action="store_true", help="xác nhận cấu hình đã chốt (bắt buộc với tập đóng băng)")
    ap.add_argument("--luu", type=Path, default=None)
    args = ap.parse_args(argv)
    if args.tap in TAP_DONG_BANG and not args.da_chot:
        sys.exit(f"LỖI: tập {args.tap!r} là tập đóng băng; chỉ chạy một lần với cấu hình đã chốt, thêm --da-chot.")
    tau = TAU_MAC_DINH[args.sim] if args.tau is None else args.tau

    try:
        bo = doc_bo(args.bo_cau_hoi, args.tap, "nhieu_dieu")
        if args.chi_id:
            bo = loc_theo_id(bo, args.chi_id)
    except BoCauHoiError as e:
        sys.exit(f"LỖI: {e}")
    if not bo:
        sys.exit("LỖI: không có tình huống nhiều Điều nào để so.")
    ids = [c["id"] for c in bo]
    chuan = [doc_file(p) for p in args.chuan]
    mo_hinh = {p.stem.removeprefix("tach_dev_"): doc_file(p) for p in args.du_doan}
    for ten, d in [(p.name, c) for p, c in zip(args.chuan, chuan)] + list(mo_hinh.items()):
        thieu = [i for i in ids if i not in d]
        if thieu:
            sys.exit(f"LỖI: {ten} thiếu {len(thieu)} id: {', '.join(thieu[:8])}{'...' if len(thieu) > 8 else ''}")

    emb = None
    if args.sim != "chu" or args.tim_du:
        emb = HashEmbedder() if args.sim == "gia" else tu_config(load_config(), model=args.model, endpoint=args.endpoint)
    td = tuong_dong_chu
    try:
        if args.sim != "chu":
            td = tuong_dong_vec(emb.embed)
            td.nap([hv for d in [*chuan, *mo_hinh.values()] for i in ids for hv in d[i]])        # nhúng trước theo lô
        tran = tran_chuan(chuan, ids, td, tau) if len(chuan) >= 2 else None
        kq = {t: so_voi_cac_chuan(d, chuan, ids, td, tau) for t, d in mo_hinh.items()}
        f1_lo = {t: tong_hop(so_voi_cac_chuan(d, chuan, ids, td, max(0.0, tau - 0.1)))["f1"] for t, d in mo_hinh.items()}
        f1_hi = {t: tong_hop(so_voi_cac_chuan(d, chuan, ids, td, min(1.0, tau + 0.1)))["f1"] for t, d in mo_hinh.items()}
        tran_lo = tong_hop(tran_chuan(chuan, ids, td, max(0.0, tau - 0.1)))["f1"] if tran else None
        tran_hi = tong_hop(tran_chuan(chuan, ids, td, min(1.0, tau + 0.1)))["f1"] if tran else None

        # số đo cuối (tùy chọn): «tìm đủ» khi dùng cách tách của mô hình / của từng bản chuẩn, cùng đường truy hồi
        td_mh: dict[str, list[float]] = {}
        td_chuan: list[float] | None = None
        if args.tim_du:
            dgn = nap_danh_gia_nhieu()
            ip = args.index or index_path()
            if not ip.exists():
                sys.exit(f"LỖI: chưa có {ip}. Chạy trước: python scripts/build_index.py")
            idx, nho = dgn.open_index(ip), dgn.NhoTam(emb)

            def tim_du_cua(d: dict[str, list[str]]) -> list[float]:
                return [cham(c["dieu"], [dgn.xep_hang(idx, nho, hv, dgn.CHE_DO_MAC_DINH, None) for hv in d[c["id"]]], args.m)["tim_du"] for c in bo]
            td_mh = {t: tim_du_cua(d) for t, d in mo_hinh.items()}
            theo_chuan = [tim_du_cua(c) for c in chuan]
            td_chuan = [sum(v[k] for v in theo_chuan) / len(theo_chuan) for k in range(len(bo))]
    except EmbedError as e:
        sys.exit(f"LỖI: {e}")

    n = len(ids)
    dong = [f"So với chuẩn Claude (mù): {len(chuan)} bản chuẩn, {n} tình huống [{args.tap}], độ tương đồng `{args.sim}`, ngưỡng ghép {tau:.2f} (chưa hiệu chỉnh)", ""]
    cot = ["đồng số hành vi", "ghép", "F1 (τ)", "F1 (τ-0.1 / τ+0.1)", "lệch TB (+ = tách thừa)"] + (["tìm đủ"] if args.tim_du else [])
    dong += ["| | " + " | ".join(cot) + " |", "|---|" + "---|" * len(cot)]

    def theo_cot(tb: dict[str, float], lo: float, hi: float, tdu: list[float] | None) -> str:
        c = [pc(tb["bang_so"]), pc(tb["ghep"]), pc(tb["f1"]), f"{pc(lo)} / {pc(hi)}", f"{tb['lech']:+.2f}"]
        if args.tim_du:
            c.append(pc(sum(tdu) / n) if tdu is not None else "–")
        return " | ".join(c)

    tb_tran = tong_hop(tran) if tran else None
    if tb_tran:
        dong.append(f"| **TRẦN** (Claude với Claude, {len(chuan)} bản) | " + theo_cot(tb_tran, tran_lo, tran_hi, td_chuan) + " |")
    else:
        dong.append("| TRẦN | chưa có (cần ≥ 2 bản chuẩn) |" + " |" * (len(cot) - 1))
    tb_mh = {t: tong_hop(k) for t, k in kq.items()}
    for t in mo_hinh:
        dong.append(f"| {t} | " + theo_cot(tb_mh[t], f1_lo[t], f1_hi[t], td_mh.get(t)) + " |")

    if tran:
        dong += ["", f"Mô hình so với TRẦN (hiệu = mô hình − trần, tính theo cặp từng tình huống; khoảng tin cậy bootstrap 95%, hạt {args.hat}; "
                     f"«không kém trần quá {args.bien * 100:.0f} điểm» khi cận dưới ≥ −{args.bien * 100:.0f}):", "",
                 "| mô hình | số đo | mô hình / trần | hiệu (điểm %) | KTC 95% | không kém trần quá biên? |", "|---|---|---|---|---|---|"]
        so_do = [("đồng số hành vi", "bang_so"), ("ghép", "ghep")]
        for t in mo_hinh:
            for ten, k in so_do:
                a = [kq[t][i][k] for i in ids]
                b = [tran[i][k] for i in ids]
                h, lo, hi = boot_hieu(a, b, hat=args.hat)
                ti = (sum(a) / sum(b)) if sum(b) else float("nan")
                dong.append(f"| {t} | {ten} | {pc(ti)} | {diem(h)} | [{diem(lo)}, {diem(hi)}] | {'có' if lo >= -args.bien else 'chưa chắc'} |")
            if args.tim_du and td_chuan is not None:
                h, lo, hi = boot_hieu(td_mh[t], td_chuan, hat=args.hat)
                ti = (sum(td_mh[t]) / sum(td_chuan)) if sum(td_chuan) else float("nan")
                dong.append(f"| {t} | tìm đủ (so với tách của chuẩn) | {pc(ti)} | {diem(h)} | [{diem(lo)}, {diem(hi)}] | {'có' if lo >= -args.bien else 'chưa chắc'} |")
        dong += ["", f"Với {n} tình huống, khoảng tin cậy rộng cỡ ±15–20 điểm: chỉ kết luận được «không kém chuẩn quá ~{args.bien * 100:.0f} điểm», không chứng minh được «cách chuẩn vài phần trăm»."]

    dong += ["", "Ghi chú đọc: chuẩn là cách tách của Claude (không phải đáp án pháp lý); ghép = tổng độ tương đồng của phép ghép tối ưu / max(số hành vi hai bên); "
                 "tiền tố tên tội được bỏ trước khi so. Câu hỏi và dữ liệu học đều do Claude soạn nên số đo trên dev nghiêng lạc quan."]
    if args.chi_tiet:
        dong += ["", "## Tình huống mô hình tách khác số hành vi với đa số bản chuẩn", ""]
        for t, d in mo_hinh.items():
            for i in ids:
                dem = Counter(len(c[i]) for c in chuan).most_common(1)[0][0]
                if len(d[i]) != dem:
                    dong.append(f"- [{t}] {i}: mô hình {len(d[i])} hành vi, chuẩn {[len(c[i]) for c in chuan]}")
    txt = "\n".join(dong)
    print(txt)
    if args.luu:
        args.luu.parent.mkdir(parents=True, exist_ok=True)
        args.luu.write_text(txt + "\n", encoding="utf-8")
        print(f"\nĐã ghi {args.luu}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
