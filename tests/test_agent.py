"""Agent chức năng 1 (src/agent): định tuyến câu hỏi tới công cụ, hạ cấp khi thiếu Ollama, trình bày kết quả.
Kho thử là bộ luật thử nghiệm của test_lookup_history (đã áp lệnh sửa đổi); chỉ mục dùng HashEmbedder, LLM tách dùng LLMGiaTach,
nên không cần Ollama và KHÔNG phản ánh chất lượng thật của mô hình."""
import json

import pytest

from src.agent import y_dinh as yd
from src.agent.agent import MIEN_TRU, Agent, thanh_van_ban
from src.agent.cong_cu import CongCu
from src.index.cau_hoi import LLMError
from src.index.embedder import EmbedError
from src.index.tach_hanh_vi import LLMGiaTach
from src.index.xep_lai import XepLaiError

from test_apply_rebuild import BASE_DATE, D1, D2, D3, P, env  # noqa: F401  (env là fixture)
from test_index import dung_chi_muc  # noqa: F401
from test_lookup_history import daapdung  # noqa: F401  (daapdung là fixture)

TINH_HUONG = "Anh A trộm cắp tài sản của người khác. Sau đó anh A lừa đảo chiếm đoạt tiền của bà B."


def tao(env, tmp_path, *, vec=True, tach=None, xep_lai=None, cau_hinh=None):  # noqa: F811
    idx, emb = dung_chi_muc(env, tmp_path)
    return CongCu(env.c, idx, embedder=emb if vec else None, tach_llm=tach, tach_ten="gia" if tach else None, xep_lai=xep_lai, cau_hinh=cau_hinh)


@pytest.fixture
def ag(daapdung, tmp_path):  # noqa: F811
    return Agent(tao(daapdung, tmp_path, tach=LLMGiaTach()))


# ------------------------------------------------------------------------------------------------ tra Điều

def test_tra_dieu_hien_hanh_kem_nguon_va_khung_hieu_luc(ag):
    tl = ag.hoi("Điều 2")
    assert (tl.loai, tl.trang_thai) == (yd.TRA_DIEU, "ok")
    d = tl.dieu[0]
    assert d.tieu_de == "Điều 2. Nguyên tắc" and "**2.** Người phạm tội tự thú được miễn trách nhiệm hình sự." in d.markdown
    assert "- a) phạt cảnh cáo;" in d.markdown                                   # điểm là gạch đầu dòng
    assert ":gray[" in d.markdown and "Luật số 12/2017/QH14" in d.markdown        # chỗ bị sửa có ghi chú nguồn
    assert "Nguyên tắc" not in d.markdown and not d.markdown.startswith("**Điều")     # tiêu đề do thẻ hiển thị, không lặp lại trong thân
    assert (d.hieu_luc_tu, d.hieu_luc_den) == (D1, None) and len(d.nguon) == 1 and "12/2017/QH14" in d.nguon[0]
    assert tl.goi_y[0] == "Lịch sử sửa đổi Điều 2"
    assert not any("Điều 2" in x and "chưa" in x for x in tl.thong_bao)


def test_tra_dieu_theo_ngay_trong_cau_va_bao_se_co_sua_doi(ag):
    tl = ag.hoi("Điều 2 ngày 31/12/2017")
    d = tl.dieu[0]
    assert "giảm nhẹ" in d.markdown and "miễn" not in d.markdown and tl.ngay == "2017-12-31"
    assert (d.hieu_luc_tu, d.hieu_luc_den) == (BASE_DATE, D1) and not d.nguon
    assert any("Sẽ có sửa đổi hiệu lực từ 01/01/2018" in g for g in d.ghi_chu)
    assert any("01/07/2016" in x and not x.startswith("Lưu ý") for x in tl.thong_bao)    # nhắc ngày hiệu lực chưa đối chiếu nghị quyết hoãn


