"""Chức năng 2 (src/agent/vu_an.py): từ sự việc vụ án → bản tóm tắt kiểu cáo trạng. Kho thử và chỉ mục giả như test_agent.py; mô hình là LLM giả có kịch bản,
nên không cần Ollama và KHÔNG phản ánh chất lượng thật. Kiểm các hàng rào: Điều ngoài danh sách, khoản không có, trích dẫn bịa, hạ cấp khi thiếu mô hình."""
import json
import re

import pytest

from src.agent.agent import Agent
from src.agent.vu_an import (MIEN_TRU_VU_AN, LLMGiaSoan, PhanTichVuAn, chu_sach, doc_soan, ten_toi, thanh_cao_trang, trich_khop)
from src.index.cau_hoi import LLMError
from src.index.tach_hanh_vi import LLMGiaTach

from test_agent import tao  # noqa: F401
from test_apply_rebuild import env  # noqa: F401  (env là fixture)
from test_index import dung_chi_muc  # noqa: F401
from test_lookup_history import daapdung  # noqa: F401  (daapdung là fixture)

SU_VIEC = ("Khoảng 22 giờ ngày 12/3/2024, Nguyễn Văn A rủ Trần Văn B đến nhà anh H. A và B phá khoá cổng, lấy trộm một chiếc xe máy trị giá 15 triệu đồng. "
           "Sau đó A bán chiếc xe cho Lê Văn C với giá 4 triệu đồng.")
NGAY = "2025-12-31"                                           # trước ngày Điều 4 bị bãi bỏ trong kho thử (xem test_agent)


def dieu_dau(messages) -> str:
    return re.search(r"### Điều (\S+?)\.", messages[-1]["content"]).group(1)


class LLMKichBan:
    """`tra(messages)` trả dict (thành JSON), chuỗi (nguyên văn) hoặc ném lỗi; ghi lại các lần gọi."""

    def __init__(self, tra):
        self.tra, self.schema, self.goi = tra, {}, []

    def hoi(self, messages):
        self.goi.append(messages)
        r = self.tra(messages) if callable(self.tra) else self.tra
        if isinstance(r, Exception):
            raise r
        return r if isinstance(r, str) else json.dumps(r, ensure_ascii=False)


def soan_mot_nguoi(**toi):
    """Kịch bản: một người, một tội ở Điều đầu tiên trong lời nhắc; `toi` ghi đè trường của tội."""
    def tra(messages):
        t = {"dieu": dieu_dau(messages), "khoan": "", "ly_do": "lấy trộm xe máy của người khác", "trich": ["phá khoá cổng, lấy trộm một chiếc xe máy"]} | toi
        return {"tom_tat": "Hai người trộm xe máy rồi bán.", "nguoi": [{"ten": "Nguyễn Văn A", "vai_tro": "người thực hành",
                "hanh_vi": [{"mo_ta": "phá khoá lấy xe", "trich": "phá khoá cổng"}], "toi": [t]}]}
    return LLMKichBan(tra)


def pv(daapdung, tmp_path, **kw):  # noqa: F811
    ag = Agent(tao(daapdung, tmp_path, tach=LLMGiaTach()))
    return PhanTichVuAn(ag, loc_toi_pham=lambda s: True, **kw)        # kho thử có Điều 2–4 nên không lọc theo phần các tội phạm của BLHS


# ------------------------------------------------------------------------------------------------ hàm thuần

def test_trich_khop():
    goc = "khoảng 22 giờ ngày 12/3/2024,  A phá khoá cổng\nlấy trộm xe máy."
    assert trich_khop("Phá khoá cổng lấy trộm xe máy", re.sub(r"\s+", " ", goc))                    # khác khoảng trắng, hoa/thường vẫn khớp
    assert trich_khop("khoảng 22 giờ … lấy trộm xe máy", re.sub(r"\s+", " ", goc))                   # «…» tách mảnh, mỗi mảnh có mặt
    assert not trich_khop("A dùng dao đe doạ chủ nhà", goc) and not trich_khop("", goc) and not trich_khop("…", goc)


def test_ten_toi_va_chu_sach():
    assert ten_toi("Điều 173. Tội trộm cắp tài sản") == "Tội trộm cắp tài sản" and ten_toi("Điều 249a. Tội X") == "Tội X"
    md = "**1.** Người nào phạm tội \\*\\* này :gray[*(sửa đổi bởi Luật 12/2017/QH14)*]\n\n  - a) giá trị từ 2.000.000 đồng"
    assert chu_sach(md) == "1. Người nào phạm tội ** này\n\n  - a) giá trị từ 2.000.000 đồng"


# ------------------------------------------------------------------------------------------------ đường ống

