"""Parse VĂN BẢN GỐC (luật ban hành lần đầu) thành cây Phần > Chương > Mục > Điều > Khoản > Điểm bằng regex.

Không dùng LLM (nguyên tắc 1 của kế hoạch v2). Đầu vào là danh sách dòng đã chuẩn hoá (src/ingest/docx_text.py).
Quy tắc chính:
  * Dòng mở đầu một đơn vị: "Phần thứ nhất", "Chương I", "Mục 1", "Điều 5. Tiêu đề", "1. ...", "a) ...".
  * Tiêu đề Phần/Chương/Mục là (các) dòng IN HOA ngay sau dòng mở đầu.
  * Dòng không mở đầu đơn vị nào là ĐOẠN NỐI TIẾP của đơn vị mở gần nhất (nối bằng '\\n').
  * Câu chốt "Bộ luật này đã được Quốc hội ... thông qua ngày ..." và các dòng sau nó là chân văn bản, không thuộc Điều nào.
"""
from __future__ import annotations

import re

from .model import RANK, VN_LETTERS, LawMeta, Node, ParsedLaw
from .text import DATE_RE, date_from_match, parse_vn_date

_ROMAN = r"[IVXLCDM]+"
_END = r"(?=\s|[.:–-]|$)\s*[.:–-]?\s*(.*)$"

RE_PHAN = re.compile(rf"^(?:Phần|PHẦN)\s+(thứ\s+[^\s.:–-]+|{_ROMAN}){_END}")
RE_CHUONG = re.compile(rf"^(?:Chương|CHƯƠNG)\s+({_ROMAN}){_END}")
RE_TIEU_MUC = re.compile(rf"^(?:Tiểu mục|TIỂU MỤC)\s+(\d+|{_ROMAN}){_END}")
RE_MUC = re.compile(rf"^(?:Mục|MỤC)\s+(\d+|{_ROMAN}){_END}")
RE_DIEU = re.compile(r"^Điều\s+(\d+[a-zđ]?)\s*\.\s*(.*)$")
RE_KHOAN = re.compile(r"^(\d+[a-zđ]?)\.(?:\s+(.*))?$")   # "2.000.000" không khớp: sau dấu chấm phải là khoảng trắng hoặc hết dòng
RE_DIEM = re.compile(r"^([a-zđ])\)\s*(.*)$")
RE_CLOSING = re.compile(r"^(?:Bộ luật|Luật|Pháp lệnh|Nghị quyết)\s+này\s+đã được\b.*\bthông qua\b", re.IGNORECASE)
RE_RULE = re.compile(r"^[_\-–—=*\s]{5,}$")
RE_SO_HIEU = re.compile(r"Số\s*:?\s*(\d+(?:/[0-9A-Za-zĐđ\-]+)+)")
RE_HIEU_LUC = re.compile(
    r"hiệu lực(?:\s+thi hành)?\s+(?:kể\s+)?từ\s+ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})", re.IGNORECASE
)

_STRUCTURAL = (
    ("phan", RE_PHAN),
    ("chuong", RE_CHUONG),
    ("tieu_muc", RE_TIEU_MUC),   # trước "muc" vì cùng có chữ "mục"
    ("muc", RE_MUC),
    ("dieu", RE_DIEU),
)
_LOAI_VAN_BAN = (("BỘ LUẬT", "bo_luat"), ("LUẬT", "luat"), ("PHÁP LỆNH", "phap_lenh"), ("NGHỊ QUYẾT", "nghi_quyet"),
                 ("NGHỊ ĐỊNH", "nghi_dinh"))
MAX_WORDS_VIET_TAT = 6


def _match_structural(s: str) -> tuple[str, str, str | None] | None:
    for loai, rx in _STRUCTURAL:
        m = rx.match(s)
        if m:
            return loai, m.group(1), (m.group(2) or "").strip() or None
    return None