def test_tra_dieu_ngay_tu_giao_dien_va_cau_uu_tien_hon(ag):
    assert "giảm nhẹ" in ag.hoi("Điều 2", ngay="2017-12-31").dieu[0].markdown                  # ngày mặc định của giao diện
    tl = ag.hoi("Điều 2 ngày 01/01/2018", ngay="2017-12-31")                                  # câu nêu ngày thì theo câu
    assert "miễn" in tl.dieu[0].markdown and tl.ngay == D1


def test_tra_dieu_theo_nam_lay_cuoi_ky_va_bao_sua_doi_trong_ky(ag):
    tl = ag.hoi("Điều 2 năm 2018")
    assert tl.ngay == "2018-12-31" and any("cuối kỳ" in x for x in tl.thong_bao)
    assert any("Trong năm 2018 có sửa đổi hiệu lực từ 01/01/2018" in g for g in tl.dieu[0].ghi_chu)


def test_tra_khoan_va_diem(ag):
    tl = ag.hoi("khoản 2 Điều 2")
    d = tl.dieu[0]
    assert d.pham_vi == "khoản 2" and "tự thú" in d.markdown and "Mọi hành vi" not in d.markdown and "Mọi hành vi" in d.markdown_ca_dieu
    d = ag.hoi("điểm b khoản 1 Điều 2").dieu[0]
    assert d.pham_vi == "điểm b khoản 1" and "phạt tiền từ 10.000.000" in d.markdown and "phạt cảnh cáo" not in d.markdown
    tl = ag.hoi("khoản 9 Điều 2")
    assert tl.dieu[0].pham_vi == "" and any("không có khoản 9" in x for x in tl.thong_bao)    # sai khoản: báo và cho xem cả Điều


def test_tra_nhieu_dieu_va_dieu_khong_co(ag):
    tl = ag.hoi("Điều 2 và Điều 3 và Điều 99")
    assert [d.so for d in tl.dieu] == ["2", "3"] and any("Điều 99 chưa từng có" in x for x in tl.thong_bao)
    tl = ag.hoi("Điều 99")
    assert tl.trang_thai == "khong_co" and not tl.dieu


def test_dieu_da_bai_bo_giai_thich_ly_do(ag):
    tl = ag.hoi("Điều 4 ngày 01/02/2026")
    assert tl.trang_thai == "khong_co" and any("hết hiệu lực từ 01/01/2026" in x for x in tl.thong_bao)
    assert ag.hoi("Điều 4 ngày 31/12/2025").dieu                                              # trước ngày bị bãi bỏ vẫn xem được
    assert ag.hoi("Điều 3a ngày 01/01/2018").trang_thai == "khong_co"                          # Điều thêm sau


def test_lay_dieu_duong_tat(ag):
    d = ag.lay_dieu("2", D1)
    assert d is not None and "miễn" in d.markdown
    assert ag.lay_dieu("4", "2026-02-01") is None and ag.lay_dieu("999") is None


def test_canh_bao_lenh_chua_duyet(daapdung, tmp_path):  # noqa: F811
    daapdung.cmd("sua_doi", {"muc_tieu": [{"duong_dan": P("dieu", "2", "khoan", "1")}]}, tu=D2, noi_dung="1. Chưa duyệt.", trang_thai="cho_duyet")
    ag = Agent(tao(daapdung, tmp_path))
    tl = ag.hoi("Điều 2")
    assert any("CHƯA được duyệt" in x for x in tl.thong_bao) and "Chưa duyệt." not in tl.dieu[0].markdown


# ------------------------------------------------------------------------------------------------ lịch sử, so sánh

def test_lich_su(ag):
    tl = ag.hoi("lịch sử sửa đổi Điều 3")
    assert tl.loai == yd.LICH_SU and [e.ngay for e in tl.lich_su][:2] == [BASE_DATE, D1]
    assert "Ban hành" in tl.lich_su[0].noi_dung and "khoản 1" in tl.lich_su[1].noi_dung and tl.lich_su[1].so_hieu == "12/2017/QH14"
    tl = ag.hoi("lịch sử Điều 3a")                                                              # Điều thêm sau: không có dòng «ban hành»
    assert [e.ngay for e in tl.lich_su] == [D2] and "bổ sung" in tl.lich_su[0].noi_dung
    tl = ag.hoi("lịch sử Điều 5")
    assert len(tl.lich_su) == 1 and any("chưa từng bị sửa đổi" in x for x in tl.thong_bao)
    assert ag.hoi("lịch sử Điều 99").trang_thai == "khong_co"


