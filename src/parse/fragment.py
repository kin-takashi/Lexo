"""Parse KHỐI TRÍCH DẪN của luật sửa đổi (nội dung mới của một Điều/khoản/điểm...) thành cây nút.

Khác văn bản gốc, khối trích dẫn thường bắt đầu ngay bằng "2." (một khoản) hoặc "b)" (một điểm) mà không có Điều bao quanh,
nên parse ở chế độ loose. Kết quả dùng chung mô hình Node với văn bản gốc để engine so khớp với cây hiện có theo (loại, ký hiệu).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .base_law import parse_body
from .model import Node

PathT = list[tuple[str, str]]


@dataclass
class Fragment:
    nodes: list[Node]                                   # các nút cấp cao nhất trong khối, theo thứ tự
    preamble: list[str] = field(default_factory=list)   # đoạn văn trước nút đầu tiên (không có ký hiệu mở đầu)
    warnings: list[str] = field(default_factory=list)

    def walk(self):
        for n in self.nodes:
            yield from n.walk()


def parse_fragment(text: str) -> Fragment:
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    roots, preamble, warnings = parse_body(lines, loose=True)
    return Fragment(nodes=roots, preamble=preamble, warnings=warnings)


def locate(nodes: list[Node], path: PathT) -> Node | None:
    """Tìm trong khối nút ứng với `path` (đường dẫn đầy đủ của đích, vd [Điều 5, khoản 2]). Khối có thể bắt đầu ở bất kỳ mức
    nào: thử khớp cả đường dẫn trước, rồi bỏ dần phần tử đầu (khối chỉ chứa khoản 2 thì khớp với [khoản 2])."""
    for j in range(len(path)):
        cur, node = nodes, None
        for loai, ky in path[j:]:
            node = next((n for n in cur if n.loai == loai and n.ky_hieu == ky), None)
            if node is None:
                break
            cur = node.children
        else:
            return node
    return None
