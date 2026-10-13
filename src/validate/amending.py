"""Validator tự động cho luật sửa đổi đã parse (amending.json) — chạy trước khi trích lệnh.

Kiểm tra cấu trúc: mọi dòng của Điều sửa đổi đều có chủ; khối trích dẫn đều gắn với một mục; mục cuối cùng
("như sau:") có khối trích dẫn; số thứ tự mục liên tục; ngày ban hành / hiệu lực đọc được và hợp lý.
Không phán đoán nội dung pháp lý.
"""
from __future__ import annotations

from collections import Counter

from src.parse.amending import PHAM_VI_KHONG_RO, PHAM_VI_TRONG, AmendingLaw, DieuSuaDoi, Item
from src.parse.model import VN_LETTERS
from src.validate.base_law import CANH_BAO, LOI, THONG_TIN, Flag


def _check_numbering(d: DieuSuaDoi, flags: list[Flag]) -> None:
    exp = 1
    for it in d.items:
        try:
            got = int(it.ky_hieu)
        except ValueError:
            flags.append(Flag(LOI, "Muc_ky_hieu", f"Điều {d.ky_hieu}: mục '{it.ky_hieu}' không phải số", it.line_start))
            continue
        if got != exp:
            flags.append(Flag(LOI, "Muc_nhay_so", f"Điều {d.ky_hieu}: sau mục {exp - 1} là mục {got} (mong đợi {exp})", it.line_start))
        exp = got + 1
        letters = [c.ky_hieu for c in it.children]
        want = list(VN_LETTERS[: len(letters)])
        if letters != want:
            flags.append(Flag(LOI, "Diem_nhay_chu", f"Điều {d.ky_hieu} khoản {it.ky_hieu}: các điểm {letters} không liên tục "
                                                     f"(mong đợi {want})", it.line_start))


def _check_item(d: DieuSuaDoi, it: Item, flags: list[Flag]) -> None:
    leaf = not it.children
    ends_colon = it.text.rstrip().endswith(":")
    if it.pham_vi == PHAM_VI_KHONG_RO:
        flags.append(Flag(CANH_BAO, "Dich_khong_ro", f"{it.vi_tri_nguon}: không xác định được văn bản đích ({it.text[:70]!r})", it.line_start))
    if it.pham_vi != PHAM_VI_TRONG:
        return                                            # ngoài phạm vi: chỉ cần biết là ngoài phạm vi
    if leaf and ends_colon and not it.quote_ids:
        flags.append(Flag(LOI, "Thieu_khoi_trich_dan", f"{it.vi_tri_nguon}: kết thúc bằng ':' nhưng không có khối trích dẫn", it.line_start))
    if it.quote_ids and not leaf:
        flags.append(Flag(CANH_BAO, "Khoi_o_muc_cha", f"{it.vi_tri_nguon}: có khối trích dẫn dù còn mục con", it.line_start))
    if leaf and not ends_colon and not it.quote_ids and "\n" in it.text:
        flags.append(Flag(CANH_BAO, "Lenh_nhieu_dong", f"{it.vi_tri_nguon}: lệnh gồm nhiều dòng, kiểm tra nguyên văn", it.line_start))