def test_day_du_voi_llm_gia(daapdung, tmp_path):  # noqa: F811
    buoc = []
    kq = pv(daapdung, tmp_path, soan_llm=LLMGiaSoan(), soan_ten="gia").phan_tich(SU_VIEC, ngay=NGAY, bao=buoc.append)
    assert kq.che_do == "day_du" and len(kq.nguoi) == 1 and kq.ung_vien and kq.dieu
    toi = kq.nguoi[0].toi[0]
    assert toi.dieu in {d.so for d in kq.dieu} and toi.ten_toi
    assert kq.so_trich_sai == 0 and not kq.nghiem_trong and kq.nguoi[0].ten_khop is False       # «Người 1» không có trong sự việc: bị đánh dấu
    assert any("không xuất hiện trong sự việc" in x for x in kq.thong_bao)
    assert len(buoc) >= 3 and all(isinstance(b, str) for b in buoc)                              # có báo tiến độ


def test_ket_qua_tot_khong_canh_bao(daapdung, tmp_path):  # noqa: F811
    llm = soan_mot_nguoi()
    kq = pv(daapdung, tmp_path, soan_llm=llm).phan_tich(SU_VIEC, ngay=NGAY)
    assert kq.che_do == "day_du" and kq.so_toi == 1 and kq.so_trich_sai == 0 and kq.nguoi[0].ten_khop
    assert not kq.nghiem_trong and kq.thong_bao == [] and kq.giay >= 0
    nd = llm.goi[0][-1]["content"]
    assert nd.startswith("Sự việc:\n") and "Các Điều có thể liên quan (nguyên văn):" in nd and "### Điều " in nd   # luật lấy từ kho, đưa nguyên văn
    assert ":gray[" not in nd and "\\*" not in nd                                                # ghi chú nguồn và ký tự thoát đã gỡ
    assert llm.schema["properties"]["nguoi"]["items"]["properties"]["toi"]["items"]["properties"]["dieu"]["enum"] == [d.so for d in kq.dieu]
    assert kq.to_dict()["nguoi"][0]["ten"] == "Nguyễn Văn A"                                    # xuất JSON được


def test_trich_bia_bi_danh_dau(daapdung, tmp_path):  # noqa: F811
    kq = pv(daapdung, tmp_path, soan_llm=soan_mot_nguoi(trich=["A dùng dao đe doạ chủ nhà", "phá khoá cổng"])).phan_tich(SU_VIEC, ngay=NGAY)
    can_cu = kq.nguoi[0].toi[0].can_cu
    assert [t.khop for t in can_cu] == [False, True] and kq.so_trich_sai == 1
    assert kq.nghiem_trong and any("KHÔNG có nguyên văn" in x for x in kq.thong_bao)


def test_dieu_ngoai_danh_sach_bi_bo(daapdung, tmp_path):  # noqa: F811
    kq = pv(daapdung, tmp_path, soan_llm=soan_mot_nguoi(dieu="999")).phan_tich(SU_VIEC, ngay=NGAY)
    assert kq.che_do == "chi_dieu" and not kq.nguoi and kq.dieu                                  # không có tội hợp lệ → vẫn trả Điều gợi ý
    assert any("Điều 999 không nằm trong danh sách" in x for x in kq.ky_thuat)
    assert any("không nêu được người nào" in x for x in kq.thong_bao)


def test_khoan_khong_co_bi_bo_nhung_giu_toi(daapdung, tmp_path):  # noqa: F811
    kq = pv(daapdung, tmp_path, soan_llm=soan_mot_nguoi(khoan="Khoản 9")).phan_tich(SU_VIEC, ngay=NGAY)
    assert kq.che_do == "day_du" and kq.nguoi[0].toi[0].khoan == "" and any("không có khoản đó" in x for x in kq.ky_thuat)


def test_khong_co_mo_hinh_soan_chi_goi_y_dieu(daapdung, tmp_path):  # noqa: F811
    kq = pv(daapdung, tmp_path).phan_tich(SU_VIEC, ngay=NGAY)
    assert kq.che_do == "chi_dieu" and not kq.nguoi and kq.dieu and kq.ung_vien
    assert any("Chưa có mô hình soạn" in x for x in kq.thong_bao) and not kq.nghiem_trong


@pytest.mark.parametrize("tra, thong_bao", [(LLMError("không kết nối được Ollama"), "Không gọi được mô hình soạn"),
                                            ("xin chào, đây không phải JSON", "không đúng định dạng"),
                                            ({"tom_tat": "x"}, "không đúng định dạng")])
def test_soan_hong_thi_ha_cap(daapdung, tmp_path, tra, thong_bao):  # noqa: F811
    kq = pv(daapdung, tmp_path, soan_llm=LLMKichBan(tra)).phan_tich(SU_VIEC, ngay=NGAY)
    assert kq.che_do == "chi_dieu" and kq.dieu and any(thong_bao in x for x in kq.thong_bao) and any(x.startswith("soạn:") for x in kq.ky_thuat)


