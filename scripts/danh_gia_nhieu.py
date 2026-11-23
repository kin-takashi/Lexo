"""Đo «tìm đủ» cho các tình huống nhiều Điều (loai = nhieu_dieu trong eval/bo_cau_hoi.json).

  python scripts/danh_gia_nhieu.py                          # mốc «không tách»: cả tình huống là MỘT truy vấn, tập dev
  python scripts/danh_gia_nhieu.py --chi-tiet               # liệt kê Điều còn thiếu của từng tình huống
  python scripts/danh_gia_nhieu.py --du-doan tach_dev.json  # so với bản đã tách hành vi (file do bước tách tạo ra)
  python scripts/danh_gia_nhieu.py --chi-id dn01-dn14       # chỉ một phần tập dev (khoảng id hoặc danh sách cách nhau dấu phẩy)
  python scripts/danh_gia_nhieu.py --tap kiem_tra           # tập đóng băng: chỉ chạy với lời nhắc / tham số ĐÃ CHỐT
  python scripts/danh_gia_nhieu.py --gia                    # vector giả, chỉ thử đường ống

File --du-doan là JSON {"dn01": ["mô tả hành vi 1", "mô tả hành vi 2"], ...}: mỗi hành vi được tìm riêng, lấy m Điều đầu (--m, mặc định 3).
Số đo xem src/index/tim_du.py. Kết quả được so với mốc «không tách» ở CÙNG số Điều hiển thị, để không thắng chỉ vì hiển thị nhiều hơn.
Không có tham số nào để quét ở đây: chọn lời nhắc tách bằng tập dev, rồi chạy tập kiểm tra đúng một lần cho số báo cáo cuối.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import index_path, load_config  # noqa: E402
from src.index.bo_cau_hoi import MAC_DINH, TAP, TAP_DONG_BANG, BoCauHoiError, doc_bo, loc_theo_id  # noqa: E402
from src.index.embedder import EmbedError, HashEmbedder, tu_config  # noqa: E402
from src.index.search import CHE_DO, MAC_DINH as CHE_DO_MAC_DINH, gop_theo_dieu, tim  # noqa: E402
from src.index.store import open_index  # noqa: E402
from src.index.tim_du import cham, so_dieu, so_ngan_sach, tong_hop  # noqa: E402

KS_MOC = (3, 6, 9)


class NhoTam:
    """Bọc embedder: cùng một đoạn chữ chỉ nhúng một lần."""

    def __init__(self, emb):
        self.emb, self.name, self.cache = emb, emb.name, {}

    def embed(self, texts):
        out = []
        for t in texts:
            if t not in self.cache:
                self.cache[t] = self.emb.embed([t])[0]
            out.append(self.cache[t])
        return out


def xep_hang(idx, emb, chu: str, che_do: str, ngay: str | None) -> list[str]:
    """Danh sách số Điều xếp hạng giảm dần cho một đoạn chữ."""
    kq = tim(idx, chu, embedder=emb, ngay=ngay, k=2000, che_do=che_do, n_ung_vien=300)
    return [so_dieu(d.dieu) for d in gop_theo_dieu(kq.hits, 10_000)]


def doc_du_doan(duong_dan: Path, bo: list[dict]) -> dict[str, list[str]]:
    try:
        d = json.loads(duong_dan.read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        raise SystemExit(f"LỖI: không đọc được {duong_dan}: {e}")
    if not isinstance(d, dict) or not all(isinstance(v, list) and v and all(isinstance(s, str) and s.strip() for s in v) for v in d.values()):
        raise SystemExit('LỖI: file --du-doan phải là {"id": ["mô tả hành vi", ...], ...}, mỗi id có ít nhất một hành vi không rỗng')
    thieu = [c["id"] for c in bo if c["id"] not in d]
    if thieu:
        raise SystemExit(f"LỖI: --du-doan thiếu {len(thieu)} id: {', '.join(thieu[:8])}{'...' if len(thieu) > 8 else ''}")
    return d


def dong_bang(ten: str, tb: dict, co_hanh_vi: bool = True) -> str:
    """Một dòng của bảng. Mốc «không tách» không có hành vi riêng nên hai cột về hành vi để «–»."""
    hv = (f"{tb['hanh_vi_co_dap_an']:.0%} | {tb['dung_so_hanh_vi']:.0%}" if co_hanh_vi else "– | –")
    return f"| {ten} | {tb['tim_du']:.0%} | {tb['bao_phu']:.0%} | {tb['chinh_xac']:.0%} | {hv} | {tb['so_hien_thi']:.1f} |"


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bo-cau-hoi", type=Path, default=MAC_DINH)
    ap.add_argument("--tap", choices=(*TAP, "tat_ca"), default="dev", help="tập có câu nhieu_dieu để chấm (mặc định dev)")
    ap.add_argument("--du-doan", type=Path, default=None, help="JSON {id: [mô tả hành vi, ...]} do bước tách tạo ra")
    ap.add_argument("--m", type=int, default=3, help="số Điều hiển thị cho mỗi hành vi (mặc định 3)")
    ap.add_argument("--che-do", choices=CHE_DO, default=CHE_DO_MAC_DINH)
    ap.add_argument("--ngay", default=None)
    ap.add_argument("--index", type=Path, default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--endpoint", default=None)
    ap.add_argument("--gia", action="store_true")
    ap.add_argument("--chi-da-duyet", action="store_true")
    ap.add_argument("--chi-id", default=None, help="chỉ chấm các id này: cách nhau dấu phẩy, cho phép khoảng như dn01-dn14 (tách báo cáo bộ cũ / bộ mới)")
    ap.add_argument("--chi-tiet", action="store_true")
    ap.add_argument("--luu", type=Path, default=None, help="ghi báo cáo markdown")
    args = ap.parse_args()
    if args.m < 1:
        sys.exit("LỖI: --m phải >= 1")

    ip = args.index or index_path()
    if not ip.exists():
        sys.exit(f"LỖI: chưa có {ip}. Chạy trước: python scripts/build_index.py")
    try:
        bo = doc_bo(args.bo_cau_hoi, args.tap, "nhieu_dieu")
    except BoCauHoiError as e:
        sys.exit(f"LỖI: {e}")
    if args.chi_da_duyet:
        bo = [c for c in bo if c.get("trang_thai") == "da_duyet"]
    if args.chi_id:
        try:
            bo = loc_theo_id(bo, args.chi_id)
        except BoCauHoiError as e:
            sys.exit(f"LỖI: {e}")
    if not bo:
        sys.exit("LỖI: không có tình huống nhiều Điều nào để chấm.")
    du_doan = doc_du_doan(args.du_doan, bo) if args.du_doan else None

    idx = open_index(ip)
    emb = NhoTam(HashEmbedder() if args.gia else tu_config(load_config(), model=args.model, endpoint=args.endpoint))
    try:
        xh_ca_cau = [xep_hang(idx, emb, c["cau_hoi"], args.che_do, args.ngay) for c in bo]
        xh_hanh_vi = [[xep_hang(idx, emb, hv, args.che_do, args.ngay) for hv in du_doan[c["id"]]] for c in bo] if du_doan else None
    except (EmbedError, ValueError) as e:
        sys.exit(f"LỖI: {e}")

    bang: list[tuple[str, dict, bool]] = []
    for k in KS_MOC:
        bang.append((f"không tách, hiển thị {k} Điều", tong_hop([so_ngan_sach(c["dieu"], xh, k) for c, xh in zip(bo, xh_ca_cau)]), False))
    chi_tiet: list[tuple[dict, dict, dict | None]] = []
    if xh_hanh_vi is not None:
        tach = [cham(c["dieu"], hv, args.m) for c, hv in zip(bo, xh_hanh_vi)]
        cung = [so_ngan_sach(c["dieu"], xh, t["so_hien_thi"]) for c, xh, t in zip(bo, xh_ca_cau, tach)]
        bang.append(("không tách, cùng số Điều hiển thị với bản tách", tong_hop(cung), False))
        bang.append((f"TÁCH hành vi, mỗi hành vi {args.m} Điều", tong_hop(tach), True))
        chi_tiet = list(zip(bo, tach, cung))
    else:
        chi_tiet = [(c, so_ngan_sach(c["dieu"], xh, KS_MOC[0]), None) for c, xh in zip(bo, xh_ca_cau)]

    n = len(bo)
    co_dong_bang = args.tap in TAP_DONG_BANG or args.tap == "tat_ca"
    dong = [f"Tình huống nhiều Điều: {args.bo_cau_hoi.name}[{args.tap}] ({n} tình huống, TB {sum(len(c['dieu']) for c in bo) / n:.1f} Điều đáp án); "
             f"chế độ {args.che_do}; mô hình {emb.name}", ""]
    if co_dong_bang:
        dong += ["CHÚ Ý: tập này đóng băng — chỉ chạy với lời nhắc/tham số đã chốt; không chỉnh theo kết quả này.", ""]
    dong += ["| cách | tìm đủ | bao phủ | chính xác | hành vi có đáp án | đúng số hành vi | Điều hiển thị |", "|---|---|---|---|---|---|---|"]
    dong += [dong_bang(t, tb, co) for t, tb, co in bang]
    dong += ["",
             "tìm đủ = mọi Điều đáp án đều được hiển thị (số đo chính). bao phủ = phần Điều đáp án được hiển thị. chính xác = phần Điều hiển thị là đáp án. "
             "hành vi có đáp án = phần hành vi có ít nhất một Điều đáp án trong m Điều đầu (đo tách thừa). đúng số hành vi = số hành vi tách ra bằng số Điều đáp án. "
             "Mốc «không tách» không có hành vi riêng nên hai cột đó để «–»."]
    sai = [(c, t) for c, t, _ in chi_tiet if t["thieu"]]
    dong += ["", f"## Tình huống còn thiếu Điều ({'bản tách' if du_doan else 'không tách, hiển thị ' + str(KS_MOC[0])}): {len(sai)}/{n}", ""]
    if args.chi_tiet or len(sai) <= 12:
        for c, t in sai:
            dong.append(f"- [{c['id']}] đáp án {'/'.join(c['dieu'])}, thiếu {'/'.join(t['thieu'])}: {c['cau_hoi'][:90]}")
    else:
        dong.append(f"(quá {12} tình huống; thêm --chi-tiet để xem)")
    txt = "\n".join(dong)
    print(txt)
    if args.luu:
        args.luu.parent.mkdir(parents=True, exist_ok=True)
        args.luu.write_text(txt + "\n", encoding="utf-8")
        print(f"\nĐã ghi {args.luu}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