def validate_amending_law(law: AmendingLaw) -> list[Flag]:
    flags: list[Flag] = []
    m = law.meta
    if not m.so_hieu:
        flags.append(Flag(LOI, "Thieu_so_hieu", "Không đọc được số hiệu"))
    if not m.ngay_ban_hanh:
        flags.append(Flag(LOI, "Thieu_ngay_ban_hanh", "Không đọc được ngày thông qua ở câu chốt"))
    if not m.ngay_hieu_luc:
        flags.append(Flag(LOI, "Thieu_ngay_hieu_luc", "Không đọc được ngày hiệu lực trong Điều hiệu lực thi hành"))
    if m.ngay_ban_hanh and m.ngay_hieu_luc and m.ngay_hieu_luc < m.ngay_ban_hanh:
        flags.append(Flag(LOI, "Hieu_luc_truoc_ban_hanh", f"Hiệu lực {m.ngay_hieu_luc} trước ngày thông qua {m.ngay_ban_hanh}"))
    if m.ngay_header and m.ngay_ban_hanh and m.ngay_header != m.ngay_ban_hanh:
        flags.append(Flag(CANH_BAO, "Ngay_header_khac", f"Ngày ở đầu văn bản {m.ngay_header} khác ngày thông qua {m.ngay_ban_hanh}"))
    if m.hieu_luc_ngoai_le:
        for x in m.hieu_luc_ngoai_le:
            flags.append(Flag(CANH_BAO, "Hieu_luc_ngoai_le", f"Có ngày hiệu lực khác trong Điều hiệu lực: {x['ngay']} — {x['cau'][:90]}"))
    if not law.dieu_sua_doi:
        flags.append(Flag(LOI, "Khong_co_dieu_sua_doi", "Không tìm thấy Điều sửa đổi nào"))
    if not law.footer:
        flags.append(Flag(CANH_BAO, "Thieu_cau_chot", "Không thấy câu chốt 'Luật này đã được Quốc hội ... thông qua'"))
    if not law.dieu_hieu_luc:
        flags.append(Flag(CANH_BAO, "Thieu_dieu_hieu_luc", "Không thấy Điều hiệu lực thi hành"))
    for w in law.warnings:
        flags.append(Flag(CANH_BAO, "Parser", w))

    owned: set[int] = set()
    q_owned: Counter[str] = Counter()
    for d in law.dieu_sua_doi:
        owned.add(d.line_start)
        _check_numbering(d, flags)
        for it in d.walk_items():
            owned.update(range(it.line_start, it.line_end + 1))
            for qid in it.quote_ids:
                q_owned[qid] += 1
            _check_item(d, it, flags)
        for qid in d.quotes_mo_coi:
            flags.append(Flag(LOI, "Khoi_mo_coi", f"Điều {d.ky_hieu}: khối trích dẫn {qid} không gắn với mục nào"))
    for q in law.quotes:
        if q_owned[q.id] > 1:
            flags.append(Flag(LOI, "Khoi_trung", f"Khối {q.id} gắn với {q_owned[q.id]} mục"))
        if not q.text.strip():
            flags.append(Flag(LOI, "Khoi_rong", f"Khối {q.id} rỗng", q.line_start))
    for d in law.dieu_sua_doi:
        for i in range(d.line_start, d.line_end):
            if i not in owned:
                flags.append(Flag(LOI, "Dong_khong_chu", f"Điều {d.ky_hieu}: dòng {i} không thuộc mục hoặc khối nào: {law.lines[i][:60]!r}", i))

    c = Counter(it.pham_vi for _, it in law.iter_items())
    flags.append(Flag(THONG_TIN, "Tong_ket", f"{sum(1 for _ in law.iter_items())} mục lệnh (trong phạm vi {c['trong']}, ngoài {c['ngoai']}, "
                                              f"không rõ {c['khong_ro']}), {len(law.quotes)} khối trích dẫn"))
    return flags


def has_errors(flags: list[Flag]) -> bool:
    return any(f.level == LOI for f in flags)


def format_report(law: AmendingLaw, flags: list[Flag], limit: int = 40) -> str:
    m = law.meta
    out = [f"{m.ten_day_du or '?'} — số hiệu {m.so_hieu}", f"  ngày thông qua: {m.ngay_ban_hanh}   hiệu lực: {m.ngay_hieu_luc}"]
    for level in (LOI, CANH_BAO, THONG_TIN):
        sel = [f for f in flags if f.level == level]
        if not sel:
            continue
        out.append(f"{level}: {len(sel)}")
        for f in sel[:limit]:
            out.append(f"  [{f.code}] {f.message}")
        if len(sel) > limit:
            out.append(f"  ... và {len(sel) - limit} cờ nữa")
    return "\n".join(out)
