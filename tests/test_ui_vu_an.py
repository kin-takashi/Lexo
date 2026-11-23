"""Giao diện Chức năng 2 (src/ui/app_vu_an.py) chạy bằng streamlit AppTest, không mở trình duyệt, không cần Ollama.
Kho thử như test_ui_tra_cuu.py; LEXO_GIA=1 dùng vector giả, tách giả và LLM soạn giả (kết quả KHÔNG có nghĩa về chất lượng)."""
import sqlite3
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from src.ban_an import chon_dieu as cd  # noqa: E402

from test_apply_rebuild import env  # noqa: E402,F401  (env là fixture)
from test_index import dung_chi_muc  # noqa: E402
from test_lookup_history import daapdung  # noqa: E402,F401  (daapdung là fixture)
from test_vu_an import SU_VIEC  # noqa: E402

APP = str(Path(__file__).resolve().parent.parent / "src" / "ui" / "app_vu_an.py")


@pytest.fixture
def kho_tep(daapdung, tmp_path, monkeypatch):  # noqa: F811
    db = tmp_path / "luat.sqlite"
    dst = sqlite3.connect(db)
    daapdung.c.backup(dst)
    dst.close()
    dung_chi_muc(daapdung, tmp_path)
    monkeypatch.setenv("LEXO_DB", str(db))
    monkeypatch.setenv("LEXO_INDEX", str(tmp_path / "idx.sqlite"))
    monkeypatch.setenv("LEXO_GIA", "1")
    monkeypatch.setattr(cd, "la_dieu_toi_pham", lambda so: True)         # kho thử chỉ có Điều 2–4, không nằm trong phần các tội phạm của BLHS
    return tmp_path


def chay():
    return AppTest.from_file(APP, default_timeout=60).run()


def phan_tich(at, chu=SU_VIEC):
    at.text_area(key="su_viec").set_value(chu)
    at.button(key="phan_tich").click()
    return at.run()


def md(at):
    return "\n".join(m.value for m in at.markdown)


def test_khoi_dong_hien_o_nhap_vi_du_va_trang_thai(kho_tep):
    at = chay()
    assert not at.exception and at.title[0].value == "Lexo · Phân tích vụ án" and not at.error
    assert at.text_area(key="su_viec").value == "" and at.button(key="phan_tich").label == "Phân tích vụ án"
    assert [at.button(key=f"vd{i}").label for i in range(2)] == ["Trộm xe máy rồi bán", "Đánh nhau gây thương tích"]
    side = "\n".join(m.value for m in at.sidebar.markdown)
    assert "Soạn bản cáo buộc" in side and "Chọn Điều" in side and "Tìm Điều ứng viên" in side
    assert any("không phải tư vấn pháp lý" in c.value for c in at.caption)               # lời nhắc chỉ tham khảo luôn có


def test_phan_tich_hien_nguoi_toi_va_nguyen_van(kho_tep):
    at = phan_tich(chay())
    assert not at.exception and not at.error
    assert [m.label for m in at.metric] == ["Người có dấu hiệu phạm tội", "Số tội", "Số Điều đã xét", "Thời gian"] and at.metric[0].value == "1"
    assert [t.label for t in at.tabs] == ["Bản cáo buộc tham khảo", "Theo từng người", "Điều luật liên quan", "Chi tiết kỹ thuật"]
    ht = md(at)
    assert "Bản tóm tắt kiểu cáo trạng" in ht and "có dấu hiệu của" in ht and "Vì sao:" in ht and ":red-badge[" in ht
    assert any(e.label.startswith("Đọc nguyên văn Điều") for e in at.expander)           # đối chiếu được với luật gốc
    assert any(b.label == "Tải bản văn (.txt)" for b in at.get("download_button"))
    assert any("không xuất hiện trong sự việc" in w.value for w in [*at.info, *at.warning])  # LLM giả đặt tên «Người 1»: giao diện phải cảnh báo


def test_vi_du_bam_la_chay(kho_tep):
    at = chay()
    at.button(key="vd0").click()
    at.run()
    assert not at.exception and "Nguyễn Văn A" in at.text_area(key="su_viec").value and at.metric[0].value == "1"


def test_qua_ngan_thi_bao_ro_khong_goi_mo_hinh(kho_tep):
    at = phan_tich(chay(), "Anh A trộm xe máy.")
    assert not at.exception and any("quá ngắn" in w.value for w in at.warning) and not at.metric


def test_xoa_dua_ve_trang_thai_dau(kho_tep):
    at = phan_tich(chay())
    at.button(key="xoa").click()
    at.run()
    assert not at.exception and at.text_area(key="su_viec").value == "" and not at.metric and at.button(key="vd0")


def test_chon_ngay_xay_ra_hanh_vi(kho_tep):
    at = chay()
    at.checkbox(key="dung_ngay").check()
    at.run()
    assert not at.exception and at.date_input(key="ngay_xem")
    at = phan_tich(at)
    assert not at.exception and at.metric[0].value == "1"
