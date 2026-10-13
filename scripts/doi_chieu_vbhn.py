"""Bước 3: đối chiếu bản hệ thống dựng với VĂN BẢN HỢP NHẤT chính thức, rồi hiệu đính có bằng chứng (người duyệt từng đợt).

  trich      <thư_mục_raw> ... [--mau "*.pdf"] [--ra vbhn.json]
                                    PDF Công báo trong raw/<thư_mục>/ -> raw/<thư_mục>/vbhn.json (cần pdfplumber; chậm ~1 phút/bộ)
  so-sanh    [--vbhn 135-VBHN-VPQH] [--ngay YYYY-MM-DD] [--bao-cao FILE.md] [--xem-truoc]
                                    so từng nút Phần/Chương/Mục/Điều/Khoản/Điểm; KHÔNG đổi CSDL
  de-xuat    [--xem-truoc]           lập đề xuất hiệu đính (chờ duyệt) vào CSDL và raw/<dich>/hieu_dinh.json; từ chối nếu còn lệnh sửa đổi chưa duyệt
                                    (so với văn bản hợp nhất thì bản hệ thống phải đã gồm các luật sửa đổi), trừ khi --xem-truoc
  danh-sach  [--trang-thai ...]      liệt kê đề xuất kèm bằng chứng
  duyet      --nguoi TEN [--id N ...] [--loai loi_go ...] [--tu-choi] [--ghi-chu ...] [--ap-dung]
                                    duyệt (hoặc từ chối) đề xuất; --ap-dung dựng lại phiên bản ngay
  nap                                nạp quyết định từ raw/<dich>/hieu_dinh.json vào CSDL mới (sau init_db --reset)

Quy trình:  trich -> so-sanh (xem số liệu) -> de-xuat -> danh-sach (đọc) -> duyet --nguoi TEN --ap-dung -> so-sanh (khớp sau hiệu đính)
Hiệu đính chỉ sửa chữ có bằng chứng; con số/từ pháp lý bị đổi vẫn do NGƯỜI duyệt quyết định (loại sai_so_lieu hiển thị riêng).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.apply import hieu_dinh as hd  # noqa: E402
from src.apply.rebuild import RebuildError, preview, rebuild  # noqa: E402
from src.config import db_path, raw_dir  # noqa: E402
from src.query.lookup import so_lenh_cho_duyet  # noqa: E402
from src.store import connect  # noqa: E402
from src.validate.vbhn import compare, items_from_db, lap_de_xuat, nap_vbhn_json  # noqa: E402

VBHN_CHINH = "135-VBHN-VPQH"
# (nhãn, đường dẫn trong raw/): các bản dùng làm bằng chứng đồng thuận cho đề xuất
THAM_CHIEU = [
    ("135/VBHN-VPQH", "135-VBHN-VPQH/vbhn.json"),
    ("01/VBHN-VPQH", "01-VBHN-VPQH/vbhn.json"),
    ("11/VBHN-VPQH", "11-VBHN-VPQH/vbhn.json"),
    ("100/2015/QH13 (Công báo 1263-1270, bản gốc)", "100-2015-QH13/congbao/cb.json"),
]
MOC_LICH_SU = ("01-VBHN-VPQH", "2018-01-01")      # VBHN 01 hợp nhất BLHS + Luật 12/2017 (có hiệu lực 2018-01-01)


def _nhan_cua(slug: str) -> str:
    return next((n for n, rel in THAM_CHIEU if rel.startswith(slug + "/")), slug)


def _tham_chieu(tru: str | None = None) -> dict:
    out = {}
    for nhan, rel in THAM_CHIEU:
        if tru and rel.startswith(tru + "/"):
            continue
        p = raw_dir() / rel
        if p.exists():
            out[nhan] = nap_vbhn_json(p)[0]
    return out


def _xac_minh(dich_slug: str) -> dict[str, list[dict]]:
    p = raw_dir() / dich_slug / "xac_minh_nguon.json"
    if not p.exists():
        return {}
    out: dict[str, list[dict]] = {}
    for m in json.loads(p.read_text(encoding="utf-8")).get("muc", []):
        out.setdefault(m["khoa"], []).append({k: v for k, v in m.items() if k != "khoa"})
    return out


def _slug(so_hieu: str) -> str:
    return so_hieu.replace("/", "-")


def _cut(s: str, n: int = 90) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1] + "…"


def cmd_trich(args) -> int:
    from src.ingest.vbhn_pdf import extract_vbhn

    for slug in args.thu_muc:
        d = raw_dir() / slug
        pdfs = sorted(d.glob(args.mau))
        if not pdfs:
            print(f"Không có PDF nào ({args.mau}) trong {d}", file=sys.stderr)
            return 2
        v = extract_vbhn(pdfs)
        out = d / args.ra
        out.write_text(json.dumps(v.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"{slug}: {len(pdfs)} PDF -> {len(v.lines)} đoạn, {len(v.footnotes)} chú thích -> {out}")
    return 0


def _so_sanh(conn, vb: int, slug: str, ngay: str):
    p = raw_dir() / slug / "vbhn.json"
    if not p.exists():
        raise FileNotFoundError(f"Chưa có {p}. Chạy: python scripts/doi_chieu_vbhn.py trich {slug}")
    theirs, rep = nap_vbhn_json(p)
    return compare(items_from_db(conn, vb, ngay), theirs, rep)


def _tom_tat(res, nhan: str, ngay: str) -> list[str]:
    ok_dieu = len(res.dieu_with_diffs())
    kinds = {k: v for k, v in res.by_kind().items()}
    return [
        f"Đối chiếu với {nhan}, bản hệ thống tại ngày {ngay}:",
        f"  số nút: hệ thống {res.n_ours}, văn bản hợp nhất {res.n_theirs} (trong đó {len(res.repealed_theirs)} nút ghi \"được bãi bỏ\" coi là không có)",
        f"  giống hệt từng chữ: {res.n_match} ({res.n_match_pct:.2%})",
        f"  giống hệt hoặc chỉ khác trình bày (viết hoa, oá/óa, sỹ/sĩ, dấu câu, khoảng trắng): {res.n_match_fold} ({res.n_khop_chuan_hoa_pct:.2%})",
        f"  sai khác nội dung: {sum(v for k, v in kinds.items() if k != 'khac_trinh_bay')} chỗ ở {ok_dieu} Điều; "
        + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items())),
    ]


def _cho_duyet_canh_bao(conn, vb) -> str | None:
    n = so_lenh_cho_duyet(conn, vb)
    if not n:
        return None
    return (f"Lưu ý: còn {n} lệnh sửa đổi CHƯA được duyệt nên bản hệ thống chưa gồm các luật sửa đổi đó, số liệu dưới đây sẽ lệch nhiều. "
            "Duyệt và áp dụng lệnh trước (scripts/apply_commands.py duyet ... ; ap-dung ...), hoặc thêm --xem-truoc để so trên bản chạy thử.")


def cmd_so_sanh(args, conn, vb, dich_slug) -> int:
    slug = args.vbhn
    ngay = args.ngay or (date.today().isoformat() if slug == VBHN_CHINH else MOC_LICH_SU[1])
    if args.xem_truoc:
        _rep, conn = preview(conn, vb)                      # bản sao trong bộ nhớ: gồm lệnh và hiệu đính chưa duyệt
        print("(so trên BẢN CHẠY THỬ: gồm cả lệnh sửa đổi và đề xuất hiệu đính chưa được duyệt)")
    elif (w := _cho_duyet_canh_bao(conn, vb)):
        print(w)
    res = _so_sanh(conn, vb, slug, ngay)
    print("\n".join(_tom_tat(res, _nhan_cua(slug), ngay)))
    n_content = [d for d in res.diffs if d.kind != "khac_trinh_bay"]
    for d in n_content[: args.hien]:
        print(f"  {d.kind:14s} {d.key}: {_cut(d.note or (d.ours + ' | ' + d.theirs), 120)}")
    if len(n_content) > args.hien:
        print(f"  … còn {len(n_content) - args.hien} chỗ (dùng --bao-cao FILE để xem đủ)")
    if args.bao_cao:
        lines = ["# " + _tom_tat(res, _nhan_cua(slug), ngay)[0], ""] + ["- " + x.strip() for x in _tom_tat(res, _nhan_cua(slug), ngay)[1:]] + [""]
        for kind in ("khac_noi_dung", "khac_tieu_de", "thieu_o_ta", "thua_o_ta", "khac_vi_tri", "khac_trinh_bay"):
            ds = [d for d in res.diffs if d.kind == kind]
            if not ds:
                continue
            lines += [f"## {kind} ({len(ds)})", ""]
            for d in ds:
                lines.append(f"- `{d.key}`: {_cut(d.note or (d.ours + ' → ' + d.theirs), 400)}")
            lines.append("")
        args.bao_cao.parent.mkdir(parents=True, exist_ok=True)
        args.bao_cao.write_text("\n".join(lines), encoding="utf-8")
        print(f"Đã ghi {args.bao_cao}")
    return 0


def _luu_json(conn, vb, dich_slug) -> Path:
    out = raw_dir() / dich_slug / "hieu_dinh.json"
    out.write_text(json.dumps({"van_ban": dich_slug, "quy_tac": hd.xuat(conn, vb)}, ensure_ascii=False, indent=1), encoding="utf-8")
    return out


def cmd_de_xuat(args, conn, vb, dich_slug) -> int:
    ngay = args.ngay or date.today().isoformat()
    xm = _xac_minh(dich_slug)
    goc = conn                                              # nơi ghi đề xuất; so sánh có thể chạy trên bản chạy thử
    cho = so_lenh_cho_duyet(conn, vb)
    if cho and not args.xem_truoc:
        print(f"LỖI: còn {cho} lệnh sửa đổi CHƯA được duyệt nên bản hệ thống chưa đủ các luật sửa đổi; lập đề xuất lúc này sẽ cho kết quả sai.\n"
              "Duyệt và áp dụng lệnh trước (scripts/apply_commands.py duyet ... ; ap-dung ...), hoặc thêm --xem-truoc để lập đề xuất trên bản chạy thử "
              "(đề xuất vẫn ở trạng thái CHỜ DUYỆT).", file=sys.stderr)
        return 2
    if args.xem_truoc:
        _rep, conn = preview(conn, vb, hieu_dinh=hd.DA_DUYET)       # chỉ áp hiệu đính đã duyệt, để đề xuất chờ duyệt không che nhau
    # A: bản hiện hành so với VBHN mới nhất (đề xuất khi có bản tham chiếu khác đồng thuận hoặc đã xác minh nguồn)
    theirs_a, rep_a = nap_vbhn_json(raw_dir() / VBHN_CHINH / "vbhn.json")
    ours_a = items_from_db(conn, vb, ngay)
    da, khong_a = lap_de_xuat(ours_a, theirs_a, _tham_chieu(VBHN_CHINH), xm, nhan_nguon=f"{_nhan_cua(VBHN_CHINH)} (bản hệ thống ngày {ngay})")
    # B: mốc lịch sử (BLHS + Luật 12/2017) so với VBHN 01; cùng điều kiện bằng chứng như A
    de_xuat, khong = list(da), list(khong_a)
    slug_b, ngay_b = MOC_LICH_SU
    if (raw_dir() / slug_b / "vbhn.json").exists():
        theirs_b, _ = nap_vbhn_json(raw_dir() / slug_b / "vbhn.json")
        db_, kb = lap_de_xuat(items_from_db(conn, vb, ngay_b), theirs_b, _tham_chieu(slug_b), xm,
                              nhan_nguon=f"{_nhan_cua(slug_b)} (bản hệ thống ngày {ngay_b})")
        seen = {(d["khoa"], d["truong"], d["tu_cu"], d["thanh_moi"]) for d in de_xuat}
        de_xuat += [d for d in db_ if (d["khoa"], d["truong"], d["tu_cu"], d["thanh_moi"]) not in seen]
        khong += kb
    if conn is not goc:
        conn.close()
        conn = goc
    with conn:
        moi, co = hd.luu_de_xuat(conn, vb, de_xuat)
    out = _luu_json(conn, vb, dich_slug)
    by = {}
    for d in de_xuat:
        by[d["loai"]] = by.get(d["loai"], 0) + 1
    print(f"Đề xuất hiệu đính: {len(de_xuat)} (mới {moi}, đã có {co}); theo loại: " + ", ".join(f"{k} {v}" for k, v in sorted(by.items())))
    if khong:
        print(f"Không đề xuất {len(khong)} nút (thiếu bằng chứng hoặc không sửa tự động được) — xem bằng so-sanh:")
        for k in khong[: args.hien]:
            print(f"  {k['ly_do']:16s} {k['khoa']} [{k['truong']}]")
    print(f"Đã ghi {out}. Đọc: python scripts/doi_chieu_vbhn.py danh-sach ; duyệt: ... duyet --nguoi TEN --ap-dung")
    return 0


def cmd_danh_sach(args, conn, vb, dich_slug) -> int:
    q = "SELECT * FROM hieu_dinh WHERE van_ban_id = ?"
    a: list = [vb]
    if args.trang_thai:
        q += f" AND trang_thai_duyet IN ({','.join('?' * len(args.trang_thai))})"
        a += args.trang_thai
    rows = conn.execute(q + " ORDER BY id", a).fetchall()
    if not rows:
        print("Chưa có đề xuất nào (chạy de-xuat).")
        return 0
    for r in rows:
        bc = json.loads(r["bang_chung_json"])
        tc = bc.get("tham_chieu", {})
        nhom = {"cung_sua": [], "giong_ban_he_thong": [], "khac": []}
        for k, v in tc.items():
            if v in nhom:
                nhom[v].append(k)
        print(f"#{r['id']:<3d} [{r['trang_thai_duyet']}] {r['loai']:11s} {r['khoa']} ({r['truong']})")
        print(f"      “{r['tu_cu']}” → “{r['thanh_moi']}”")
        if r["trang_thai_duyet"] != "cho_duyet":
            print(f"      {r['trang_thai_duyet']} bởi {r['nguoi_duyet']} ngày {r['ngay_duyet']}" + (f" — {r['ghi_chu_duyet']}" if r["ghi_chu_duyet"] else ""))
        for nhan, ten in (("cung_sua", "viết như văn bản hợp nhất (đồng thuận)"), ("giong_ban_he_thong", "giống bản hệ thống"),
                          ("khac", "khác cả hai (thường do luật sửa đổi ở giữa)")):
            if nhom[nhan]:
                print(f"      {ten}: {', '.join(nhom[nhan])}")
        for x in bc.get("xac_minh", []):
            print(f"      đã kiểm nguồn: {x['nguon']}")
    print(f"Tổng {len(rows)}.")
    return 0


def cmd_duyet(args, conn, vb, dich_slug) -> int:
    n = hd.duyet(conn, vb, nguoi=args.nguoi, ids=args.id, loai=args.loai, tu_choi=args.tu_choi, ghi_chu=args.ghi_chu)
    out = _luu_json(conn, vb, dich_slug)
    print(f"Đã {'từ chối' if args.tu_choi else 'duyệt'} {n} đề xuất (người duyệt: {args.nguoi}). Quyết định lưu ở {out}.")
    if args.ap_dung:
        rep = rebuild(conn, vb)
        _in_hieu_dinh(rep.hieu_dinh)
    else:
        print("Chạy 'python scripts/apply_commands.py ap-dung 100/2015/QH13' (hoặc thêm --ap-dung) để dựng lại phiên bản.")
    return 0


def _in_hieu_dinh(bao) -> None:
    print(f"Hiệu đính: {bao.n_ap}/{len(bao.ket_qua)} quy tắc đã áp.")
    for r in bao.khong_ap_duoc():
        print(f"  ! #{r.id} {r.khoa}: không áp được ({'không có nút' if not r.co_nut else 'không còn chỗ nào chứa từ cũ — có thể luật sửa đổi mới đã thay đoạn này'})")
    for r in bao.ket_qua:
        if r.n_mo_ho:
            print(f"  ! #{r.id} {r.khoa}: {r.n_mo_ho} phiên bản có từ cũ xuất hiện nhiều chỗ, bỏ qua")


def cmd_nap(args, conn, vb, dich_slug) -> int:
    p = raw_dir() / dich_slug / "hieu_dinh.json"
    if not p.exists():
        print(f"Không có {p}", file=sys.stderr)
        return 2
    with conn:
        them, cap = hd.nap(conn, vb, json.loads(p.read_text(encoding="utf-8"))["quy_tac"])
    print(f"Đã nạp từ {p}: thêm {them}, cập nhật quyết định {cap}. Chạy ap-dung để áp.")
    return 0


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--db", type=Path, default=None)
    common.add_argument("--dich", default="100/2015/QH13", help="số hiệu văn bản gốc (mặc định BLHS 2015)")
    common.add_argument("--hien", type=int, default=30, help="số dòng tối đa in ra")
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("trich", parents=[common])
    s.add_argument("thu_muc", nargs="+")
    s.add_argument("--mau", default="*.pdf", help="mẫu tên file PDF lấy trong thư mục (mặc định *.pdf)")
    s.add_argument("--ra", default="vbhn.json", help="tên file kết quả trong thư mục đó (mặc định vbhn.json)")
    s = sub.add_parser("so-sanh", parents=[common])
    s.add_argument("--vbhn", default=VBHN_CHINH, help="thư mục trong raw/ của văn bản hợp nhất (đã trich)")
    s.add_argument("--ngay", default=None, help="ngày của bản hệ thống cần so (mặc định: hôm nay với VBHN mới nhất, 2018-01-01 với VBHN 01)")
    s.add_argument("--bao-cao", type=Path, default=None)
    s.add_argument("--xem-truoc", action="store_true", help="so trên bản chạy thử (gồm cả lệnh và hiệu đính chưa duyệt)")
    s = sub.add_parser("de-xuat", parents=[common])
    s.add_argument("--ngay", default=None)
    s.add_argument("--xem-truoc", action="store_true", help="lập đề xuất trên bản chạy thử khi còn lệnh sửa đổi chưa duyệt (đề xuất vẫn chờ duyệt)")
    s = sub.add_parser("danh-sach", parents=[common])
    s.add_argument("--trang-thai", nargs="*", choices=("cho_duyet", "da_duyet", "tu_choi"))
    s = sub.add_parser("duyet", parents=[common])
    s.add_argument("--nguoi", required=True)
    s.add_argument("--id", type=int, nargs="*")
    s.add_argument("--loai", nargs="*", choices=hd.LOAI)
    s.add_argument("--tu-choi", action="store_true")
    s.add_argument("--ghi-chu", default=None)
    s.add_argument("--ap-dung", action="store_true")
    sub.add_parser("nap", parents=[common])
    args = ap.parse_args()
    if args.cmd == "trich":
        return cmd_trich(args)
    path = args.db or db_path()
    if not path.exists():
        print(f"Chưa có CSDL {path}.", file=sys.stderr)
        return 2
    conn = connect(path)
    try:
        row = conn.execute("SELECT id FROM van_ban WHERE so_hieu = ?", (args.dich,)).fetchone()
        if row is None:
            print(f"Không có văn bản {args.dich} trong CSDL.", file=sys.stderr)
            return 2
        fn = {"so-sanh": cmd_so_sanh, "de-xuat": cmd_de_xuat, "danh-sach": cmd_danh_sach, "duyet": cmd_duyet, "nap": cmd_nap}[args.cmd]
        return fn(args, conn, row["id"], _slug(args.dich))
    except (hd.HieuDinhError, RebuildError, FileNotFoundError) as e:
        print(f"LỖI: {e}", file=sys.stderr)
        return 2
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
