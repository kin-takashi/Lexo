"""Đường dẫn và cấu hình dùng chung (đọc config.yaml)."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_config() -> dict:
    import yaml

    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def db_path() -> Path:
    return ROOT / load_config()["paths"]["db"]


def raw_dir() -> Path:
    """Thư mục raw/. Biến môi trường LEXO_RAW_DIR ghi đè (dùng cho test, chạy thử)."""
    override = os.environ.get("LEXO_RAW_DIR")
    return Path(override) if override else ROOT / load_config()["paths"]["raw"]


def amending_scope() -> tuple[dict[str, str], set[str]]:
    """(tên -> số hiệu, tập số hiệu thuộc phạm vi áp dụng sửa đổi) đọc từ config.yaml (mục pham_vi_sua_doi)."""
    section = load_config().get("pham_vi_sua_doi") or {}
    aliases = {str(k).lower(): str(v) for k, v in (section.get("ten_goi") or {}).items()}
    scope = {str(v) for v in (section.get("van_ban") or [])} or set(aliases.values())
    return aliases, scope


def index_path() -> Path:
    """File chỉ mục tìm kiếm (dẫn xuất, dựng lại được). Mặc định db/chi_muc.sqlite."""
    return ROOT / ((load_config().get("paths") or {}).get("index") or "db/chi_muc.sqlite")
