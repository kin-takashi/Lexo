"""Chạy thử giao diện duyệt bằng streamlit AppTest (không mở trình duyệt)."""
import json
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from src.ingest.base_law import ingest_base_law, stage_base_law  # noqa: E402
from src.review.base_law_review import blocking_problems, file_sha256, flag_key, load_parsed, load_review  # noqa: E402
from src.review.base_law_view import sample_dieu  # noqa: E402
from src.store import connect, init_db  # noqa: E402
from src.validate.base_law import CANH_BAO, LOI  # noqa: E402
from tests.test_ingest_lookup import LINES, build_docx  # noqa: E402

APP = str(Path(__file__).resolve().parent.parent / "src" / "review" / "app_base_law.py")


@pytest.fixture
def raw_with_defects(tmp_path, monkeypatch):
    lines = list(LINES)
    lines.insert(lines.index("b) bảo vệ quyền con người.") + 1, "d) nhảy chữ cái;")        # điểm d sau b: LỖI
    lines.insert(lines.index("Chương II") + 2, "1. Khoản lạc ngoài Điều")                    # CẢNH BÁO
    raw = tmp_path / "raw"
    st = stage_base_law(build_docx(tmp_path / "BLTN.docx", lines), raw, ten_viet_tat="BLTN")
    monkeypatch.setenv("LEXO_RAW_DIR", str(raw))
    return st


def run_app():
    return AppTest.from_file(APP, default_timeout=60).run()


def test_app_renders_and_blocks_until_everything_is_done(raw_with_defects):
    st = raw_with_defects
    at = run_app()
    assert not at.exception
    assert at.button(key="duyet").disabled                               # còn lỗi, cảnh báo, mẫu, tên
    err = next(f for f in st.flags if f.level == LOI)
    warn = next(f for f in st.flags if f.level == CANH_BAO)
    at.text_input(key=f"mien::{flag_key(err)}").set_value("lỗi cố ý trong dữ liệu thử").run()
    assert at.button(key="duyet").disabled
    at.checkbox(key=f"xem::{flag_key(warn)}").set_value(True).run()
    law = load_parsed(st.parsed_path)
    for k in sample_dieu(law):
        at.checkbox(key=f"mau::{k}").set_value(True).run()
    assert at.button(key="duyet").disabled                               # vẫn thiếu tên người duyệt
    at.text_input(key="nguoi_duyet").set_value("Người duyệt thử").run()
    assert not at.button(key="duyet").disabled
    at.button(key="duyet").click().run()
    assert not at.exception

    review = load_review(st.directory / "review.json")
    assert review["da_duyet"] and review["nguoi_duyet"] == "Người duyệt thử"
    assert blocking_problems(law, review, file_sha256(st.parsed_path)) == []
    conn = connect()
    init_db(conn)
    assert ingest_base_law(conn, st.directory)["so_loi_mien"] == 1       # review do giao diện ghi nạp được


def test_app_draft_is_saved_and_restored(raw_with_defects):
    st = raw_with_defects
    at = run_app()
    at.text_input(key="nguoi_duyet").set_value("Nháp").run()
    at.button(key="luu_nhap").click().run()
    review = load_review(st.directory / "review.json")
    assert review["da_duyet"] is False and review["nguoi_duyet"] == "Nháp"
    at2 = run_app()                                                     # phiên mới đọc lại nháp
    assert at2.text_input(key="nguoi_duyet").value == "Nháp"


def test_app_ignores_stale_review(raw_with_defects):
    st = raw_with_defects
    at = run_app()
    at.text_input(key="nguoi_duyet").set_value("Cũ").run()
    at.button(key="luu_nhap").click().run()
    path = st.directory / "review.json"
    r = json.loads(path.read_text(encoding="utf-8"))
    r["parsed_sha256"] = "0" * 64
    path.write_text(json.dumps(r), encoding="utf-8")
    at2 = run_app()
    assert not at2.exception and at2.text_input(key="nguoi_duyet").value == ""


def test_app_with_no_documents(tmp_path, monkeypatch):
    monkeypatch.setenv("LEXO_RAW_DIR", str(tmp_path / "trong"))
    at = run_app()
    assert not at.exception and any("parse_base_law.py" in i.value for i in at.info)
