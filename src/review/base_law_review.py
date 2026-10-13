"""Lưu và kiểm tra kết quả DUYỆT của người cho một văn bản gốc đã parse (nguyên tắc: bắt buộc có người duyệt trước khi nạp).

Thư mục làm việc của một văn bản: raw/<slug>/
    <tên file gốc>.docx   bản sao file gốc (nguồn sự thật, không sửa)
    parsed.json           kết quả parse (ParsedLaw.to_dict())
    review.json           kết quả duyệt (do giao diện duyệt ghi)

review.json gắn với sha256 của parsed.json: parse lại thì review cũ mất hiệu lực, phải duyệt lại.
Lỗi validator (mức LỖI) chỉ được nạp khi người duyệt MIỄN từng lỗi kèm ghi chú (vd lỗi do chính văn bản nguồn).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path

from src.parse.model import ParsedLaw
from src.validate.base_law import CANH_BAO, LOI, Flag, validate_base_law

REVIEW_VERSION = 1


def slugify_so_hieu(so_hieu: str) -> str:
    return so_hieu.replace("/", "-").replace(" ", "")


def flag_key(flag: Flag) -> str:
    """Khoá ổn định của một cờ: cùng nguồn + cùng parser thì cùng khoá."""
    return f"{flag.code}|{flag.message}"


def file_sha256(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def save_parsed(law: ParsedLaw, path: Path) -> str:
    """Ghi parsed.json (tất định: cùng đầu vào, cùng byte); trả về sha256."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(law.to_dict(), ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return file_sha256(path)


def load_parsed(path: Path) -> ParsedLaw:
    return ParsedLaw.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def new_review(parsed_sha256: str) -> dict:
    return {
        "review_version": REVIEW_VERSION,
        "parsed_sha256": parsed_sha256,
        "da_duyet": False,
        "nguoi_duyet": "",
        "ngay_duyet": None,
        "mien_loi": {},            # flag_key -> ghi chú bắt buộc (chỉ cờ mức LỖI)
        "da_xem_canh_bao": [],     # flag_key của mọi cờ CẢNH BÁO người duyệt đã xem (vd các chỗ parser tự tách điểm)
        "mau_doi_chieu": [],       # ký hiệu các Điều mẫu đã đối chiếu tay với bản chính thức
        "ghi_chu": "",
    }


def load_review(path: Path) -> dict | None:
    path = Path(path)
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_review(review: dict, path: Path) -> None:
    Path(path).write_text(json.dumps(review, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def approve(review: dict, nguoi_duyet: str, *, now: datetime | None = None) -> dict:
    """Đánh dấu đã duyệt (mới chỉ ghi nhận; ingest sẽ kiểm tra lại toàn bộ điều kiện)."""
    if not nguoi_duyet.strip():
        raise ValueError("Phải ghi tên người duyệt")
    out = dict(review)
    out["da_duyet"] = True
    out["nguoi_duyet"] = nguoi_duyet.strip()
    out["ngay_duyet"] = (now or datetime.now()).strftime("%Y-%m-%d")
    return out


def blocking_problems(law: ParsedLaw, review: dict | None, parsed_sha256: str) -> list[str]:
    """Các lý do chưa được nạp. Danh sách rỗng = được nạp."""
    if review is None:
        return ["Chưa có review.json: người duyệt phải mở giao diện duyệt và bấm 'Duyệt'."]
    problems: list[str] = []
    if review.get("review_version") != REVIEW_VERSION:
        problems.append("review.json khác phiên bản định dạng; duyệt lại.")
    if review.get("parsed_sha256") != parsed_sha256:
        problems.append("review.json thuộc bản parse cũ (parsed.json đã đổi); duyệt lại.")
    if not review.get("da_duyet"):
        problems.append("Người duyệt chưa bấm 'Duyệt'.")
    if not str(review.get("nguoi_duyet", "")).strip():
        problems.append("Thiếu tên người duyệt.")
    waived = review.get("mien_loi", {})
    seen = set(review.get("da_xem_canh_bao", []))
    for f in validate_base_law(law):
        if f.level == LOI and not str(waived.get(flag_key(f), "")).strip():
            problems.append(f"Lỗi chưa được miễn kèm ghi chú: {f.message}")
        elif f.level == CANH_BAO and flag_key(f) not in seen:
            problems.append(f"Cảnh báo chưa được xem: {f.message}")
    return problems
