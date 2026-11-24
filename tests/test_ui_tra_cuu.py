"""Giao diện tra cứu (src/ui/app_tra_cuu.py) chạy bằng streamlit AppTest, không mở trình duyệt, không cần Ollama.
Kho thử: bộ luật thử nghiệm của test_lookup_history sao ra file SQLite; LEXO_GIA=1 dùng vector giả và tách giả (kết quả KHÔNG có nghĩa về chất lượng)."""
import sqlite3
from datetime import date
from pathlib import Path

import pytest

pytest.importorskip("streamlit")
from streamlit.testing.v1 import AppTest  # noqa: E402

from test_apply_rebuild import env  # noqa: E402,F401  (env là fixture)
from test_index import dung_chi_muc  # noqa: E402
from test_lookup_history import daapdung  # noqa: E402,F401  (daapdung là fixture)

APP = str(Path(__file__).resolve().parent.parent / "src" / "ui" / "app_tra_cuu.py")
TINH_HUONG = "Anh A trộm cắp tài sản của người khác. Sau đó anh A lừa đảo chiếm đoạt tiền của bà B."


@pytest.fixture
def kho_tep(daapdung, tmp_path, monkeypatch):  # noqa: F811
    db = tmp_path / "luat.sqlite"
    dst = sqlite3.connect(db)
    daapdung.c.backup(dst)
    dst.close()
    dung_chi_muc(daapdung, tmp_path)                                         # ghi tmp_path/idx.sqlite
    monkeypatch.setenv("LEXO_DB", str(db))
    monkeypatch.setenv("LEXO_INDEX", str(tmp_path / "idx.sqlite"))
    monkeypatch.setenv("LEXO_GIA", "1")
    return tmp_path


def chay():
    return AppTest.from_file(APP, default_timeout=60).run()


def hoi(at, cau):
    at.text_area(key="cau_nhap").set_value(cau)
    at.button(key="tra_cuu").click()
    return at.run()


def md(at):
    return "\n".join(m.value for m in at.markdown)


def test_khoi_dong_hien_vi_du_va_trang_thai(kho_tep):
    at = chay()
    assert not at.exception and at.title[0].value == "Lexo" and not at.warning and not at.error
    assert at.button(key="vd0").label == "Điều 173"                         # câu mẫu bấm được
    side = "\n".join(m.value for m in at.sidebar.markdown)
    assert "Kho luật" in side and "Tìm theo mô tả" in side and "Tách hành vi" in side
    assert "chỉ để tham khảo" in at.caption[0].value or any("tham khảo" in c.value for c in at.caption)


def test_tra_dieu(kho_tep):
    at = hoi(chay(), "Điều 2")
    assert not at.exception
    assert any("Điều 2. Nguyên tắc" in s.value for s in at.subheader)
    assert "miễn trách nhiệm hình sự" in md(at)
    assert any(e.label.startswith("Nguồn sửa đổi") for e in at.expander)
    assert any("tham khảo" in c.value for c in at.caption)                  # lời nhắc chỉ tham khảo luôn có


def test_goi_y_chay_cau_ke_tiep(kho_tep):
    at = hoi(chay(), "Điều 2")
    at.button(key="tl_gy0").click()
    at.run()
    assert not at.exception and at.text_area(key="cau_nhap").value == "Lịch sử sửa đổi Điều 2"
    assert "**01/01/2018**" in md(at)


def test_so_sanh_hai_ban(kho_tep):
    at = hoi(chay(), "so sánh Điều 2 từ 31/12/2017 đến 01/01/2018")
    assert not at.exception
    ht = md(at)
    assert "line-through" in ht and "miễn trách nhiệm" in ht and "Các lần sửa đổi có hiệu lực giữa hai ngày" in ht


def test_tinh_huong_hien_tung_hanh_vi_va_doc_nguyen_van(kho_tep):
    at = hoi(chay(), TINH_HUONG)
    assert not at.exception
    ht = md(at)
    assert "#### Hành vi 1" in ht and "#### Hành vi 2" in ht
    assert any(e.label == "Đọc nguyên văn Điều này" for e in at.expander)
    assert any("không phải kết luận về tội danh" in i.value for i in at.info)


def test_ngay_xem_o_thanh_ben(kho_tep):
    at = chay()
    at.sidebar.checkbox(key="dung_ngay").check()
    at.run()
    at.sidebar.date_input(key="ngay_xem").set_value(date(2017, 12, 31))
    at = hoi(at, "Điều 2")
    assert not at.exception and "giảm nhẹ" in md(at) and "miễn" not in md(at).split("Nguồn")[0]


def test_ngoai_pham_vi_la_canh_bao(kho_tep):
    at = hoi(chay(), "Điều 5 BLDS")
    assert not at.exception and any("Bộ luật Dân sự" in w.value for w in at.warning)


def test_loi_bat_ngo_khong_lam_trang_trang(kho_tep, monkeypatch):
    from src.agent.agent import Agent

    def hong(self, *a, **k):
        raise RuntimeError("lỗi giả để thử")
    monkeypatch.setattr(Agent, "hoi", hong)
    at = hoi(chay(), "Điều 2")
    assert any("Có lỗi khi xử lý" in e.value for e in at.error) and len(at.exception) == 1 and "lỗi giả để thử" in at.exception[0].message


def test_thieu_kho_thi_bao_ro_khong_sap(tmp_path, monkeypatch):
    monkeypatch.setenv("LEXO_DB", str(tmp_path / "khong_co.sqlite"))
    monkeypatch.delenv("LEXO_GIA", raising=False)
    at = chay()
    assert not at.exception and any("Chưa có kho luật" in e.value for e in at.error)