def test_chon_dieu_dung_mo_hinh_va_ha_cap_khi_hong(daapdung, tmp_path):  # noqa: F811
    chon = LLMKichBan({"dieu": ["3"]})
    kq = pv(daapdung, tmp_path, chon_llm=chon, chon_ten="x").phan_tich(SU_VIEC, ngay=NGAY)
    assert kq.da_chon == ["3"] and [d.so for d in kq.dieu] == ["3"] and "Điều ứng viên" in chon.goi[0][-1]["content"]
    kq = pv(daapdung, tmp_path / "b", chon_llm=LLMKichBan(LLMError("hỏng")), chon_ten="x").phan_tich(SU_VIEC, ngay=NGAY, so_dieu=2)
    assert kq.da_chon == [d.so for d in kq.ung_vien][:2] and any("chọn Điều gặp lỗi" in x for x in kq.thong_bao)


def test_qua_ngan_khong_goi_mo_hinh(daapdung, tmp_path):  # noqa: F811
    llm = soan_mot_nguoi()
    kq = pv(daapdung, tmp_path, soan_llm=llm).phan_tich("Anh A trộm xe máy.", ngay=NGAY)
    assert kq.nghiem_trong and not llm.goi and not kq.ung_vien and any("quá ngắn" in x for x in kq.thong_bao)


def test_su_viec_dai_thi_luoc_va_bao(daapdung, tmp_path):  # noqa: F811
    kq = pv(daapdung, tmp_path, soan_llm=soan_mot_nguoi(), cau_hinh={"tu_dau_soan": 10, "tu_cuoi_soan": 5}).phan_tich(SU_VIEC, ngay=NGAY)
    assert any("lược phần giữa" in x for x in kq.thong_bao)


def test_khong_co_dieu_toi_pham_nao(daapdung, tmp_path):  # noqa: F811
    p = pv(daapdung, tmp_path, soan_llm=soan_mot_nguoi())
    p._loc = lambda s: False
    kq = p.phan_tich(SU_VIEC, ngay=NGAY)
    assert kq.nghiem_trong and not kq.ung_vien and any("Không tìm thấy Điều nào" in x for x in kq.thong_bao)


def test_trang_thai_noi_ro_thieu_gi(daapdung, tmp_path):  # noqa: F811
    tt = {t["ten"]: t for t in pv(daapdung, tmp_path).trang_thai()}
    assert tt["Tìm Điều ứng viên"]["ok"] and not tt["Chọn Điều"]["ok"] and not tt["Soạn bản cáo buộc"]["ok"]
    assert "chưa kết nối được Ollama" in tt["Soạn bản cáo buộc"]["mo_ta"]
    assert pv(daapdung, tmp_path / "b", soan_llm=LLMGiaSoan(), soan_ten="gia").trang_thai()[2]["ok"]


# ------------------------------------------------------------------------------------------------ bản văn

def test_thanh_cao_trang(daapdung, tmp_path):  # noqa: F811
    kq = pv(daapdung, tmp_path, soan_llm=soan_mot_nguoi(khoan="1")).phan_tich(SU_VIEC, ngay=NGAY)
    thuan, md = thanh_cao_trang(kq), thanh_cao_trang(kq, md=True)
    assert "1. Nguyễn Văn A (người thực hành)" in thuan and "có dấu hiệu của «" in thuan and "Điều " in thuan and MIEN_TRU_VU_AN in thuan
    assert "**" not in thuan and "**Nguyễn Văn A**" in md and MIEN_TRU_VU_AN not in md
    assert "đã phạm tội" not in thuan                                                            # chỉ nói «có dấu hiệu», không kết luận
    trong = thanh_cao_trang(pv(daapdung, tmp_path / "b").phan_tich(SU_VIEC, ngay=NGAY))
    assert "Chưa soạn được nội dung theo từng người" in trong


def test_doc_soan_chiu_duoc_rao_json_va_khoi_think():
    from src.agent.agent import DieuDayDu
    dd = {"3": DieuDayDu("3", "Điều 3. Tội trộm cắp tài sản", "BLHS (100/2015/QH13)", "2025-12-31", None, None, "**1.** x", "", "")}
    tho = '<think>nghĩ…</think>```json\n{"tom_tat":"t","nguoi":[{"ten":"A","hanh_vi":["đi trộm"],"toi":[{"dieu":"Điều 3","khoan":"1","ly_do":"r","trich":"đi trộm"}]}]}\n```'
    tt, nguoi, luu_y = doc_soan(tho, dd, "A đi trộm xe máy")
    assert tt == "t" and nguoi[0].toi[0].dieu == "3" and nguoi[0].toi[0].khoan == "1" and nguoi[0].toi[0].can_cu[0].khop and nguoi[0].hanh_vi[0].mo_ta == "đi trộm" and not luu_y
