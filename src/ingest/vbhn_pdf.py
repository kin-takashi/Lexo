"""Trích VĂN BẢN HỢP NHẤT (bản PDF trên Công báo) thành các đoạn văn thân + chú thích, để ĐỐI CHIẾU độc lập với bản hệ thống dựng lại.

Bản PDF Công báo là văn bản có chữ (không phải ảnh quét) và có ba dấu hiệu bố cục giúp tách đoạn mà không cần đoán:
  * cỡ chữ: thân 14pt, chú thích cuối trang 12pt, số chú thích (chỉ số trên) 8-9pt;
  * đoạn mới thụt đầu dòng (x0 lớn hơn lề trái), dòng xuống hàng tiếp nối đoạn thì bắt đầu đúng lề trái;
  * dòng đầu trang ("CÔNG BÁO/Số ... /Ngày ...") nằm cao hơn mọi dòng thân.
Số chú thích được gỡ khỏi văn bản nhưng GIỮ vị trí (marks), vì chú thích của văn bản hợp nhất cho biết điều/khoản nào do luật nào sửa:
đó là bằng chứng độc lập về nguồn sửa đổi.
Cần pdfplumber (nạp trễ để phần còn lại của dự án không phụ thuộc).
"""
from __future__ import annotations

import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from src.parse.text import normalize_text

MARK_RE = re.compile(r"⟦(\d+)⟧")
HEADER_TOP = 62.0          # dòng đầu trang có top ~54; dòng thân đầu tiên có top >= ~84
BODY_MIN_SIZE = 13.0       # thân >= 13pt (kể cả tiêu đề 16-18pt); chú thích ~12pt; số chú thích <= 10pt
NOTE_MIN_SIZE = 11.0
INDENT = 8.0               # x0 lớn hơn lề trái chừng này thì là đoạn mới
_FRONT = re.compile(
    r"^(?:VĂN BẢN KHÁC|VĂN BẢN PHÁP LUẬT KHÁC|Bộ luật Hình sự|VĂN BẢN HỢP NHẤT - VĂN PHÒNG QUỐC HỘI|Văn bản hợp nhất số .*|hợp nhất Bộ luật Hình sự|\(Tiếp theo Công báo số .*\))$",
    re.IGNORECASE)
_END = re.compile(r"(?:^|\s)XÁC THỰC VĂN BẢN HỢP NHẤT$", re.IGNORECASE)   # có thể dính sau "VĂN PHÒNG QUỐC HỘI" cùng dòng
_TRAILER = re.compile(r"^\(Xem tiếp Công báo số\b.*\)$", re.IGNORECASE)


@dataclass
class VbhnText:
    lines: list[str]                         # đoạn văn thân (từ "Phần thứ nhất"), đã chuẩn hoá, KHÔNG có số chú thích
    marks: dict[int, list[int]]              # chỉ số đoạn -> số các chú thích gắn ở đoạn đó
    footnotes: dict[int, str]                # số chú thích -> nội dung
    preamble: list[str]                      # phần đầu (tên, danh sách luật được hợp nhất) trước "Phần thứ nhất"
    pages: list[tuple[int, int]]             # với mỗi đoạn: (phần PDF, trang trong phần) đoạn bắt đầu ở đâu — để người duyệt mở đúng chỗ
    sources: list[dict] = field(default_factory=list)       # tên + sha256 từng file PDF

    def to_dict(self) -> dict:
        return {"lines": self.lines, "marks": {str(k): v for k, v in self.marks.items()},
                "footnotes": {str(k): v for k, v in self.footnotes.items()}, "preamble": self.preamble,
                "pages": [list(p) for p in self.pages], "sources": self.sources}

    @classmethod
    def from_dict(cls, d: dict) -> VbhnText:
        return cls(d["lines"], {int(k): v for k, v in d["marks"].items()}, {int(k): v for k, v in d["footnotes"].items()},
                   d["preamble"], [tuple(p) for p in d["pages"]], d.get("sources", []))


def _page_lines(words: list[dict]) -> list[dict]:
    """Gom từ thành dòng (dòng chính theo cỡ chữ >= 11pt), gắn số chú thích (chỉ số trên) vào đúng dòng, đúng vị trí."""
    main = sorted((w for w in words if w["size"] >= NOTE_MIN_SIZE and w["top"] >= HEADER_TOP), key=lambda w: (w["bottom"], w["x0"]))
    lines: list[list[dict]] = []
    for w in main:
        if lines and abs(w["bottom"] - lines[-1][-1]["bottom"]) <= 3.5:
            lines[-1].append(w)
        else:
            lines.append([w])
    out = [{"words": sorted(ws, key=lambda w: w["x0"]), "marks": [], "top": min(w["top"] for w in ws)} for ws in lines]
    for m in (w for w in words if w["size"] < NOTE_MIN_SIZE and w["top"] >= HEADER_TOP - 6):
        if not out or not m["text"].strip().isdigit():
            continue
        target = min(out, key=lambda ln: abs(ln["top"] - m["top"]))
        target["marks"].append(m)
    for ln in out:
        toks, items = [], sorted(ln["words"] + ln["marks"], key=lambda w: w["x0"])
        prev = None
        for w in items:
            is_mark = w["size"] < NOTE_MIN_SIZE
            text = f"⟦{w['text'].strip()}⟧" if is_mark else w["text"]
            exponent = is_mark and prev is not None and w["text"].strip() in ("2", "3") and prev["text"].endswith(("(m", "cm", "km"))
            if exponent:
                text = w["text"].strip()                                # m2, m3 (đơn vị đo, chỉ số trên) chứ không phải số chú thích
            glue = prev is not None and (is_mark or (prev["size"] < NOTE_MIN_SIZE and w["x0"] - prev["x1"] < 3.0))
            toks.append(text if (glue or prev is None) else " " + text)
            prev = w
        ln["text"] = "".join(toks)
        ln["x0"] = ln["words"][0]["x0"]
        ln["size"] = ln["words"][0]["size"]
        ln["starts_with_mark"] = bool(ln["marks"]) and ln["marks"][0]["x0"] <= ln["words"][0]["x0"]
    return out


