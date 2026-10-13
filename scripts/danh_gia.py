"""Đo chất lượng tìm kiếm trên bộ câu hỏi (eval/bo_cau_hoi.json, chọn tập bằng --tap, mặc định dev): Hit@k và MRR theo Điều, cho từng chế độ.

  python scripts/danh_gia.py                      # hybrid + vector + fts, in tóm tắt và các câu sai
  python scripts/danh_gia.py --chi-tiet           # in hạng của từng câu
  python scripts/danh_gia.py --luu eval/ket_qua.md
  python scripts/danh_gia.py --tap kiem_tra       # chỉ để báo cáo số cuối; --quet / --quet-cau-hoi chỉ chạy trên tập dev
  python scripts/danh_gia.py --gia                # vector giả, chỉ thử đường ống

Một câu "trúng" ở hạng r nếu Điều đáp án (bất kỳ Điều nào trong danh sách chấp nhận) đứng hạng r theo Điều.
Chỉ tính các câu trang_thai = da_duyet nếu thêm --chi-da-duyet.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import index_path, load_config  # noqa: E402
from src.index.bo_cau_hoi import MAC_DINH, TAP, TAP_DONG_BANG, BoCauHoiError, doc_bo  # noqa: E402
from src.index.cau_hoi import gom_dieu, loc_dieu_toi_pham  # noqa: E402
from src.index.chan_doan import ket_luan_quet  # noqa: E402
from src.index.embedder import EmbedError, HashEmbedder, tu_config  # noqa: E402
from src.index.search import CHE_DO, gop_theo_dieu, tim  # noqa: E402
from src.index.store import open_index  # noqa: E402

KS = (1, 3, 5, 10)
CANH_BAO: set[str] = set()


class NhoTam:
    """Bọc embedder: cùng một câu hỏi chỉ nhúng một lần dù chạy nhiều chế độ."""

    def __init__(self, emb):
        self.emb, self.name, self.cache = emb, emb.name, {}

    def embed(self, texts):
        out = []
        for t in texts:
            if t not in self.cache:
                self.cache[t] = self.emb.embed([t])[0]
            out.append(self.cache[t])
        return out


def hang_dap_an(idx, cau, emb, che_do, ngay, **tham_so):
    kq = tim(idx, cau["cau_hoi"], embedder=emb, ngay=ngay, k=2000, che_do=che_do, n_ung_vien=300, **tham_so)
    CANH_BAO.update(kq.canh_bao)
    ds = gop_theo_dieu(kq.hits, 10_000)
    chap_nhan = {f"dieu {d}" for d in cau["dieu"]}
    rank = next((i for i, d in enumerate(ds, 1) if d.dieu in chap_nhan), None)
    return rank, (ds[0].tieu_de if ds else "-")


def tom_tat(kq, n):
    hit = [sum(1 for r, _ in kq if r and r <= k) / n for k in (1, 3, 5)]
    return hit, sum(1 / r for r, _ in kq if r) / n


def quet(idx, bo, emb, ngay) -> int:
    """Thử lưới (trọng số từ khoá x bỏ từ dừng) cho hybrid. Câu hỏi chỉ nhúng một lần nhờ NhoTam."""
    n = len(bo)
    print(f"Quét hybrid trên {n} câu; trọng số từ khoá 0 = chỉ vector, 1 = ngang vector (RRF)\n")
    print("| trọng số từ khoá | bỏ từ dừng | Hit@1 | Hit@3 | Hit@5 | MRR |\n|---|---|---|---|---|---|")
    for tf in (0.0, 0.25, 0.5, 0.75, 1.0):
        for st in (False, True):
            if tf == 0.0 and st:
                continue
            try:
                kq = [hang_dap_an(idx, c, emb, "hybrid", ngay, trong_fts=tf, bo_tu_dung=st) for c in bo]
            except (EmbedError, ValueError) as e:
                sys.exit(f"LỖI: {e}")
            hit, mrr = tom_tat(kq, n)
            print(f"| {tf} | {'có' if st else 'không'} | " + " | ".join(f"{h:.0%}" for h in hit) + f" | {mrr:.3f} |")
    print("\nLưu ý: chọn cấu hình ổn định, đừng chọn đúng ô cao nhất — bộ này chỉ 58 câu nên chênh vài điểm là nhiễu.")
    return 0


def quet_cau_hoi(idx, bo, emb, ngay) -> int:
    """Vector thuần so với vector + câu hỏi sinh sẵn. Hệ số h: điểm Điều >= h x cosine(câu hỏi người dùng, câu hỏi sinh sẵn)."""
    n = len(bo)
    k = idx.execute("SELECT COUNT(*) FROM cau_hoi_sinh WHERE giu = 1").fetchone()[0]
    if not k:
        sys.exit("LỖI: chưa có câu hỏi sinh sẵn. Chạy: python scripts/sinh_cau_hoi.py")
    phu = idx.execute("SELECT COUNT(DISTINCT dieu) FROM cau_hoi_sinh WHERE giu = 1").fetchone()[0]
    tong = len(loc_dieu_toi_pham(gom_dieu(idx)))
    print(f"Vector + câu hỏi sinh sẵn ({k} câu, phủ {phu}/{tong} Điều) trên {n} câu kiểm tra; hệ số 0 = không dùng\n")
    if phu < 0.9 * tong:
        print(f"CẢNH BÁO: câu sinh mới phủ {phu}/{tong} Điều. Điều chưa có câu thì không bị 'gây nhiễu', nên bảng dưới đây lạc quan hơn thực tế "
              f"và chỉ để tham khảo; sinh nốt rồi đo lại.\n")
    print("| hệ số | Hit@1 | Hit@3 | Hit@5 | MRR |\n|---|---|---|---|---|")
    dong = []
    for h in (0.0, 0.6, 0.7, 0.8, 0.9, 1.0):
        try:
            kq = [hang_dap_an(idx, c, emb, "vector", ngay, he_so_cau_hoi=h) for c in bo]
        except (EmbedError, ValueError) as e:
            sys.exit(f"LỖI: {e}")
        hit, mrr = tom_tat(kq, n)
        dong.append((h, hit[0], mrr))
        print(f"| {h} | " + " | ".join(f"{x:.0%}" for x in hit) + f" | {mrr:.3f} |")
    for w in sorted(CANH_BAO):
        print(f"Lưu ý: {w}")
    co_loi, vi_sao = ket_luan_quet(dong)
    print(f"\nKết luận: {'CÓ LỢI' if co_loi else 'KHÔNG CÓ LỢI'} — {vi_sao}.")
    print("Chọn hệ số ổn định (kết quả tốt trên một dải hệ số), đừng chọn đúng ô cao nhất. Tập kiểm tra chỉ để xác nhận cuối; "
          "chỉnh hệ số bằng tập dev: --tap dev.")
    print("Nếu không có lợi, kiểm tra chất lượng câu sinh trước: python scripts/chan_doan_cau_hoi.py")
    return 0


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bo-cau-hoi", type=Path, default=MAC_DINH)
    ap.add_argument("--tap", choices=(*TAP, "tat_ca"), default="dev", help="tập câu hỏi để chấm (mặc định dev)")
    ap.add_argument("--che-do", nargs="+", choices=CHE_DO, default=list(CHE_DO))
    ap.add_argument("--ngay", default=None)
    ap.add_argument("--index", type=Path, default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--endpoint", default=None)
    ap.add_argument("--gia", action="store_true")
    ap.add_argument("--chi-da-duyet", action="store_true")
    ap.add_argument("--chi-tiet", action="store_true")
    ap.add_argument("--quet", action="store_true", help="thử các trọng số từ khoá / bỏ từ dừng cho chế độ hybrid rồi thoát")
    ap.add_argument("--quet-cau-hoi", action="store_true", help="đo vector có/không dùng câu hỏi sinh sẵn, thử vài hệ số, rồi thoát")
    ap.add_argument("--luu", type=Path, default=None, help="ghi báo cáo markdown")
    args = ap.parse_args()

    ip = args.index or index_path()
    if not ip.exists():
        sys.exit(f"LỖI: chưa có {ip}. Chạy trước: python scripts/build_index.py")
    if (args.quet or args.quet_cau_hoi) and args.tap != "dev":
        sys.exit("Quét tham số chỉ được chạy trên tập dev (--tap dev); các tập khác chỉ để xác nhận, không dùng để chỉnh.")
    try:
        bo = doc_bo(args.bo_cau_hoi, args.tap)
    except BoCauHoiError as e:
        sys.exit(f"LỖI: {e}")
    if args.chi_da_duyet:
        bo = [c for c in bo if c.get("trang_thai") == "da_duyet"]
    if not bo:
        sys.exit("LỖI: không có câu hỏi nào để chấm.")
    idx = open_index(ip)
    emb = NhoTam(HashEmbedder() if args.gia else tu_config(load_config(), model=args.model, endpoint=args.endpoint))

    if args.quet:
        return quet(idx, bo, emb, args.ngay)
    if args.quet_cau_hoi:
        return quet_cau_hoi(idx, bo, emb, args.ngay)
    ket_qua: dict[str, list] = {}
    try:
        for cd in args.che_do:
            ket_qua[cd] = [hang_dap_an(idx, c, emb, cd, args.ngay) for c in bo]
    except (EmbedError, ValueError) as e:
        sys.exit(f"LỖI: {e}")

    n = len(bo)
    dong = [f"Lưu ý: {w}" for w in sorted(CANH_BAO)]
    dong += [f"Bộ câu hỏi: {args.bo_cau_hoi.name}[{args.tap}] ({n} câu); mô hình {emb.name}", "",
            "| chế độ | " + " | ".join(f"Hit@{k}" for k in KS) + " | MRR |", "|---|" + "---|" * (len(KS) + 1)]
    for cd, kq in ket_qua.items():
        hit = [sum(1 for r, _ in kq if r and r <= k) / n for k in KS]
        mrr = sum(1 / r for r, _ in kq if r) / n
        dong.append(f"| {cd} | " + " | ".join(f"{h:.0%}" for h in hit) + f" | {mrr:.3f} |")
    dong += ["", "Hit@k = tỷ lệ câu mà Điều đáp án nằm trong k Điều đầu. MRR = trung bình 1/hạng của đáp án (1.0 là luôn đứng đầu)."]

    chinh = "hybrid" if "hybrid" in ket_qua else next(iter(ket_qua))
    sai = [(c, ket_qua[chinh][i]) for i, c in enumerate(bo) if not ket_qua[chinh][i][0] or ket_qua[chinh][i][0] > 3]
    dong += ["", f"## Các câu đáp án KHÔNG nằm trong top 3 ({chinh}): {len(sai)}/{n}", ""]
    for c, (r, top1) in sai:
        dong.append(f"- [{c['id']}] {c['cau_hoi']}  -> đáp án Điều {'/'.join(c['dieu'])}, hạng {r or '>300 đoạn'}; hạng 1 là: {top1}")
    if args.chi_tiet:
        dong += ["", "## Hạng từng câu", ""]
        for i, c in enumerate(bo):
            dong.append(f"- [{c['id']}] " + ", ".join(f"{cd}={ket_qua[cd][i][0] or '-'}" for cd in ket_qua) + f"  {c['cau_hoi']}")
    txt = "\n".join(dong)
    print(txt)
    if args.luu:
        args.luu.parent.mkdir(parents=True, exist_ok=True)
        args.luu.write_text(txt + "\n", encoding="utf-8")
        print(f"\nĐã ghi {args.luu}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