def _match_khoan_diem(s: str) -> tuple[str, str, str | None] | None:
    m = RE_KHOAN.match(s)
    if m:
        return "khoan", m.group(1), (m.group(2) or "").strip() or None
    m = RE_DIEM.match(s)
    if m:
        return "diem", m.group(1), (m.group(2) or "").strip() or None
    return None


def _is_title_line(s: str) -> bool:
    return bool(s) and s.isupper()


def _split_footer(lines: list[str]) -> tuple[int, bool]:
    """Chỉ số kết thúc phần thân (không gồm dòng kẻ ngang ngay trước câu chốt) và có tìm thấy câu chốt hay không."""
    n = len(lines)
    start = None
    for i in range(max(0, n - 40), n):
        if RE_CLOSING.match(lines[i]):
            start = i          # lấy câu khớp cuối cùng trong 40 dòng cuối
    if start is None:
        return n, False
    end = start
    while end > 0 and RE_RULE.match(lines[end - 1]):
        end -= 1
    return end, True


def _append_text(node: Node, line: str, index: int) -> None:
    node.noi_dung = f"{node.noi_dung}\n{line}" if node.noi_dung else line
    node.line_end = index


def _open(node: Node, stack: list[Node], roots: list[Node]) -> None:
    while stack and RANK[stack[-1].loai] >= RANK[node.loai]:
        stack.pop()
    (stack[-1].children if stack else roots).append(node)
    stack.append(node)


def _split_inline_points(node: Node, stack: list[Node], roots: list[Node], warnings: list[str], index: int) -> Node:
    """Một số file Word gộp nhiều điểm vào cùng một dòng: "b) ...; c) ...; d) ...".
    Chỉ tách khi ký hiệu đứng sau dấu ';' hoặc '.' đúng bằng chữ cái KẾ TIẾP của điểm hiện tại
    (b → c, d → đ), nên câu dẫn chiếu kiểu "điểm a) khoản 1" không bị tách nhầm. Mỗi lần tách đều ghi cảnh báo để người duyệt thấy.
    Trả về nút điểm cuối cùng (đang mở)."""
    while node.loai == "diem":
        pos = VN_LETTERS.find(node.ky_hieu)
        if pos < 0 or pos + 1 >= len(VN_LETTERS):
            break
        nxt = VN_LETTERS[pos + 1]
        m = re.search(rf"(?<=[;.])[ ]+{re.escape(nxt)}\)[ ]+", node.noi_dung)
        if not m:
            break
        tail = node.noi_dung[m.end():]
        node.noi_dung = node.noi_dung[: m.start()]
        new = Node(loai="diem", ky_hieu=nxt, noi_dung=tail, line_start=index, line_end=index)
        _open(new, stack, roots)
        warnings.append(f"dòng {index}: tách điểm {nxt}) đang gộp cùng dòng với điểm {node.ky_hieu})")
        node = new
    return node