def test_so_sanh_hai_ngay(ag):
    tl = ag.hoi("so sánh Điều 2 từ 31/12/2017 đến 01/01/2018")
    s = tl.so_sanh
    assert (s.ngay_a, s.ngay_b, s.co_a, s.co_b) == ("2017-12-31", D1, True, True) and s.so_dong_khac >= 1
    assert "giảm nhẹ" in s.html and "miễn trách nhiệm" in s.html and "<span" in s.html and "line-through" in s.html
    assert "-" in s.unified and any(x.startswith("01/01/2018") for x in s.thay_doi)
    tl = ag.hoi("so sánh Điều 2 từ 01/01/2018 đến 01/01/2026")
    assert tl.so_sanh.so_dong_khac == 0 and any("giống nhau" in x for x in tl.thong_bao)


def test_so_sanh_thieu_moc_thi_dung_mac_dinh_va_noi_ro(ag):
    tl = ag.hoi("so sánh Điều 2")                                                                # không nêu mốc: bản lúc hiệu lực với hiện nay
    assert tl.so_sanh.ngay_a == BASE_DATE and tl.so_sanh.so_dong_khac >= 1 and any("không nêu mốc" in x for x in tl.thong_bao)
    tl = ag.hoi("so sánh Điều 2 từ 31/12/2017")                                                  # một mốc: so với hiện nay hoặc ngày giao diện
    assert tl.so_sanh.ngay_a == "2017-12-31" and tl.so_sanh.ngay_b > D3 and any("một mốc" in x for x in tl.thong_bao)
    assert ag.hoi("so sánh Điều 2 từ 31/12/2017", ngay="2018-06-01").so_sanh.ngay_b == "2018-06-01"
    tl = ag.hoi("Điều 2 khác gì bản gốc")
    assert tl.so_sanh.ngay_a == BASE_DATE and tl.so_sanh.so_dong_khac >= 1


def test_so_sanh_dieu_bi_bai_bo_hoac_moi_them(ag):
    tl = ag.hoi("so sánh Điều 4 từ 01/01/2025 đến 01/02/2026")
    s = tl.so_sanh
    assert (s.co_a, s.co_b) == (True, False) and "line-through" in s.html and any("hết hiệu lực" in x for x in tl.thong_bao)
    s = ag.hoi("so sánh Điều 3a từ 01/01/2018 đến 01/08/2025").so_sanh
    assert (s.co_a, s.co_b) == (False, True) and "rgba(46,160,67" in s.html
    assert ag.hoi("so sánh Điều 99").trang_thai == "khong_co"


# ------------------------------------------------------------------------------------------------ quan hệ, chuyển tiếp, phạm vi

def nap_quan_he(env):  # noqa: F811
    for so_hieu, vt, loai, nd in [("12/2017/QH14", "Điều 3", "hieu_luc", "Luật này có hiệu lực từ 01/01/2018."),
                                  ("86/2025/QH15", "Điều 4", "chuyen_tiep", "Quy định chuyển tiếp.")]:
        a = env.c.execute("SELECT id FROM van_ban WHERE so_hieu = ?", (so_hieu,)).fetchone()[0]
        env.c.execute("INSERT INTO quan_he_van_ban (van_ban_a_id, loai_quan_he, van_ban_b_id) VALUES (?, 'sua_doi', ?)", (a, env.vb))
        env.c.execute("INSERT INTO dieu_khoan_van_ban (van_ban_id, loai, vi_tri, noi_dung) VALUES (?, ?, ?, ?)", (a, loai, vt, nd))


