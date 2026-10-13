"""Validator tự động cho văn bản gốc đã parse — chạy TRƯỚC khi người duyệt (nguyên tắc 2 của kế hoạch v2).

Chỉ kiểm tra cấu trúc và metadata; không phán đoán nội dung pháp lý.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from src.parse.model import LOAI_ORDER, VN_LETTERS, Node, ParsedLaw

LOI, CANH_BAO, THONG_TIN = "LỖI", "CẢNH BÁO", "THÔNG TIN"

_KEY = re.compile(r"^(\d+)([a-zđ]?)$")
_ROMAN_VAL = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
_PHAN_WORDS = {"nhất": 1, "hai": 2, "ba": 3, "tư": 4, "bốn": 4, "năm": 5, "sáu": 6, "bảy": 7, "tám": 8, "chín": 9, "mười": 10}
_TIEU_DE_LOAI = {"phan": "Phần", "chuong": "Chương", "muc": "Mục", "tieu_muc": "Tiểu mục"}


@dataclass(frozen=True)
class Flag:
    level: str
    code: str
    message: str
    line: int | None = None     # chỉ số dòng trong ParsedLaw.lines, để giao diện duyệt nhảy tới


def roman_to_int(s: str) -> int | None:
    total, prev = 0, 0
    for ch in reversed(s.upper()):
        v = _ROMAN_VAL.get(ch)
        if v is None:
            return None
        total += v if v >= prev else -v
        prev = max(prev, v)
    return total


def _key_tuple(ky: str) -> tuple[int, str] | None:
    m = _KEY.match(ky)
    return (int(m.group(1)), m.group(2)) if m else None


def _allowed_next(prev: tuple[int, str]) -> set[tuple[int, str]]:
    n, suffix = prev
    allowed = {(n + 1, "")}
    idx = -1 if suffix == "" else VN_LETTERS.find(suffix)
    if idx + 1 < len(VN_LETTERS):
        allowed.add((n, VN_LETTERS[idx + 1]))
    return allowed


def _fmt(t: tuple[int, str]) -> str:
    return f"{t[0]}{t[1]}"


def _check_sequence(nodes: list[Node], label: str, where: str, flags: list[Flag], *, must_start_at_one: bool) -> None:
    """Ký hiệu dạng số (kèm hậu tố chữ): 1, 2, 2a, 3 ... liên tục, không trùng."""
    prev: tuple[int, str] | None = None
    for node in nodes:
        cur = _key_tuple(node.ky_hieu)
        if cur is None:
            flags.append(Flag(LOI, f"{label}_ky_hieu_la", f"{label} có ký hiệu lạ {node.ky_hieu!r}{where}", node.line_start))
            prev = None
            continue
        if cur[1] and cur[1] not in VN_LETTERS:
            flags.append(Flag(CANH_BAO, f"{label}_hau_to_la", f"{label} {node.ky_hieu}{where}: hậu tố ngoài bảng chữ cái luật", node.line_start))
        if prev is None:
            if must_start_at_one and cur != (1, ""):
                flags.append(Flag(LOI, f"{label}_khong_bat_dau_tu_1", f"{label} đầu tiên là {node.ky_hieu}, không phải 1{where}", node.line_start))
        elif cur == prev:
            flags.append(Flag(LOI, f"{label}_trung", f"{label} {node.ky_hieu} bị trùng{where}", node.line_start))
        elif cur not in _allowed_next(prev):
            missing = ""
            if cur[1] == "" and cur[0] > prev[0] + 1:
                gap = list(range(prev[0] + 1, cur[0]))
                missing = " (thiếu " + ", ".join(map(str, gap[:6])) + (", ..." if len(gap) > 6 else "") + ")"
            flags.append(Flag(LOI, f"{label}_nhay_so", f"{label} nhảy số: {_fmt(prev)} → {node.ky_hieu}{missing}{where}", node.line_start))
        prev = cur


def _check_int_sequence(nodes: list[Node], label: str, where: str, flags: list[Flag], *, must_start_at_one: bool) -> None:
    """Ký hiệu số nguyên hoặc số La Mã (Chương I, II ...; Mục 1, 2 ...)."""
    prev = None
    for node in nodes:
        value = int(node.ky_hieu) if node.ky_hieu.isdigit() else roman_to_int(node.ky_hieu)
        if value is None:
            flags.append(Flag(LOI, f"{label}_ky_hieu_la", f"{label} có ký hiệu lạ {node.ky_hieu!r}{where}", node.line_start))
            prev = None
            continue
        if prev is None:
            if must_start_at_one and value != 1:
                flags.append(Flag(LOI, f"{label}_khong_bat_dau_tu_1", f"{label} đầu tiên là {node.ky_hieu}, không phải 1{where}", node.line_start))
        elif value != prev + 1:
            flags.append(Flag(LOI, f"{label}_nhay_so", f"{label} nhảy số: {prev} → {node.ky_hieu}{where}", node.line_start))
        prev = value


def _check_points(points: list[Node], where: str, flags: list[Flag]) -> None:
    for i, p in enumerate(points):
        expected = VN_LETTERS[i] if i < len(VN_LETTERS) else None
        if p.ky_hieu != expected:
            flags.append(Flag(LOI, "diem_sai_thu_tu", f"điểm {p.ky_hieu} nhưng mong đợi {expected}{where}", p.line_start))
            break                                   # một cờ cho mỗi nhóm, tránh dây chuyền


def _where(trail: list[Node]) -> str:
    names = {"dieu": "Điều", "khoan": "khoản", "diem": "điểm", "chuong": "Chương", "muc": "Mục", "phan": "Phần"}
    return " (trong " + " ".join(f"{names.get(n.loai, n.loai)} {n.ky_hieu}" for n in trail) + ")" if trail else ""


def _check_children(children: list[Node], trail: list[Node], flags: list[Flag]) -> None:
    where = _where([n for n in trail if n.loai in ("dieu", "khoan", "chuong", "phan", "muc")])
    by_loai: dict[str, list[Node]] = {}
    for c in children:
        by_loai.setdefault(c.loai, []).append(c)
    if "khoan" in by_loai:
        _check_sequence(by_loai["khoan"], "khoản", where, flags, must_start_at_one=True)
    if "diem" in by_loai:
        _check_points(by_loai["diem"], where, flags)
    if "muc" in by_loai:
        _check_int_sequence(by_loai["muc"], "Mục", where, flags, must_start_at_one=True)
    if "chuong" in by_loai:      # số Chương có thể tiếp nối qua các Phần, nên không bắt buộc bắt đầu từ I
        _check_int_sequence(by_loai["chuong"], "Chương", where, flags, must_start_at_one=False)


def _walk(node: Node, trail: list[Node], flags: list[Flag]) -> None:
    trail = trail + [node]
    if node.loai == "dieu":
        if not node.noi_dung and not node.children:
            flags.append(Flag(LOI, "dieu_rong", f"Điều {node.ky_hieu} không có nội dung", node.line_start))
        if not node.tieu_de:
            flags.append(Flag(CANH_BAO, "dieu_thieu_tieu_de", f"Điều {node.ky_hieu} không có tiêu đề", node.line_start))
    elif node.loai in _TIEU_DE_LOAI:
        if not node.tieu_de:
            flags.append(Flag(CANH_BAO, "thieu_tieu_de", f"{_TIEU_DE_LOAI[node.loai]} {node.ky_hieu} không có tiêu đề", node.line_start))
    elif not node.noi_dung and not node.children:
        flags.append(Flag(CANH_BAO, "don_vi_rong", f"{node.loai} {node.ky_hieu} rỗng{_where(trail[:-1])}", node.line_start))
    _check_children(node.children, trail, flags)
    for child in node.children:
        _walk(child, trail, flags)


def validate_base_law(law: ParsedLaw) -> list[Flag]:
    flags: list[Flag] = []
    m = law.meta

    # --- metadata ---
    if not m.so_hieu:
        flags.append(Flag(LOI, "thieu_so_hieu", "Không đọc được số hiệu văn bản (truyền --so-hieu nếu cần)"))
    if not m.ten_day_du or not m.loai:
        flags.append(Flag(LOI, "thieu_ten", "Không đọc được loại/tên văn bản từ hai dòng đầu"))
    if not m.ten_viet_tat:
        flags.append(Flag(LOI, "thieu_viet_tat", "Chưa có tên viết tắt (tra chính xác cần); truyền --ten-viet-tat"))
    if not m.ngay_ban_hanh:
        flags.append(Flag(LOI, "thieu_ngay_ban_hanh", "Không đọc được ngày ban hành từ câu 'đã được Quốc hội ... thông qua ngày ...'"))
    if not m.ngay_hieu_luc:
        flags.append(Flag(LOI, "thieu_ngay_hieu_luc", "Không đọc được ngày hiệu lực từ Điều hiệu lực thi hành"))
    if m.ngay_ban_hanh and m.ngay_hieu_luc and m.ngay_hieu_luc < m.ngay_ban_hanh:
        flags.append(Flag(LOI, "hieu_luc_truoc_ban_hanh", f"Ngày hiệu lực {m.ngay_hieu_luc} sớm hơn ngày ban hành {m.ngay_ban_hanh}"))
    if not any(True for _ in law.footer if _.startswith(("Bộ luật này", "Luật này", "Pháp lệnh này", "Nghị quyết này"))):
        flags.append(Flag(CANH_BAO, "khong_thay_cau_thong_qua", "Không thấy câu chốt 'đã được Quốc hội ... thông qua' ở cuối văn bản"))
    if m.ngay_hieu_luc:
        flags.append(Flag(THONG_TIN, "hieu_luc_theo_van_ban",
                          "Ngày hiệu lực lấy theo chính văn bản; CHƯA tính nghị quyết hoãn/đình chỉ hiệu lực (nếu có) — xử lý ở Bước 2"))
    if law.source.get("homoglyphs_fixed"):
        flags.append(Flag(THONG_TIN, "da_sua_ky_tu", f"Đã sửa {law.source['homoglyphs_fixed']} ký tự Ð/ð (Latin Eth) thành Đ/đ"))
    if law.source.get("n_tables", 0) > 2:
        flags.append(Flag(CANH_BAO, "nhieu_bang", f"Văn bản có {law.source['n_tables']} bảng; chỉ nội dung bảng đầu trang/chữ ký được xử lý, bảng trong thân bị bỏ qua"))
    for w in law.warnings:
        flags.append(Flag(CANH_BAO, "canh_bao_parse", w))

    # --- cấu trúc ---
    dieus = [n for n in law.iter_nodes() if n.loai == "dieu"]
    if not dieus:
        flags.append(Flag(LOI, "khong_co_dieu", "Không tìm thấy Điều nào"))
    _check_sequence(dieus, "Điều", "", flags, must_start_at_one=True)
    _check_children(law.roots, [], flags)
    phans = [r for r in law.roots if r.loai == "phan"]
    for k, p in enumerate(phans, start=1):
        words = p.ky_hieu.split()
        if len(words) == 2 and _PHAN_WORDS.get(words[1]) not in (None, k):
            flags.append(Flag(CANH_BAO, "phan_sai_thu_tu", f"Phần {p.ky_hieu} ở vị trí thứ {k}", p.line_start))
    for root in law.roots:
        _walk(root, [], flags)
    return flags


def summarize(law: ParsedLaw) -> dict[str, int]:
    counts = Counter(n.loai for n in law.iter_nodes())
    return {loai: counts.get(loai, 0) for loai in LOAI_ORDER}


def has_errors(flags: list[Flag]) -> bool:
    return any(f.level == LOI for f in flags)


def format_report(law: ParsedLaw, flags: list[Flag], limit: int = 40) -> str:
    m = law.meta
    out = [
        f"Nguồn: {law.source.get('name', '?')}",
        f"Số hiệu: {m.so_hieu} | Loại: {m.loai} | Tên: {m.ten_day_du} | Viết tắt: {m.ten_viet_tat}",
        f"Ban hành: {m.ngay_ban_hanh} | Hiệu lực (theo văn bản): {m.ngay_hieu_luc}",
        "Số đơn vị: " + ", ".join(f"{k}={v}" for k, v in summarize(law).items()),
        f"Dòng mở đầu: {len(law.preamble)} | dòng chân văn bản: {len(law.footer)}",
        "",
    ]
    for level in (LOI, CANH_BAO, THONG_TIN):
        group = [f for f in flags if f.level == level]
        if not group:
            continue
        out.append(f"[{level}] {len(group)}")
        for f in group[:limit]:
            at = f" (dòng {f.line})" if f.line is not None else ""
            out.append(f"  - {f.message}{at}")
        if len(group) > limit:
            out.append(f"  ... và {len(group) - limit} cờ nữa")
    n_err = sum(1 for f in flags if f.level == LOI)
    n_warn = sum(1 for f in flags if f.level == CANH_BAO)
    out.append("")
    out.append(f"KẾT QUẢ: {n_err} lỗi, {n_warn} cảnh báo — " + ("CHƯA THỂ NẠP, cần sửa lỗi" if n_err else "có thể chuyển sang duyệt"))
    return "\n".join(out)
