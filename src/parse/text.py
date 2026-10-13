"""Chuẩn hoá văn bản luật và đọc ngày kiểu Việt Nam. Dùng chung cho parser và (sau này) validator nội dung mới."""
from __future__ import annotations

import re
import unicodedata
from datetime import date

# Ð/ð (chữ Latin Eth, U+00D0/U+00F0) trông giống hệt Đ/đ (U+0110/U+0111) nhưng là ký tự khác.
# Nhiều file .docx luật dùng nhầm, làm regex "Điều" và "đ)" trượt.
HOMOGLYPHS = {"Ð": "Đ", "ð": "đ"}
_INVISIBLE = dict.fromkeys(map(ord, "​‌‍﻿­"), None)
_SPACES = re.compile(r"[ \t  -   　]+")

DATE_RE = re.compile(r"ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})", re.IGNORECASE)


def count_homoglyphs(text: str) -> int:
    """Số ký tự Ð/ð sẽ bị sửa (đếm trên văn bản thô, trước khi chuẩn hoá)."""
    return sum(text.count(ch) for ch in HOMOGLYPHS)


def normalize_text(text: str) -> str:
    """NFC, sửa Ð/ð thành Đ/đ, bỏ ký tự ẩn, xuống dòng mềm thành dấu cách, gộp khoảng trắng, cắt hai đầu."""
    text = unicodedata.normalize("NFC", text)
    for bad, good in HOMOGLYPHS.items():
        text = text.replace(bad, good)
    text = text.translate(_INVISIBLE)
    text = re.sub(r"\s*[\r\n\v]+\s*", " ", text)
    return _SPACES.sub(" ", text).strip()


def date_from_match(m: re.Match) -> str | None:
    """Kết quả khớp DATE_RE (hoặc mẫu có 3 nhóm ngày, tháng, năm) thành 'YYYY-MM-DD'; None nếu ngày không có thật."""
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
    except ValueError:
        return None


def parse_vn_date(text: str) -> str | None:
    """Ngày đầu tiên dạng 'ngày 27 tháng 11 năm 2015' trong text, thành 'YYYY-MM-DD'."""
    m = DATE_RE.search(text)
    return date_from_match(m) if m else None
