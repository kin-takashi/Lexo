"""Chuẩn bị (stage) LUẬT SỬA ĐỔI: docx -> parse -> validate -> raw/<slug>/{file gốc, amending.json}. Chưa ghi CSDL."""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path

from src.ingest.base_law import IngestError
from src.ingest.docx_text import extract_docx
from src.parse.amending import AmendingLaw, parse_amending_law
from src.review.base_law_review import file_sha256, slugify_so_hieu
from src.validate.amending import validate_amending_law
from src.validate.base_law import Flag


@dataclass
class StagedAmending:
    law: AmendingLaw
    flags: list[Flag]
    directory: Path
    amending_path: Path
    sha256: str
    raw_copy: Path


def save_amending(law: AmendingLaw, path: Path) -> str:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(law.to_dict(), ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return file_sha256(path)


def load_amending(path: Path) -> AmendingLaw:
    return AmendingLaw.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def stage_amending_law(
    docx_path: str | Path,
    raw_root: str | Path,
    *,
    aliases: dict[str, str],
    pham_vi_so_hieu: set[str],
    so_hieu: str | None = None,
    dieu_sua_doi: list[str] | None = None,
) -> StagedAmending:
    docx_path = Path(docx_path)
    ex = extract_docx(docx_path)
    law = parse_amending_law(ex.lines, ex.header_text, aliases=aliases, pham_vi_so_hieu=pham_vi_so_hieu,
                             dieu_sua_doi=dieu_sua_doi, so_hieu=so_hieu, source=ex.source_info())
    flags = validate_amending_law(law)
    if not law.meta.so_hieu:
        raise IngestError("Không đọc được số hiệu; chạy lại với --so-hieu")
    directory = Path(raw_root) / slugify_so_hieu(law.meta.so_hieu)
    directory.mkdir(parents=True, exist_ok=True)
    raw_copy = directory / docx_path.name
    if raw_copy.exists() and file_sha256(raw_copy) != ex.sha256:
        raise IngestError(f"{raw_copy} đã có và KHÁC file đầu vào; không ghi đè file gốc. Kiểm tra lại đầu vào.")
    if not raw_copy.exists():
        shutil.copy2(docx_path, raw_copy)
    path = directory / "amending.json"
    sha = save_amending(law, path)
    return StagedAmending(law, flags, directory, path, sha, raw_copy)
