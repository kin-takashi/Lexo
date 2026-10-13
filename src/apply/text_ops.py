"""Thao tác cụm từ (thay / bỏ / bổ sung) trên một đoạn văn bản: hàm thuần, không đụng CSDL."""
from __future__ import annotations

import re

KIEU = ("thay", "bo", "chen_sau", "chen_truoc", "chen_dau", "chen_cuoi")
_PUNCT_AFTER = ",;.:)"


def _is_word(ch: str) -> bool:
    return bool(re.match(r"\w", ch))


def phrase_regex(phrase: str) -> re.Pattern:
    """Khớp nguyên cụm; đầu/cuối cụm là chữ thì phải đứng riêng (không nằm giữa một từ dài hơn)."""
    pat = re.escape(phrase)
    if _is_word(phrase[0]):
        pat = r"(?<!\w)" + pat
    if _is_word(phrase[-1]):
        pat += r"(?!\w)"
    return re.compile(pat)


def _sep(moi: str) -> str:
    return "" if moi[:1] in _PUNCT_AFTER else " "


def apply_phrase(text: str, kieu: str, cu: str | None, moi: str | None) -> tuple[str, int]:
    """Trả về (văn bản mới, số chỗ đã đổi). 0 nghĩa là không tìm thấy cụm cần tìm.

    Luật sửa đổi thường dẫn cụm từ theo dạng giữa câu ("gây thiệt hại về tài sản") trong khi văn bản đích viết hoa chữ đầu vì nó mở
    đầu một điểm/khoản ("Gây thiệt hại về tài sản ..."). Nếu KHÔNG có chỗ nào khớp nguyên dạng mà văn bản mở đầu đúng bằng cụm đó
    viết hoa chữ đầu, thì áp lệnh ở đầu văn bản và giữ chữ hoa (kết quả vẫn được ghi cảnh báo ở tầng trên khi cần)."""
    if kieu not in KIEU:
        raise ValueError(f"kiểu thao tác cụm từ không hợp lệ: {kieu!r}")
    moi = moi or ""
    if kieu in ("chen_dau", "chen_cuoi"):
        if not text or not moi:
            return text, 0
        if kieu == "chen_dau":
            return f"{moi} {text}", 1
        return f"{text}{_sep(moi)}{moi}", 1
    if not cu:
        raise ValueError(f"kiểu {kieu} cần cụm từ cũ")
    out = _apply_exact(text, kieu, cu, moi)
    if out[1] == 0 and cu[0].islower() and text[:1] == cu[0].upper():
        cap = cu[0].upper() + cu[1:]
        if text.startswith(cap) and not (len(text) > len(cap) and _is_word(text[len(cap)]) and _is_word(cap[-1])):
            return _apply_at_start(text, kieu, cap, moi)
    return out


def _cap(x: str) -> str:
    return x[:1].upper() + x[1:]


def _apply_at_start(text: str, kieu: str, cap: str, moi: str) -> tuple[str, int]:
    rest = text[len(cap):]
    if kieu == "thay":
        return _cap(moi) + rest, 1
    if kieu == "chen_sau":
        return cap + _sep(moi) + moi + rest, 1
    if kieu == "chen_truoc":
        return _cap(moi) + " " + cap[0].lower() + cap[1:] + rest, 1
    out, n = _remove(text, cap, phrase_regex(cap))                       # bo
    return _cap(out), n


def _apply_exact(text: str, kieu: str, cu: str, moi: str) -> tuple[str, int]:
    rx = phrase_regex(cu)
    if kieu == "thay":
        return _subn(rx, text, moi)
    if kieu == "chen_sau":
        return _subn(rx, text, cu + _sep(moi) + moi)
    if kieu == "chen_truoc":
        return _subn(rx, text, moi + " " + cu)
    return _remove(text, cu, rx)


def _subn(rx: re.Pattern, text: str, repl: str) -> tuple[str, int]:
    new, n = rx.subn(lambda _m: repl, text)
    return new, n


def _remove(text: str, cu: str, rx: re.Pattern) -> tuple[str, int]:
    mark = "\x00"
    t, n = rx.subn(lambda _m: mark, text)
    if not n:
        return text, 0
    if _is_word(cu[0]) and _is_word(cu[-1]):          # cụm là chữ thuần: gọn lại khoảng trắng quanh chỗ bỏ
        t = re.sub(r" ?\x00(?=[,;.:)]|$)", "", t)     # "A tư pháp, B" -> "A, B"
        t = t.replace(" \x00 ", " ")                   # "A tư pháp B"  -> "A B"
        t = re.sub(r"^\x00 ", "", t)                   # bỏ ở đầu câu
    return t.replace(mark, ""), n