def test_quan_he_va_chuyen_tiep(daapdung, tmp_path):  # noqa: F811
    ag = Agent(tao(daapdung, tmp_path))
    assert ag.hoi("Những luật nào đã sửa đổi bộ luật này?").trang_thai == "khong_co"              # chưa nạp quan hệ
    nap_quan_he(daapdung)
    tl = ag.hoi("Những luật nào đã sửa đổi bộ luật này?")
    assert tl.loai == yd.QUAN_HE and [r["so_hieu"] for r in tl.quan_he] == ["12/2017/QH14", "86/2025/QH15"]
    assert all(r["loai_quan_he"] == "sua_doi" and r["huong"] == "tac_dong_len_vb" for r in tl.quan_he)
    tl = ag.hoi("điều khoản chuyển tiếp của các luật sửa đổi")
    assert tl.loai == yd.CHUYEN_TIEP and [(r["so_hieu"], r["loai"]) for r in tl.chuyen_tiep] == [("12/2017/QH14", "hieu_luc"), ("86/2025/QH15", "chuyen_tiep")]
    assert any("KHÔNG tự suy ra" in x for x in tl.thong_bao)


def test_ngoai_pham_vi_tro_giup_trong(ag):
    tl = ag.hoi("Điều 5 BLDS")
    assert tl.trang_thai == "ngoai_pham_vi" and any("Bộ luật Dân sự" in x and "BLTN" in x for x in tl.thong_bao)
    tl = ag.hoi("Điều 5 BLHS")                                                                   # BLHS không có trong kho thử (chỉ có BLTN): báo, không đoán
    assert tl.trang_thai == "khong_co" and any("BLHS" in x for x in tl.thong_bao)
    tl = ag.hoi("xin chào")
    assert tl.trang_thai == "tro_giup" and tl.goi_y == list(yd.VI_DU) and "không đưa ra kết luận" in tl.tom_tat
    assert ag.hoi("").trang_thai == "trong"


# ------------------------------------------------------------------------------------------------ tìm theo mô tả

def test_tim_mo_ta_bang_vector(ag):
    tl = ag.hoi("trộm cắp tài sản")
    assert tl.loai == yd.TIM_MO_TA and tl.ket_qua[0].so == "3" and tl.ket_qua[0].tieu_de == "Điều 3. Tội trộm cắp" and not tl.thong_bao
    assert [k.hang for k in tl.ket_qua] == list(range(1, len(tl.ket_qua) + 1))
    assert tl.goi_y[0] == "Điều 3"
    assert ag.hoi("trộm cắp tài sản", ngay="2017-12-31", k=2).ket_qua[0].so == "3" and len(ag.hoi("trộm cắp tài sản", k=2).ket_qua) == 2


def test_tim_mo_ta_tu_ha_cap_khi_khong_co_vector(daapdung, tmp_path):  # noqa: F811
    ag = Agent(tao(daapdung, tmp_path, vec=False))
    tl = ag.hoi("trộm cắp tài sản")
    assert tl.ket_qua[0].so == "3" and any("từ khoá" in x for x in tl.thong_bao)


def test_tim_mo_ta_tu_ha_cap_khi_embedding_hong_giua_chung(daapdung, tmp_path):  # noqa: F811
    class Hong:
        name = "hash:256"                                                                         # trùng tên để có vector trong chỉ mục, rồi nhúng câu hỏi thì lỗi

        def embed(self, texts):
            raise EmbedError("Ollama đã tắt")
    cc = tao(daapdung, tmp_path)
    cc.embedder = Hong()
    tl = Agent(cc).hoi("trộm cắp tài sản")
    assert tl.ket_qua[0].so == "3" and any("chuyển sang tìm theo từ khoá" in x for x in tl.thong_bao) and any("Ollama đã tắt" in x for x in tl.ky_thuat)


