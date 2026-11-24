"""Trình bày kết quả cho người đọc: Markdown của một Điều (khoản, điểm, ghi chú nguồn sửa đổi) và HTML so sánh hai bản.
Hàm thuần (không đụng CSDL), nên kiểm thử được độc lập. Giao diện Streamlit và CLI dùng chung.
"""
from __future__ import annotations

import difflib
import html
import re
from dataclasses import replace

from src.query.lookup import UnitView, fmt_date


def md_thoat(s: str) -> str:
    """Chữ luật vào Markdown: không để «$» thành công thức, «*»/«_» thành in nghiêng/đậm, «#»/«>» đầu dòng thành tiêu đề/trích dẫn."""
    s = s.replace("\\", "\\\\")
    for c in ("$", "*", "_", "`", "<", ">", "[", "]", "|"):
        s = s.replace(c, "\\" + c)
    return re.sub(r"^(\s*)([#+\-])", r"\1\\\2", s)


def ghi_chu_nguon(u: UnitView, nguon_cha: tuple[int, ...] = ()) -> str:
    """«sửa đổi bởi Luật số 12/2017/QH14 (Điều 1 khoản 3), hiệu lực từ 01/01/2018»; rỗng nếu nút không bị sửa hoặc cùng nguồn với nút cha."""
    ids = tuple(n.lenh_id for n in u.nguon)
    if not u.nguon or ids == nguon_cha:
        return ""
    return "; rồi ".join(n.mo_ta() for n in u.nguon)


def _ghi(note: str) -> str:
    return f" :gray[*({md_thoat(note)})*]" if note else ""


def _nut(u: UnitView, sau: int, ghi_chu: bool, nguon_cha: tuple[int, ...]) -> list[str]:
    """Các khối Markdown của khoản/điểm `u`. Khoản là đoạn riêng; điểm là gạch đầu dòng lồng nhau."""
    note = ghi_chu_nguon(u, nguon_cha) if ghi_chu else ""
    ids = tuple(n.lenh_id for n in u.nguon)
    if u.loai == "khoan":
        dau = f"**{md_thoat(u.ky_hieu)}.** {md_thoat(u.noi_dung)}{_ghi(note)}".rstrip()
        con = [x for c in u.children for x in _nut_lui(c, 0, ghi_chu, ids)]
        return [dau + ("\n\n" + "\n".join(con) if con else "")]
    return _nut_lui(u, sau, ghi_chu, nguon_cha)


def _nut_lui(u: UnitView, sau: int, ghi_chu: bool, nguon_cha: tuple[int, ...]) -> list[str]:
    note = ghi_chu_nguon(u, nguon_cha) if ghi_chu else ""
    ids = tuple(n.lenh_id for n in u.nguon)
    nhan = f"{md_thoat(u.ky_hieu)})" if u.loai == "diem" else f"{md_thoat(u.ky_hieu)}."
    ra = [f"{'  ' * sau}- {nhan} {md_thoat(u.noi_dung)}{_ghi(note)}".rstrip()]
    for c in u.children:
        ra += _nut_lui(c, sau + 1, ghi_chu, ids)
    return ra


def markdown_dieu(u: UnitView, *, ghi_chu: bool = True, tieu_de: bool = True) -> str:
    """Điều → Markdown: tiêu đề đậm, chữ riêng của Điều (nếu không chia khoản), từng khoản một đoạn, điểm là gạch đầu dòng.
    ghi_chu=True: sau nút đã bị sửa có dòng xám nhỏ nêu luật sửa đổi và ngày hiệu lực.
    tieu_de=False: bỏ dòng tiêu đề (nơi hiển thị đã có tiêu đề riêng, vd. thẻ Điều trong giao diện)."""
    ids = tuple(n.lenh_id for n in u.nguon)
    note = ghi_chu_nguon(u) if ghi_chu else ""
    khoi = [f"**Điều {md_thoat(u.ky_hieu)}. {md_thoat(u.tieu_de or '')}**".rstrip()] if tieu_de else []
    if u.noi_dung:
        khoi.append(md_thoat(u.noi_dung) + _ghi(note))
    elif note:
        if khoi:
            khoi[0] += _ghi(note)
        else:
            khoi.append(_ghi(note).strip())
    for c in u.children:
        khoi += _nut(c, 0, ghi_chu, ids)
    return "\n\n".join(khoi)


def loc_khoan(u: UnitView, khoan: str | None, diem: str | None) -> tuple[UnitView | None, str, str | None]:
    """Chỉ giữ khoản (và điểm) được hỏi. Trả (Điều đã lọc, mô tả phạm vi, lỗi). Không có khoản → (u, '', None)."""
    if not khoan:
        return u, "", None
    k = next((c for c in u.children if c.loai == "khoan" and c.ky_hieu == khoan), None)
    if k is None:
        return None, "", f"Điều {u.ky_hieu} không có khoản {khoan} tại ngày này."
    if diem:
        d = next((c for c in k.children if c.loai == "diem" and c.ky_hieu == diem), None)
        if d is None:
            return None, "", f"Khoản {khoan} Điều {u.ky_hieu} không có điểm {diem} tại ngày này."
        return replace(u, noi_dung="", children=[replace(k, children=[d])]), f"điểm {diem} khoản {khoan}", None
    return replace(u, noi_dung="", children=[k]), f"khoản {khoan}", None


