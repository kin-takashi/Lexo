"""Mô hình dữ liệu của kết quả parse: cây đơn vị luật, metadata, và văn bản đã parse (lưu được thành JSON chờ duyệt)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Iterator

LOAI_ORDER = ("phan", "chuong", "muc", "tieu_muc", "dieu", "khoan", "diem")
RANK = {loai: i for i, loai in enumerate(LOAI_ORDER)}
FORMAT_VERSION = 1

# Bảng chữ cái đánh số Điểm (và hậu tố Điều như 173a) trong văn bản luật VN: có đ, không có f, j, w, z.
VN_LETTERS = "abcdđeghiklmnopqrstuvxy"


@dataclass
class Node:
    loai: str
    ky_hieu: str
    tieu_de: str | None = None
    noi_dung: str = ""          # văn bản riêng của nút (các đoạn nối bằng '\n'); không gồm ký hiệu "1." / "a)"
    line_start: int = 0         # chỉ số dòng (trong ParsedLaw.lines) của dòng mở đầu nút
    line_end: int = 0           # chỉ số dòng cuối cùng thuộc chính nút này (không tính nút con)
    children: list[Node] = field(default_factory=list)

    def walk(self) -> Iterator[Node]:
        yield self
        for child in self.children:
            yield from child.walk()

    def full_text(self) -> str:
        return "\n".join(n.noi_dung for n in self.walk() if n.noi_dung)

    def to_dict(self) -> dict:
        return {
            "loai": self.loai,
            "ky_hieu": self.ky_hieu,
            "tieu_de": self.tieu_de,
            "noi_dung": self.noi_dung,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "children": [c.to_dict() for c in self.children],
        }

    @classmethod
    def from_dict(cls, d: dict) -> Node:
        return cls(
            loai=d["loai"],
            ky_hieu=d["ky_hieu"],
            tieu_de=d.get("tieu_de"),
            noi_dung=d.get("noi_dung", ""),
            line_start=d.get("line_start", 0),
            line_end=d.get("line_end", 0),
            children=[cls.from_dict(c) for c in d.get("children", [])],
        )


@dataclass
class LawMeta:
    so_hieu: str | None = None
    loai: str | None = None            # 'bo_luat' / 'luat' / ...
    ten_day_du: str | None = None
    ten_viet_tat: str | None = None    # IN HOA, vd 'BLHS'
    ngay_ban_hanh: str | None = None   # ISO; lấy từ câu "đã được Quốc hội ... thông qua ngày ..."
    ngay_hieu_luc: str | None = None   # ISO; lấy từ Điều hiệu lực thi hành CỦA CHÍNH văn bản (chưa tính nghị quyết hoãn)


@dataclass
class ParsedLaw:
    meta: LawMeta
    roots: list[Node]
    lines: list[str]                   # toàn bộ dòng đã chuẩn hoá, để giao diện duyệt hiển thị văn bản gốc
    preamble: list[str] = field(default_factory=list)
    footer: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)   # cảnh báo của parser
    source: dict = field(default_factory=dict)          # name, sha256, homoglyphs_fixed, n_tables

    def iter_nodes(self) -> Iterator[Node]:
        for root in self.roots:
            yield from root.walk()

    def to_dict(self) -> dict:
        return {
            "format_version": FORMAT_VERSION,
            "meta": asdict(self.meta),
            "roots": [r.to_dict() for r in self.roots],
            "lines": self.lines,
            "preamble": self.preamble,
            "footer": self.footer,
            "warnings": self.warnings,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ParsedLaw:
        if d.get("format_version") != FORMAT_VERSION:
            raise ValueError(f"format_version {d.get('format_version')!r} không được hỗ trợ (cần {FORMAT_VERSION})")
        return cls(
            meta=LawMeta(**d["meta"]),
            roots=[Node.from_dict(r) for r in d["roots"]],
            lines=d["lines"],
            preamble=d.get("preamble", []),
            footer=d.get("footer", []),
            warnings=d.get("warnings", []),
            source=d.get("source", {}),
        )