def test_khong_co_chi_muc(daapdung):  # noqa: F811
    tl = Agent(CongCu(daapdung.c, None)).hoi("trộm cắp tài sản")
    assert tl.trang_thai == "khong_co" and any("chỉ mục" in x for x in tl.thong_bao)
    assert Agent(CongCu(daapdung.c, None)).hoi("Điều 2").dieu                                    # tra chính xác không cần chỉ mục


def test_loi_nhac_khi_hoi_ket_luan(ag):
    tl = ag.hoi("trộm cắp tài sản có tội không")
    assert tl.ket_qua and any("không kết luận có phạm tội" in x for x in tl.thong_bao)


def test_xep_lai_doi_thu_tu_va_hong_thi_giu_nguyen(daapdung, tmp_path):  # noqa: F811
    class Dao:
        name = "dao"

        def cham(self, cau_hoi, van_ban):
            return [10.0 * i for i in range(len(van_ban))]                                       # ưu tiên ứng viên đứng cuối

    class Hong:
        name = "hong"

        def cham(self, cau_hoi, van_ban):
            raise XepLaiError("hỏng")
    cc = tao(daapdung, tmp_path, xep_lai=Dao())
    goc = [k.so for k in cc.tim_dieu("trộm cắp tài sản", k=5, xep_lai=False)[0]]
    dao = [k.so for k in cc.tim_dieu("trộm cắp tài sản", k=5, xep_lai=True)[0]]
    assert len(goc) >= 3 and dao == goc[::-1]
    cc._xep_lai = Hong()
    kq, tb, kt = cc.tim_dieu("trộm cắp tài sản", k=5, xep_lai=True)
    assert [k.so for k in kq] == goc and any("xếp lại gặp lỗi" in x for x in tb) and any("hỏng" in x for x in kt)


# ------------------------------------------------------------------------------------------------ tình huống nhiều hành vi

def test_tinh_huong_tach_tung_hanh_vi(ag):
    tl = ag.hoi(TINH_HUONG, ngay="2025-12-31", m=3)                                              # trước ngày Điều 4 (lừa đảo) bị bãi bỏ trong kho thử
    assert tl.loai == yd.TINH_HUONG and tl.da_tach and len(tl.hanh_vi) == 2
    assert tl.hanh_vi[0].mo_ta.startswith("Anh A trộm cắp") and tl.hanh_vi[0].dieu[0].so == "3"
    assert "4" in [k.so for k in tl.hanh_vi[1].dieu] and all(len(h.dieu) <= 3 for h in tl.hanh_vi)
    assert any("không phải kết luận về tội danh" in x for x in tl.thong_bao)
    assert tl.hanh_vi[0].dieu[0].so != tl.hanh_vi[1].dieu[0].so                                  # mỗi hành vi được tìm riêng


def test_tinh_huong_khong_tach_duoc_thi_noi_ro_va_tim_ca_cau(daapdung, tmp_path):  # noqa: F811
    tl = Agent(tao(daapdung, tmp_path, tach=None)).hoi(TINH_HUONG, ngay="2025-12-31")
    assert not tl.da_tach and len(tl.hanh_vi) == 1 and tl.hanh_vi[0].mo_ta == TINH_HUONG and len(tl.hanh_vi[0].dieu) == 5   # 5 Điều khi không tách
    assert any("Chưa kết nối được mô hình tách hành vi" in x for x in tl.thong_bao)
    assert not any("Chưa có Ollama" in x for x in tl.thong_bao)                                  # còn vector nên chưa tệ tới mức đó
    assert not tl.nghiem_trong
    ag2 = Agent(tao(daapdung, tmp_path / "b", vec=False, tach=None))
    tl = ag2.hoi(TINH_HUONG)
    assert any("Chưa có Ollama" in x and "rất kém" in x for x in tl.thong_bao)                   # cả hai cùng tắt: cảnh báo mạnh
    assert tl.nghiem_trong and not any(x.startswith("Đang tìm theo từ khoá") for x in tl.thong_bao)   # không lặp ý với cảnh báo mạnh
    tl = ag2.hoi(TINH_HUONG, tach=False)                                                          # giao diện gửi tach=False khi nút bị khoá
    assert tl.nghiem_trong and not any("Bạn đã tắt" in x for x in tl.thong_bao)                   # không nói sai là người dùng tự tắt