def extract_vbhn(pdf_paths: list[str | Path]) -> VbhnText:
    import pdfplumber

    body: list[tuple[str, float, tuple[int, int]]] = []          # (text, x0, page)
    notes: dict[int, list[str]] = {}
    last_note: int | None = None
    sources = []
    stop_all = False
    for part, path in enumerate(pdf_paths, start=1):
        stop_part = False
        if stop_all:
            break
        path = Path(path)
        sources.append({"name": path.name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        with pdfplumber.open(path) as pdf:
            for pn, page in enumerate(pdf.pages, start=1):
                if stop_part or stop_all:
                    break
                words = page.extract_words(extra_attrs=["size"], keep_blank_chars=False, x_tolerance=1.5, use_text_flow=False)
                past_end = False                                          # đã qua khối xác thực: bỏ chữ ký, nhưng vẫn lấy chú thích cuối trang
                for ln in _page_lines(words):
                    plain = MARK_RE.sub("", ln["text"]).strip()
                    if _TRAILER.match(plain):                              # hết phần PDF: phần sau là thông tin nhà xuất bản
                        stop_part = True
                        break
                    if _END.search(plain):
                        stop_all = True
                        past_end = True
                        continue
                    if ln["size"] >= BODY_MIN_SIZE:
                        if past_end:
                            continue
                        body.append((ln["text"], ln["x0"], (part, pn)))
                    else:                                                  # chú thích cuối trang
                        text = ln["text"]
                        if ln["starts_with_mark"]:
                            m = MARK_RE.match(text)
                            last_note = int(m.group(1))
                            notes.setdefault(last_note, [])
                            text = text[m.end():]
                        if last_note is not None and text.strip():
                            notes[last_note].append(text.strip())
    # lề trái = x0 phổ biến nhất của dòng thân
    if not body:
        raise ValueError("Không trích được dòng thân văn bản nào từ PDF (không phải bản có chữ, hoặc bố cục khác hẳn Công báo?).")
    xs = Counter(round(x, 0) for _, x, _ in body)
    ngat = min(50, max(1, max(xs.values()) // 2))                 # văn bản thật rất dài (>=50 dòng ở lề); văn bản ngắn thì hạ ngưỡng
    margin = min(x for x, n in xs.items() if n >= ngat)           # lề trái: x0 nhỏ nhất xuất hiện nhiều lần (dòng đầu đoạn thụt vào nên KHÔNG phải mode)
    paras: list[list] = []
    for text, x0, pg in body:
        plain = MARK_RE.sub("", text).strip()
        new = x0 > margin + INDENT or (plain.isupper() and len(plain) > 2 and not plain[0].isdigit()) or not paras
        if new:
            paras.append([text, pg])
        else:
            paras[-1][0] += " " + text
    lines, marks, pages = [], {}, []
    for text, pg in paras:
        nums = [int(n) for n in MARK_RE.findall(text)]
        clean = normalize_text(MARK_RE.sub("", text))
        if not clean:
            continue
        if nums:
            marks[len(lines)] = nums
        lines.append(clean)
        pages.append(pg)
    # bỏ phần đầu trang đầu mỗi phần PDF (Công báo) và phần chân (xác thực, nhà xuất bản)
    if lines:
        lines[-1] = re.sub(r"\s*VĂN PHÒNG QUỐC HỘI\s*$", "", lines[-1])
    keep = [i for i, t in enumerate(lines) if not _FRONT.match(t) and t.upper() != "VĂN PHÒNG QUỐC HỘI"]
    start = next((i for i in keep if re.match(r"^Phần thứ nhất\b", lines[i], re.IGNORECASE)), keep[0] if keep else 0)
    remap = {old: new for new, old in enumerate(i for i in keep if i >= start)}
    pre = [lines[i] for i in keep if i < start and not lines[i].startswith(("Người ký", "Email", "Cơ quan", "Thời gian ký", "CÔNG BÁO"))]
    return VbhnText(
        lines=[lines[i] for i in remap],
        marks={remap[i]: v for i, v in marks.items() if i in remap},
        footnotes={n: normalize_text(" ".join(parts)) for n, parts in notes.items()},
        preamble=pre,
        pages=[pages[i] for i in remap],
        sources=sources,
    )
