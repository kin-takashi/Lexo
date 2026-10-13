"""Parse LUẬT SỬA ĐỔI (hoặc luật mới có Điều sửa đổi luật khác) thành cấu trúc trung gian amending.json.

Không dùng LLM. Việc của module này là CHIA NHỎ văn bản một cách chính xác để các bước sau (trích lệnh, duyệt, áp lệnh)
làm việc trên những mẩu có vị trí rõ ràng:

  * Điều cấp cao nhất (ngoài khối trích dẫn) -> Điều sửa đổi / Điều hiệu lực thi hành / Điều chuyển tiếp;
  * Điều sửa đổi -> mục cấp 1 ("1. Sửa đổi, bổ sung Điều 3 như sau:") -> mục cấp 2 ("a) ... như sau:");
  * KHỐI TRÍCH DẪN “...” (nội dung mới) tách riêng, có mã Q<n>, gắn vào mục đứng ngay trước nó. Nội dung khối được
    giữ nguyên văn, không đi qua LLM;
  * mỗi mục biết văn bản đích của nó (theo "số hiệu" ghi trong câu, hoặc theo tên đã biết) để lọc phạm vi:
    lệnh nhắm BLHS thì áp, lệnh nhắm luật khác chỉ ghi nhận.

Nhận biết Điều cấp cao phải xét khối trích dẫn: trong “...” có thể chứa cả một Điều ("Điều 236. Tội ...") không phải Điều của luật sửa đổi.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterator

from .model import VN_LETTERS
from .text import DATE_RE, date_from_match, parse_vn_date

FORMAT_VERSION = 1
KIND = "amending"

RE_DIEU_TOP = re.compile(r"^Điều\s+(\d+[a-zđ]?)\s*\.\s*(.*)$")
RE_ITEM1 = re.compile(r"^(\d+)\.\s+(.+)$")
RE_ITEM2 = re.compile(r"^([a-zđ])\)\s+(.+)$")
RE_SO_HIEU = re.compile(r"[Ss]ố\s*:?\s*(\d+/\d{4}/[0-9A-Za-zĐđ\-]+)")
RE_CLOSING = re.compile(r"^(?:Bộ luật|Luật|Pháp lệnh|Nghị quyết)\s+này\s+(?:đã\s+)?được\s+Quốc hội\b.*\bthông qua\b", re.IGNORECASE)
RE_HIEU_LUC = re.compile(
    r"hiệu lực(?:\s+thi hành)?\s+(?:kể\s+)?từ\s+ngày\s+(\d{1,2})\s+tháng\s+(\d{1,2})\s+năm\s+(\d{4})", re.IGNORECASE
)
RE_TIEU_DE_SUA_DOI = re.compile(r"^(Sửa đổi|Bổ sung|Bãi bỏ|Thay thế|Đính chính)", re.IGNORECASE)
RE_TARGET_LAW = re.compile(
    r"của\s+((?:Bộ luật|Luật|Pháp lệnh|Nghị quyết|Nghị định)[^;:“”]{1,120}?)\s+số\s+(\d+/\d{4}/[0-9A-Za-zĐđ\-]+)"
)
RE_QUOTED_PHRASE = re.compile(r"“[^”]*”")
_LOAI = (("BỘ LUẬT", "bo_luat", "Bộ luật"), ("LUẬT", "luat", "Luật"), ("PHÁP LỆNH", "phap_lenh", "Pháp lệnh"),
         ("NGHỊ QUYẾT", "nghi_quyet", "Nghị quyết"))

PHAM_VI_TRONG, PHAM_VI_NGOAI, PHAM_VI_KHONG_RO = "trong", "ngoai", "khong_ro"


@dataclass
class Quote:
    id: str
    line_start: int
    line_end: int
    text: str                    # nguyên văn, đã bỏ dấu “ đầu và ” cuối (kèm dấu câu ngay sau), các dòng nối bằng '\n'

    def to_dict(self) -> dict:
        return dict(id=self.id, line_start=self.line_start, line_end=self.line_end, text=self.text)


@dataclass
class Item:
    id: str                      # vd 'D1.21' (cấp 1), 'D1.21.a' (cấp 2)
    cap: int                     # 1 hoặc 2
    ky_hieu: str                 # '21' hoặc 'a'
    vi_tri_nguon: str            # vd 'Điều 1 khoản 21 điểm a' — dùng để ghi nguồn khi tra cứu
    text: str                    # dòng lệnh, đã bỏ ký hiệu mở đầu
    line_start: int
    line_end: int                # dòng cuối thuộc chính mục này (gồm khối trích dẫn của nó, không gồm mục con)
    quote_ids: list[str] = field(default_factory=list)
    van_ban_dich_so_hieu: str | None = None
    van_ban_dich_ten: str | None = None
    pham_vi: str = PHAM_VI_KHONG_RO
    children: list[Item] = field(default_factory=list)

    def walk(self) -> Iterator[Item]:
        yield self
        for c in self.children:
            yield from c.walk()

    def to_dict(self) -> dict:
        d = {k: getattr(self, k) for k in ("id", "cap", "ky_hieu", "vi_tri_nguon", "text", "line_start", "line_end",
                                           "quote_ids", "van_ban_dich_so_hieu", "van_ban_dich_ten", "pham_vi")}
        d["children"] = [c.to_dict() for c in self.children]
        return d

    @classmethod
    def from_dict(cls, d: dict) -> Item:
        kids = [cls.from_dict(c) for c in d.get("children", [])]
        return cls(children=kids, **{k: v for k, v in d.items() if k != "children"})


@dataclass
class DieuSuaDoi:
    ky_hieu: str
    tieu_de: str
    line_start: int
    line_end: int                # exclusive: dòng mở đầu Điều cấp cao kế tiếp
    van_ban_dich_so_hieu: str | None
    van_ban_dich_ten: str | None
    pham_vi: str
    items: list[Item] = field(default_factory=list)
    quotes_mo_coi: list[str] = field(default_factory=list)      # khối trích dẫn không gắn được vào mục nào

    def walk_items(self) -> Iterator[Item]:
        for it in self.items:
            yield from it.walk()

    def to_dict(self) -> dict:
        return dict(ky_hieu=self.ky_hieu, tieu_de=self.tieu_de, line_start=self.line_start, line_end=self.line_end,
                    van_ban_dich_so_hieu=self.van_ban_dich_so_hieu, van_ban_dich_ten=self.van_ban_dich_ten,
                    pham_vi=self.pham_vi, items=[i.to_dict() for i in self.items], quotes_mo_coi=self.quotes_mo_coi)

    @classmethod
    def from_dict(cls, d: dict) -> DieuSuaDoi:
        return cls(items=[Item.from_dict(i) for i in d.get("items", [])],
                   **{k: v for k, v in d.items() if k != "items"})


@dataclass
class AmendingMeta:
    so_hieu: str | None = None
    loai: str | None = None
    ten_day_du: str | None = None
    ngay_ban_hanh: str | None = None        # = ngày thông qua ở câu chốt (quy ước của dự án, xem README)
    ngay_hieu_luc: str | None = None        # ngày mặc định của cả luật (lần xuất hiện đầu trong Điều hiệu lực thi hành)
    ngay_header: str | None = None          # 'Hà Nội, ngày ...' ở đầu văn bản (nếu có), để đối chiếu
    hieu_luc_ngoai_le: list[dict] = field(default_factory=list)     # [{"cau": ..., "ngay": ...}] — người duyệt xác nhận


@dataclass
class Clause:
    ky_hieu: str
    tieu_de: str
    noi_dung: str                            # các dòng của Điều, nối bằng '\n'
    line_start: int

    def to_dict(self) -> dict:
        return dict(ky_hieu=self.ky_hieu, tieu_de=self.tieu_de, noi_dung=self.noi_dung, line_start=self.line_start)


@dataclass
class AmendingLaw:
    meta: AmendingMeta
    dieu_sua_doi: list[DieuSuaDoi]
    quotes: list[Quote]
    lines: list[str]
    preamble: list[str] = field(default_factory=list)
    footer: list[str] = field(default_factory=list)
    dieu_hieu_luc: Clause | None = None
    dieu_chuyen_tiep: Clause | None = None
    warnings: list[str] = field(default_factory=list)
    source: dict = field(default_factory=dict)

    def quote(self, quote_id: str) -> Quote:
        return self._by_id()[quote_id]

    def _by_id(self) -> dict[str, Quote]:
        cache = getattr(self, "_quote_cache", None)
        if cache is None or len(cache) != len(self.quotes):
            cache = {q.id: q for q in self.quotes}
            self._quote_cache = cache
        return cache

    def iter_items(self) -> Iterator[tuple[DieuSuaDoi, Item]]:
        for d in self.dieu_sua_doi:
            for it in d.walk_items():
                yield d, it

    def to_dict(self) -> dict:
        m = self.meta
        return {
            "format_version": FORMAT_VERSION,
            "kind": KIND,
            "meta": dict(so_hieu=m.so_hieu, loai=m.loai, ten_day_du=m.ten_day_du, ngay_ban_hanh=m.ngay_ban_hanh,
                         ngay_hieu_luc=m.ngay_hieu_luc, ngay_header=m.ngay_header, hieu_luc_ngoai_le=m.hieu_luc_ngoai_le),
            "dieu_sua_doi": [d.to_dict() for d in self.dieu_sua_doi],
            "quotes": [q.to_dict() for q in self.quotes],
            "dieu_hieu_luc": self.dieu_hieu_luc.to_dict() if self.dieu_hieu_luc else None,
            "dieu_chuyen_tiep": self.dieu_chuyen_tiep.to_dict() if self.dieu_chuyen_tiep else None,
            "lines": self.lines,
            "preamble": self.preamble,
            "footer": self.footer,
            "warnings": self.warnings,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict) -> AmendingLaw:
        if d.get("format_version") != FORMAT_VERSION or d.get("kind") != KIND:
            raise ValueError(f"amending.json không hợp lệ (format_version={d.get('format_version')!r}, kind={d.get('kind')!r})")
        return cls(
            meta=AmendingMeta(**d["meta"]),
            dieu_sua_doi=[DieuSuaDoi.from_dict(x) for x in d["dieu_sua_doi"]],
            quotes=[Quote(**q) for q in d["quotes"]],
            lines=d["lines"],
            preamble=d.get("preamble", []),
            footer=d.get("footer", []),
            dieu_hieu_luc=Clause(**d["dieu_hieu_luc"]) if d.get("dieu_hieu_luc") else None,
            dieu_chuyen_tiep=Clause(**d["dieu_chuyen_tiep"]) if d.get("dieu_chuyen_tiep") else None,
            warnings=d.get("warnings", []),
            source=d.get("source", {}),
        )


# ---------------------------------------------------------------------------------------------------------------------
# Hàm phụ

def smart_lower(name: str) -> str:
    """Chuyển tên IN HOA thành chữ thường, giữ nguyên các từ có chữ số ('100/2015/QH13')."""
    return " ".join(w if any(c.isdigit() for c in w) else w.lower() for w in name.split())


def resolve_target_law(text: str, aliases: dict[str, str]) -> tuple[str | None, str | None]:
    """(so_hieu, tên) của văn bản đích được nêu trong câu; (None, None) nếu câu không nêu.
    Cụm từ trong “ ” bị bỏ trước khi tìm (đó là chữ được thay/bỏ, không phải đích của lệnh — vd cụm từ có chứa
    "của Bộ luật Hình sự"). Ưu tiên "của <Tên> số N/YYYY/..." — chỉ lấy lần xuất hiện ĐẦU, vì sau đó thường là
    "đã được sửa đổi theo Luật số ..."."""
    text = RE_QUOTED_PHRASE.sub(" ", text)
    m = RE_TARGET_LAW.search(text)
    if m:
        return m.group(2), m.group(1).strip()
    low = text.lower()
    for name in sorted(aliases, key=len, reverse=True):
        if name in low:
            return aliases[name], name
    return None, None


def _pham_vi(so_hieu: str | None, trong: set[str]) -> str:
    if so_hieu is None:
        return PHAM_VI_KHONG_RO
    return PHAM_VI_TRONG if so_hieu in trong else PHAM_VI_NGOAI


def _strip_quote(lines: list[str]) -> str:
    first = lines[0]
    lines = list(lines)
    if first.startswith("“"):
        lines[0] = first[1:]
    m = re.search(r"”[\s.;,]*$", lines[-1])
    if m:
        lines[-1] = lines[-1][: m.start()]
    return "\n".join(lines).strip()


def _clause_from(lines: list[str], start: int, end: int, ky_hieu: str, tieu_de: str) -> Clause:
    return Clause(ky_hieu=ky_hieu, tieu_de=tieu_de, noi_dung="\n".join(lines[start + 1:end]), line_start=start)


# ---------------------------------------------------------------------------------------------------------------------
# Parse

def scan_structure(lines: list[str], start: int = 0) -> tuple[list[tuple[int, str, str]], list[tuple[int, int]], list[str]]:
    """Duyệt các dòng, trả về (Điều cấp cao, khối trích dẫn, cảnh báo).
    Điều cấp cao: [(chỉ số dòng, ký hiệu, tiêu đề)] chỉ tính khi KHÔNG nằm trong khối trích dẫn.
    Khối trích dẫn: [(dòng đầu, dòng cuối)] — mở bằng dòng bắt đầu bởi “ và đóng khi số “ và ” cân bằng."""
    dieus: list[tuple[int, str, str]] = []
    blocks: list[tuple[int, int]] = []
    warnings: list[str] = []
    depth = 0
    block_start = -1
    for i in range(start, len(lines)):
        line = lines[i]
        opens, closes = line.count("“"), line.count("”")
        if depth == 0:
            if line.startswith("“"):
                block_start = i
                depth = opens - closes
                if depth <= 0:
                    blocks.append((i, i))
                    depth = 0
                continue
            m = RE_DIEU_TOP.match(line)
            if m:
                dieus.append((i, m.group(1), m.group(2).strip()))
            elif opens != closes:
                warnings.append(f"dòng {i}: dấu “ ” không cân bằng ngoài khối trích dẫn: {line[:60]!r}")
        else:
            depth += opens - closes
            if depth <= 0:
                blocks.append((block_start, i))
                depth = 0
    if depth > 0:
        warnings.append(f"khối trích dẫn bắt đầu ở dòng {block_start} không bao giờ đóng")
    return dieus, blocks, warnings


def parse_amending_law(
    lines: list[str],
    header_text: str = "",
    *,
    aliases: dict[str, str] | None = None,
    pham_vi_so_hieu: set[str] | None = None,
    dieu_sua_doi: list[str] | None = None,
    so_hieu: str | None = None,
    source: dict | None = None,
) -> AmendingLaw:
    """aliases: tên (chữ thường) -> số hiệu, vd {"bộ luật hình sự": "100/2015/QH13"}.
    pham_vi_so_hieu: các văn bản thuộc phạm vi dự án (mặc định: mọi số hiệu trong aliases).
    dieu_sua_doi: ký hiệu các Điều chứa lệnh sửa đổi; mặc định tự nhận theo tiêu đề bắt đầu bằng Sửa đổi/Bổ sung/Bãi bỏ/Thay thế."""
    aliases = {k.lower(): v for k, v in (aliases or {}).items()}
    trong = set(pham_vi_so_hieu) if pham_vi_so_hieu is not None else set(aliases.values())
    dieus, blocks, warnings = scan_structure(lines)

    # ---- phần mở đầu và chân văn bản
    first_dieu = dieus[0][0] if dieus else len(lines)
    preamble = lines[:first_dieu]
    closing_idx = None
    for i in range(max(0, len(lines) - 40), len(lines)):
        if RE_CLOSING.match(lines[i]):
            closing_idx = i
    footer = lines[closing_idx:] if closing_idx is not None else []
    body_end = closing_idx if closing_idx is not None else len(lines)

    meta = AmendingMeta()
    m = RE_SO_HIEU.search(header_text) or RE_SO_HIEU.search(" ".join(preamble[:6]))
    meta.so_hieu = so_hieu or (m.group(1) if m else None)
    kind = lines[0] if lines else ""
    for label, code, display in _LOAI:
        if kind == label:
            meta.loai = code
            title_parts = []
            for l in lines[1:6]:
                if l.isupper():
                    title_parts.append(l)
                else:
                    break
            if title_parts:
                meta.ten_day_du = f"{display} {smart_lower(' '.join(title_parts))}"
            break
    if footer:
        meta.ngay_ban_hanh = parse_vn_date(footer[0])
    dm = re.search(r"Hà Nội,\s*(ngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4})", header_text)
    if dm:
        meta.ngay_header = parse_vn_date(dm.group(1))

    # ---- mảng Điều cấp cao: [start, end)
    ranges = []
    for k, (idx, ky, td) in enumerate(dieus):
        end = dieus[k + 1][0] if k + 1 < len(dieus) else body_end
        ranges.append((idx, min(end, body_end) if end > body_end else end, ky, td))

    # ---- Điều hiệu lực thi hành / chuyển tiếp (lấy Điều cuối cùng khớp tiêu đề)
    hl = ct = None
    for idx, end, ky, td in ranges:
        low = td.lower()
        if "hiệu lực thi hành" in low:
            hl = _clause_from(lines, idx, end, ky, td)
        if "chuyển tiếp" in low:
            ct = _clause_from(lines, idx, end, ky, td)
    if hl:
        found = []
        for line in hl.noi_dung.split("\n"):
            for mm in RE_HIEU_LUC.finditer(line):
                found.append((line.strip(), date_from_match(mm)))
        if found:
            meta.ngay_hieu_luc = found[0][1]
            meta.hieu_luc_ngoai_le = [{"cau": c, "ngay": d} for c, d in found[1:] if d != meta.ngay_hieu_luc]

    # ---- Điều sửa đổi
    wanted = set(dieu_sua_doi) if dieu_sua_doi else None
    quotes: list[Quote] = []
    block_by_start = {a: (a, b) for a, b in blocks}
    sua_doi: list[DieuSuaDoi] = []
    for idx, end, ky, td in ranges:
        is_amending = (ky in wanted) if wanted is not None else bool(RE_TIEU_DE_SUA_DOI.match(td))
        if not is_amending:
            continue
        so, ten = resolve_target_law(td, aliases)
        d = DieuSuaDoi(ky_hieu=ky, tieu_de=td, line_start=idx, line_end=end, van_ban_dich_so_hieu=so,
                       van_ban_dich_ten=ten, pham_vi=_pham_vi(so, trong))
        _parse_items(lines, d, block_by_start, quotes, aliases, trong, warnings)
        sua_doi.append(d)

    return AmendingLaw(meta=meta, dieu_sua_doi=sua_doi, quotes=quotes, lines=lines, preamble=preamble, footer=footer,
                       dieu_hieu_luc=hl, dieu_chuyen_tiep=ct, warnings=warnings, source=dict(source or {}))


def _parse_items(lines, d: DieuSuaDoi, block_by_start, quotes: list[Quote], aliases, trong, warnings) -> None:
    cur1: Item | None = None
    cur: Item | None = None
    i = d.line_start + 1
    while i < d.line_end:
        line = lines[i]
        if i in block_by_start:                                    # khối trích dẫn
            a, b = block_by_start[i]
            q = Quote(id=f"Q{len(quotes) + 1}", line_start=a, line_end=b, text=_strip_quote(lines[a:b + 1]))
            quotes.append(q)
            if cur is None:
                d.quotes_mo_coi.append(q.id)
            else:
                cur.quote_ids.append(q.id)
                cur.line_end = b
            i = b + 1
            continue
        m1, m2 = RE_ITEM1.match(line), RE_ITEM2.match(line)
        if m1:
            item = Item(id=f"D{d.ky_hieu}.{m1.group(1)}", cap=1, ky_hieu=m1.group(1),
                        vi_tri_nguon=f"Điều {d.ky_hieu} khoản {m1.group(1)}", text=m1.group(2).strip(),
                        line_start=i, line_end=i)
            so, ten = resolve_target_law(item.text, aliases)
            item.van_ban_dich_so_hieu, item.van_ban_dich_ten = (so, ten) if so else (d.van_ban_dich_so_hieu, d.van_ban_dich_ten)
            item.pham_vi = _pham_vi(item.van_ban_dich_so_hieu, trong)
            d.items.append(item)
            cur1 = cur = item
        elif m2 and cur1 is not None:
            item = Item(id=f"{cur1.id}.{m2.group(1)}", cap=2, ky_hieu=m2.group(1),
                        vi_tri_nguon=f"{cur1.vi_tri_nguon} điểm {m2.group(1)}", text=m2.group(2).strip(),
                        line_start=i, line_end=i)
            so, ten = resolve_target_law(item.text, aliases)
            item.van_ban_dich_so_hieu, item.van_ban_dich_ten = (so, ten) if so else (cur1.van_ban_dich_so_hieu, cur1.van_ban_dich_ten)
            item.pham_vi = _pham_vi(item.van_ban_dich_so_hieu, trong)
            cur1.children.append(item)
            cur = item
        elif cur is not None:                                      # dòng nối tiếp của lệnh
            cur.text = f"{cur.text}\n{line.strip()}"
            cur.line_end = i
            warnings.append(f"dòng {i}: dòng nối tiếp lệnh {cur.id} (không có ký hiệu mở đầu): {line[:60]!r}")
        else:
            warnings.append(f"dòng {i}: dòng lạ trước mục đầu tiên của Điều {d.ky_hieu}: {line[:60]!r}")
        i += 1