@pytest.mark.parametrize("llm_hoi, ky_thuat", [
    (lambda tn: (_ for _ in ()).throw(LLMError("sập")), "sập"),
    (lambda tn: "xin chào, đây không phải JSON", "không đọc được JSON"),
])
def test_tach_hong_thi_ha_cap(daapdung, tmp_path, llm_hoi, ky_thuat):  # noqa: F811
    class Hong:
        name, seed, nhiet, da_thay_think = "hong", 0, 0.0, False

        def hoi(self, tn):
            return llm_hoi(tn)
    tl = Agent(tao(daapdung, tmp_path, tach=Hong())).hoi(TINH_HUONG)
    assert not tl.da_tach and len(tl.hanh_vi) == 1 and any(ky_thuat in x for x in tl.ky_thuat)
    assert any("tìm theo cả tình huống" in x for x in tl.thong_bao)


def test_tinh_huong_tat_tach_va_thong_bao_khong_lap(daapdung, tmp_path):  # noqa: F811
    cc = tao(daapdung, tmp_path, vec=False, tach=LLMGiaTach())
    tl = Agent(cc).hoi(TINH_HUONG)
    assert tl.da_tach and len(tl.hanh_vi) == 2 and sum("từ khoá" in x for x in tl.thong_bao) == 1     # 2 hành vi, cùng một thông báo hạ cấp: chỉ hiện một lần
    tl = Agent(cc).hoi(TINH_HUONG, tach=False)
    assert not tl.da_tach and len(tl.hanh_vi) == 1 and any("tắt tách hành vi" in x for x in tl.thong_bao)


# ------------------------------------------------------------------------------------------------ công cụ, xuất

def test_trang_thai_va_thong_tin_kho(daapdung, tmp_path):  # noqa: F811
    nap_quan_he(daapdung)
    cc = tao(daapdung, tmp_path, vec=False)
    tt = {t["ten"]: t for t in cc.trang_thai()}
    assert tt["Kho luật"]["ok"] and "luật sửa đổi đã nạp" in tt["Kho luật"]["mo_ta"]
    assert not tt["Tìm theo mô tả"]["ok"] and "từ khoá" in tt["Tìm theo mô tả"]["mo_ta"] and not tt["Tách hành vi"]["ok"]
    info = cc.thong_tin_kho()
    assert info["so_dieu"] >= 4 and [s["so_hieu"] for s in info["sua_doi"]] == ["12/2017/QH14", "86/2025/QH15"]
    assert info["lenh_cho_duyet"] == 0 and isinstance(cc.co_the_xep_lai, bool)
    assert {2015} <= cc.nam_van_ban() and {1985, 1999} <= cc.nam_van_ban()           # năm của bộ luật đã nạp + các bộ luật đã biết nhưng chưa nạp
    vb, loi = cc.van_ban("BLTN", 2015)
    assert vb is not None and loi is None
    assert cc.van_ban("BLTN", 1999)[0] is None and cc.van_ban("XYZ")[0] is None


def test_tra_loi_xuat_json_va_van_ban(ag):
    for cau in ("Điều 2", "lịch sử Điều 3", "so sánh Điều 2 từ 31/12/2017 đến 01/01/2018", "trộm cắp tài sản", TINH_HUONG, "xin chào"):
        tl = ag.hoi(cau)
        d = json.loads(json.dumps(tl.to_dict(), ensure_ascii=False, default=str))
        assert d["loai"] == tl.loai and d["mien_tru"] == MIEN_TRU
        assert MIEN_TRU in thanh_van_ban(tl)
    assert "miễn trách nhiệm hình sự" in thanh_van_ban(ag.hoi("Điều 2"))
    assert "Hành vi:" in thanh_van_ban(ag.hoi(TINH_HUONG))