def parse_body(body: list[str], *, loose: bool = False) -> tuple[list[Node], list[str], list[str]]:
    """Dựng cây từ các dòng thân văn bản. Trả về (roots, preamble, warnings); preamble = dòng trước đơn vị đầu tiên.
    loose=True: nhận "1." / "a)" làm khoản/điểm ngay cả khi chưa mở Điều nào — dùng cho khối trích dẫn của luật
    sửa đổi, vốn thường chỉ chứa một khoản hoặc một điểm."""
    roots: list[Node] = []
    stack: list[Node] = []
    preamble: list[str] = []
    warnings: list[str] = []

    i = 0
    while i < len(body):
        s = body[i]
        in_dieu = loose or any(n.loai == "dieu" for n in stack)
        hit = _match_structural(s)
        if hit is None and in_dieu:
            hit = _match_khoan_diem(s)

        if hit is None:                                   # đoạn nối tiếp (hoặc phần mở đầu)
            if not stack:
                preamble.append(s)
            else:
                top = stack[-1]
                if top.loai in ("phan", "chuong", "muc", "tieu_muc"):
                    warnings.append(f"dòng {i}: văn bản nằm ngoài Điều, dưới {top.loai} {top.ky_hieu}: {s[:60]!r}")
                _append_text(top, s, i)
            i += 1
            continue

        loai, ky_hieu, inline = hit
        node = Node(loai=loai, ky_hieu=ky_hieu, line_start=i, line_end=i)
        if loai in ("phan", "chuong", "muc", "tieu_muc"):
            node.tieu_de = inline
            j = i + 1
            if inline is None:
                parts = []
                while j < len(body) and _is_title_line(body[j]) and _match_structural(body[j]) is None:
                    parts.append(body[j])
                    j += 1
                node.tieu_de = " ".join(parts) or None
            node.line_end = j - 1
            _open(node, stack, roots)
            i = j
            continue
        if loai == "dieu":
            node.tieu_de = inline
        else:
            node.noi_dung = inline or ""
        _open(node, stack, roots)
        if loai == "diem":
            _split_inline_points(node, stack, roots, warnings, i)
        i += 1
    return roots, preamble, warnings


def parse_base_law(
    lines: list[str],
    header_text: str = "",
    *,
    ten_viet_tat: str | None = None,
    so_hieu: str | None = None,
    source: dict | None = None,
) -> ParsedLaw:
    end, has_footer = _split_footer(lines)
    body, footer = lines[:end], lines[end:]
    roots, preamble, warnings = parse_body(body)

    law = ParsedLaw(
        meta=LawMeta(),
        roots=roots,
        lines=lines,
        preamble=preamble,
        footer=footer if has_footer or footer else [],
        warnings=warnings,
        source=dict(source or {}),
    )
    law.meta = _extract_meta(law, header_text, ten_viet_tat=ten_viet_tat, so_hieu=so_hieu)
    return law


def _extract_meta(law: ParsedLaw, header_text: str, *, ten_viet_tat: str | None, so_hieu: str | None) -> LawMeta:
    meta = LawMeta()

    # số hiệu: tham số > bảng đầu trang > vài dòng đầu
    if so_hieu:
        meta.so_hieu = so_hieu
    else:
        m = RE_SO_HIEU.search(header_text) or RE_SO_HIEU.search(" ".join(law.preamble[:8]))
        meta.so_hieu = m.group(1) if m else None

    # loại và tên: hai dòng đầu, vd "BỘ LUẬT" + "HÌNH SỰ"
    kind_line = law.preamble[0] if law.preamble else ""
    name_line = law.preamble[1] if len(law.preamble) > 1 and _is_title_line(law.preamble[1]) else ""
    for label, code in _LOAI_VAN_BAN:
        if kind_line == label:
            meta.loai = code
            if name_line:
                meta.ten_day_du = f"{label.capitalize()} {name_line.lower()}"
                words = f"{label} {name_line}".split()
                if len(words) <= MAX_WORDS_VIET_TAT:
                    meta.ten_viet_tat = "".join(w[0] for w in words).upper()
            break
    if ten_viet_tat:
        meta.ten_viet_tat = ten_viet_tat.upper()

    # ngày ban hành: câu chốt ở chân văn bản
    for line in law.footer:
        if RE_CLOSING.match(line):
            meta.ngay_ban_hanh = parse_vn_date(line)
            break

    # ngày hiệu lực: Điều "Hiệu lực thi hành" (từ cuối lên) trong chính văn bản
    dieus = [n for n in law.iter_nodes() if n.loai == "dieu"]
    for dieu in reversed(dieus):
        if "hiệu lực" not in (dieu.tieu_de or "").lower():
            continue
        m = RE_HIEU_LUC.search(dieu.full_text())
        if m:
            meta.ngay_hieu_luc = date_from_match(m)
            break
    return meta
