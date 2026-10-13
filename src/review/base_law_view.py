"""Hàm thuần (không phụ thuộc Streamlit) phục vụ giao diện duyệt: dựng văn bản từ nút, ranh giới nguồn của từng Điều, mẫu đối chiếu."""
from __future__ import annotations

import random

from src.parse.model import Node, ParsedLaw
from src.parse.text import normalize_text

SAMPLE_SEED = 2015     # cố định để lần duyệt nào cũng ra cùng danh sách mẫu
SAMPLE_SIZE = 30
_HEADS = ("phan", "chuong", "muc", "tieu_muc", "dieu")


def node_to_text(node: Node, depth: int = 0) -> str:
    """Văn bản đọc được của một nút và các nút con (cùng dạng với src.query.lookup.render)."""
    pad = "  " * max(0, depth - 1)
    if node.loai == "dieu":
        head = f"Điều {node.ky_hieu}. {node.tieu_de or ''}".rstrip()
    elif node.loai == "khoan":
        head = f"{node.ky_hieu}. {node.noi_dung}".rstrip() if node.noi_dung else f"{node.ky_hieu}."
    elif node.loai == "diem":
        head = f"{node.ky_hieu}) {node.noi_dung}".rstrip() if node.noi_dung else f"{node.ky_hieu})"
    else:
        head = f"{node.loai} {node.ky_hieu}. {node.tieu_de or ''}".rstrip()
    lines = [pad + head]
    if node.loai in ("dieu", "phan", "chuong", "muc", "tieu_muc") and node.noi_dung:
        lines.append(node.noi_dung)
    lines.extend(node_to_text(c, depth + 1) for c in node.children)
    return "\n".join(lines)


def dieu_spans(law: ParsedLaw) -> list[tuple[Node, int, int]]:
    """[(Điều, dòng đầu, dòng cuối+1)] theo thứ tự văn bản. Đoạn nguồn của một Điều kết thúc ở dòng mở đầu của
    Phần/Chương/Mục/Điều kế tiếp (tiêu đề Chương nằm giữa hai Điều không thuộc Điều trước)."""
    heads = sorted((n for n in law.iter_nodes() if n.loai in _HEADS), key=lambda n: n.line_start)
    body_end = len(law.lines) - len(law.footer)
    out = []
    for k, node in enumerate(heads):
        if node.loai == "dieu":
            end = heads[k + 1].line_start if k + 1 < len(heads) else body_end
            out.append((node, node.line_start, end))
    return out


def source_text(law: ParsedLaw, start: int, end: int) -> str:
    return normalize_text(" ".join(law.lines[start:end]))


def dieu_matches_source(law: ParsedLaw, node: Node, start: int, end: int) -> bool:
    return normalize_text(node_to_text(node)) == source_text(law, start, end)


def dieu_at_line(law: ParsedLaw, line: int) -> tuple[Node, int, int] | None:
    for span in dieu_spans(law):
        if span[1] <= line < span[2]:
            return span
    return None


def path_to(law: ParsedLaw, target: Node) -> list[Node]:
    """Chuỗi Phần > Chương > Mục ... chứa target (không gồm target)."""
    def walk(nodes: list[Node], trail: list[Node]) -> list[Node] | None:
        for n in nodes:
            if n is target:
                return trail
            found = walk(n.children, trail + [n])
            if found is not None:
                return found
        return None
    return walk(law.roots, []) or []


def sample_dieu(law: ParsedLaw, n: int = SAMPLE_SIZE, seed: int = SAMPLE_SEED) -> list[str]:
    """Ký hiệu n Điều ngẫu nhiên (cố định seed), theo thứ tự văn bản, để người duyệt đối chiếu tay với bản chính thức."""
    keys = [d.ky_hieu for d, _, _ in dieu_spans(law)]
    if len(keys) <= n:
        return keys
    chosen = set(random.Random(seed).sample(range(len(keys)), n))
    return [k for i, k in enumerate(keys) if i in chosen]