def cua_so_hieu_luc(u: UnitView) -> tuple[str | None, str | None]:
    """Khoảng hiệu lực của CẢ bản đang hiển thị: từ lần thay đổi gần nhất của bất kỳ nút nào, đến lần thay đổi kế tiếp (None = còn hiệu lực)."""
    tus = [n.hieu_luc_tu for n in u.walk() if n.hieu_luc_tu]
    dens = [n.hieu_luc_den for n in u.walk() if n.hieu_luc_den]
    return (max(tus) if tus else None), (min(dens) if dens else None)


# ---------------------------------------------------------------------------------------------------------------------
# So sánh hai bản

_INS = "background:rgba(46,160,67,.30);text-decoration:none;border-radius:3px;padding:0 2px"
_DEL = "background:rgba(248,81,73,.30);text-decoration:line-through;border-radius:3px;padding:0 2px"
_TOKEN = re.compile(r"\s+|[^\s]+")


def _gop_dong(a: str, b: str) -> str | None:
    """Hai dòng thay thế nhau → MỘT dòng, chỗ bỏ có nền đỏ gạch ngang, chỗ thêm nền xanh, so từng từ. None nếu hai dòng quá khác nhau
    (xen kẽ từng từ sẽ khó đọc hơn là cho xem hai dòng riêng)."""
    if difflib.SequenceMatcher(None, a.split(), b.split(), autojunk=False).ratio() < 0.35:       # đo trên TỪ (khoảng trắng giống nhau không tính là giống)
        return None
    ta, tb = _TOKEN.findall(a), _TOKEN.findall(b)
    sm = difflib.SequenceMatcher(None, ta, tb, autojunk=False)
    doan: list[list] = []                                       # [đổi?, chữ ở bản cũ, chữ ở bản mới]
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        ca, cb = "".join(ta[i1:i2]), "".join(tb[j1:j2])
        if op == "equal":
            doan.append([False, ca, cb])
        elif doan and doan[-1][0]:
            doan[-1][1] += ca
            doan[-1][2] += cb
        else:
            doan.append([True, ca, cb])
    for k in range(1, len(doan) - 1):                           # đoạn «giống» chỉ là khoảng trắng kẹp giữa hai chỗ đổi → gộp (đọc «~~giảm nhẹ.~~ miễn trách nhiệm» liền mạch, không rời rạc từng từ)
        if not doan[k][0] and not doan[k][1].strip() and doan[k - 1][0] and doan[k + 1][0]:
            doan[k][0] = True
    gop: list[list] = []
    for d in doan:
        if gop and gop[-1][0] and d[0]:
            gop[-1][1] += d[1]
            gop[-1][2] += d[2]
        else:
            gop.append(d)
    ra = []
    for doi, ca, cb in gop:
        ca, cb = html.escape(ca), html.escape(cb)
        if not doi:
            ra.append(ca)
            continue
        if ca:
            ra.append(f'<span style="{_DEL}">{ca}</span>')
        if cb:
            ra.append(f'<span style="{_INS}">{cb}</span>')
    return "".join(ra)


def diff_html(a: str, b: str) -> tuple[str, int]:
    """So sánh hai văn bản theo dòng; dòng thay thế nhau thì so tiếp từng từ ngay trong dòng. Trả (HTML, số dòng khác nhau).
    Dòng giữ nguyên in thường; chỗ bị bỏ có nền đỏ nhạt gạch ngang, chỗ thêm có nền xanh nhạt. Màu là nền trong suốt nên đọc được ở cả
    giao diện sáng và tối."""
    la, lb = a.splitlines(), b.splitlines()
    sm = difflib.SequenceMatcher(None, la, lb, autojunk=False)
    ra: list[str] = []
    doi = 0
    p = 'style="margin:0 0 .45rem 0;line-height:1.55"'

    def dong(noi: str) -> str:
        return f"<p {p}>{noi}</p>"

    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == "equal":
            ra += [dong(html.escape(x)) for x in la[i1:i2]]
            continue
        doi += max(i2 - i1, j2 - j1)
        ca, cb = la[i1:i2], lb[j1:j2]
        for k in range(max(len(ca), len(cb))):
            gop = _gop_dong(ca[k], cb[k]) if k < len(ca) and k < len(cb) else None
            if gop is not None:
                ra.append(dong(gop))
                continue
            if k < len(ca):
                ra.append(dong(f'<span style="{_DEL}">{html.escape(ca[k])}</span>'))
            if k < len(cb):
                ra.append(dong(f'<span style="{_INS}">{html.escape(cb[k])}</span>'))
    return "\n".join(ra), doi


def ngay_vn(iso: str | None) -> str:
    return fmt_date(iso) if iso else "…"
