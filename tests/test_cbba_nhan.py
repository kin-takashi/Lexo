"""Kiểm thử src/ban_an/cbba_nhan.py và scripts/xu_ly_cbba_blhs.py (gán nhãn + che đáp án cho train / test của cbba_blhs).

Chỉ dùng văn bản GIẢ LẬP (tên hư cấu) lấy từ helper `_ban_an` của tests/test_anle_hf.py; không cần dữ liệu thật, không cần pyarrow.
"""
from __future__ import annotations

import gzip
import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest

from src.ban_an import anle_hf as hf
from src.ban_an import cbba_nhan as nh
from tests.test_anle_hf import _ban_an

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "xu_ly_cbba_blhs.py"
TEN_TOI = ("trộm cắp tài sản", "lừa đảo chiếm đoạt tài sản")


def _dong(ma: str, tap: str, nhom: str | None = None, *, van_ban: str | None = None, cap_ct: str | None = "phuc_tham", **kw) -> dict:
    """Một dòng giống đầu ra của cbba_blhs (khóa «ma» đứng đầu)."""
    return {"ma": ma, "tap": tap, "nhom_vu": nhom or ma, "nam": 2025, "cap_cong_thong_tin": cap_ct,
            "van_ban": _ban_an(**kw) if van_ban is None else van_ban}


def _ghi_gz(path: Path, dong: list[dict]) -> None:
    with gzip.open(path, "wt", encoding="utf-8", newline="\n") as f:
        for d in dong:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")


@pytest.fixture(autouse=True)
def _khoi_tao_sach():
    nh.khoi_tao(())
    yield
    nh.khoi_tao(())


# --------------------------------------------------------------------------------------------------------------------
# đọc dòng, chọn mẫu
# --------------------------------------------------------------------------------------------------------------------
def test_ma_trong_dong():
    assert nh.ma_trong_dong('{"ma": "129952", "tap": "test"}\n') == "129952"
    assert nh.ma_trong_dong('{"ma": "", "tap": "x"}') == ""
    with pytest.raises(ValueError):
        nh.ma_trong_dong('{"tap": "test", "ma": "1"}')


def test_ma_trong_dong_khop_voi_json_loads():
    d = _dong("ab-12", "train")
    assert nh.ma_trong_dong(json.dumps(d, ensure_ascii=False)) == json.loads(json.dumps(d))["ma"]


def test_chon_ma_lay_het():
    cac_ma = [str(i) for i in range(10)]
    assert nh.chon_ma(cac_ma, None, 1) is None
    assert nh.chon_ma(cac_ma, 10, 1) is None
    assert nh.chon_ma(cac_ma, 99, 1) is None


def test_chon_ma_co_dinh_khong_phu_thuoc_thu_tu_va_doi_theo_seed():
    cac_ma = [str(i) for i in range(200)]
    a = nh.chon_ma(cac_ma, 20, 2026)
    assert a is not None and len(a) == 20 and a <= set(cac_ma)
    assert nh.chon_ma(list(reversed(cac_ma)), 20, 2026) == a
    assert nh.chon_ma(cac_ma, 20, 2027) != a


def test_doc_tap_loc_theo_ma(tmp_path):
    p = tmp_path / "x.jsonl.gz"
    _ghi_gz(p, [_dong("1", "train"), _dong("2", "train"), _dong("3", "train")])
    assert [d["ma"] for d in nh.doc_tap(p, None)] == ["1", "2", "3"]
    assert [d["ma"] for d in nh.doc_tap(p, {"2", "9"})] == ["2"]
    assert nh.liet_ke_ma(p) == ["1", "2", "3"]


# --------------------------------------------------------------------------------------------------------------------
# dấu ngắt trang «## Page N»
# --------------------------------------------------------------------------------------------------------------------
def test_bo_dau_trang():
    assert nh.bo_dau_trang("## Page 1\n\nTÒA ÁN\n\nBản án số 1\n\n## Page 2\n\nNỘI DUNG") == "TÒA ÁN\n\nBản án số 1\nNỘI DUNG"
    assert nh.bo_dau_trang("Đề nghị không\n\n## Page 5\n\náp dụng hình phạt bổ sung.") == "Đề nghị không\náp dụng hình phạt bổ sung."
    assert nh.bo_dau_trang("a\n  ## page  12 \n\n\nb") == "a\nb"
    assert nh.bo_dau_trang("không có dấu ngắt\n\ntrang") == "không có dấu ngắt\n\ntrang"
    assert nh.bo_dau_trang("Xem ## Page 5 ở trên\nvà ## Pages") == "Xem ## Page 5 ở trên\nvà ## Pages"
    assert nh.bo_dau_trang("") == ""


def test_bo_dau_trang_thoi_gian_tuyen_tinh():
    van = "x" + " " * 200_000 + "\n" * 200_000 + "## Page 3\n\n" + " \n" * 50_000 + "y"
    t0 = time.perf_counter()
    ra = nh.bo_dau_trang(van)
    assert time.perf_counter() - t0 < 5
    assert ra == "x" + " " * 200_000 + "\ny"


def test_xu_ly_mot_cau_phan_quyet_vat_qua_trang_khong_con_lo():
    su_viec = ("Khoảng 20 giờ ngày 10/8/2024, Nguyễn Văn An lẻn vào nhà anh Trần Văn Bình lấy một chiếc xe máy trị giá 18.000.000 đồng rồi đem bán "
               "lấy tiền tiêu xài cá nhân, sau đó bị người dân phát hiện và bắt giữ cùng tang vật.\n\n"
               "Tại phiên tòa, đại diện Viện kiểm sát nhân dân giữ nguyên quan điểm truy tố. Đề nghị không\n\n## Page 3\n\n"
               "áp dụng hình phạt bổ sung đối với bị cáo. Bị cáo thừa nhận hành vi và xin được giảm nhẹ hình phạt.")
    van = _ban_an(su_viec=su_viec)
    nh.khoi_tao(TEN_TOI)
    b = nh.xu_ly_mot((0, {"ma": "tr", "tap": "train", "nhom_vu": "tr", "cap_cong_thong_tin": "phuc_tham", "van_ban": van}))
    assert b["dung_duoc"], b["ly_do"]
    assert b["lo_nhan_con_lai"] == {}
    assert "áp dụng hình phạt" not in b["dau_vao"].lower() and "## Page" not in b["dau_vao"]
    # đối chứng: không bỏ dấu ngắt trang thì câu bị cắt đôi, lọt qua bộ che và bị bộ dò báo lộ
    b0 = hf.xu_ly({"markdown": van, "doc_name": "tr", "instance_level": "Appellate"}, 0, TEN_TOI)
    assert b0["dung_duoc"] and b0["lo_nhan_con_lai"].get("cau_phan_quyet")


# --------------------------------------------------------------------------------------------------------------------
# cắt phần truy tố / đề nghị của Viện kiểm sát khỏi đầu vào
# --------------------------------------------------------------------------------------------------------------------
_DIEN_BIEN = ("Theo các tài liệu có trong hồ sơ vụ án và diễn biến tại phiên tòa, nội dung vụ án được tóm tắt như sau:\n"
              "Khoảng 20 giờ ngày 10/8/2024, Nguyễn Văn An lẻn vào nhà anh Trần Văn Bình lấy một chiếc xe máy trị giá 18.000.000 đồng rồi đem bán "
              "lấy tiền tiêu xài cá nhân, sau đó bị người dân phát hiện và bắt giữ cùng tang vật. Cơ quan điều tra đã thu giữ chiếc xe máy "
              "và trả lại cho anh Bình, đồng thời lấy lời khai của những người có liên quan đến vụ việc.")
_PHAN_VKS = ("Tại bản cáo trạng số 25/CT-VKS ngày 16/4/2019 của Viện kiểm sát nhân dân huyện X đã truy tố bị cáo Nguyễn Văn An về tội [đã che] theo [đã che].\n"
             "Tại phiên tòa, đại diện Viện kiểm sát giữ nguyên quan điểm truy tố và đề nghị Hội đồng xét xử xử phạt bị cáo 12 tháng tù.\n"
             "Bị cáo thừa nhận hành vi và xin được giảm nhẹ hình phạt.")


def test_dien_bien_du_dai_de_cat():
    assert len(_DIEN_BIEN) > nh.MIN_GIU_TRUOC_MOC


def test_cat_truoc_truy_to_cat_tai_cau_cao_trang():
    t, cat = nh.cat_truoc_truy_to(_DIEN_BIEN + "\n" + _PHAN_VKS)
    assert cat is True and t == _DIEN_BIEN


@pytest.mark.parametrize("mo_dau", ["Viện kiểm sát nhân dân huyện X đã truy tố bị cáo Nguyễn Văn An về tội [đã che] theo [đã che].",
                                    "Tại phiên tòa, đại diện Viện kiểm sát giữ nguyên quan điểm truy tố.",
                                    "Đại diện Viện kiểm sát đề nghị Hội đồng xét xử tuyên bố bị cáo phạm tội.",
                                    "Kiểm sát viên luận tội đối với bị cáo."])
def test_cat_truoc_truy_to_cac_mo_khac(mo_dau):
    t, cat = nh.cat_truoc_truy_to(_DIEN_BIEN + "\n" + mo_dau + "\nBị cáo xin giảm nhẹ.")
    assert cat is True and t == _DIEN_BIEN


def test_cat_truoc_truy_to_cat_o_dau_cau_khi_mo_nam_giua_cau():
    t, cat = nh.cat_truoc_truy_to(_DIEN_BIEN + "\nBản án số 05/2024 của Tòa án nhân dân huyện X và Viện kiểm sát nhân dân huyện X đã truy tố bị cáo về tội [đã che].")
    assert cat is True and t == _DIEN_BIEN


def test_cat_truoc_truy_to_bo_qua_mo_o_dau_van_ban():
    van = ("Theo cáo trạng của Viện kiểm sát nhân dân huyện X, bị cáo bị truy tố về hành vi phạm tội như sau: Khoảng 20 giờ ngày 10/8/2024, Nguyễn Văn An "
           "lẻn vào nhà anh Trần Văn Bình lấy một chiếc xe máy trị giá 18.000.000 đồng rồi đem bán lấy tiền tiêu xài cá nhân, sau đó bị người dân phát hiện, "
           "bắt giữ cùng tang vật và giao cho cơ quan Công an xử lý theo thẩm quyền, tang vật được niêm phong theo đúng quy định của pháp luật hiện hành. ")
    t, cat = nh.cat_truoc_truy_to(van + "Tại phiên tòa, đại diện Viện kiểm sát giữ nguyên quan điểm truy tố.\nBị cáo xin giảm nhẹ.")
    assert cat is True and t == van.rstrip() and "Tại phiên tòa" not in t


def test_cat_truoc_truy_to_khong_co_mo():
    van = _DIEN_BIEN
    assert nh.cat_truoc_truy_to(van) == (van, False)
    assert nh.cat_truoc_truy_to("") == ("", False)
    # «diễn biến tại phiên tòa» (viết thường, giữa câu) không phải mốc
    assert nh.cat_truoc_truy_to(_DIEN_BIEN + " Mọi việc diễn ra như diễn biến tại phiên tòa đã nêu.") [1] is False


def test_cat_phan_vks_tinh_lai_cac_truong_suy_ra():
    nh.khoi_tao(TEN_TOI)
    b = hf.xu_ly({"markdown": _ban_an(su_viec=_DIEN_BIEN + "\n" + _PHAN_VKS), "doc_name": "x", "instance_level": "Appellate"}, 0, TEN_TOI)
    truoc = len(b["dau_vao"])
    assert b["dung_duoc"] and "Viện kiểm sát" in b["dau_vao"]            # trước khi cắt, phần của Viện kiểm sát còn trong đầu vào
    b = nh.cat_phan_vks(b, TEN_TOI)
    assert b["dung_duoc"] and b["cat_phan_vks"] is True and b["so_ky_tu_truoc_cat"] == truoc
    assert len(b["dau_vao"]) < truoc and "Viện kiểm sát" not in b["dau_vao"] and "tháng tù" not in b["dau_vao"]
    assert b["hash_dau_vao"] == hf.hash_van(b["dau_vao"]) and b["lo_nhan_con_lai"] == {}


def test_cat_phan_vks_khong_mo_giu_nguyen_ban_ghi():
    b = hf.xu_ly({"id": "x", "content": _ban_an()}, 0, TEN_TOI)
    truoc = dict(b)
    b = nh.cat_phan_vks(b, TEN_TOI)
    assert b.pop("cat_phan_vks") is False and b == truoc
    loai = hf.xu_ly({"id": "y", "content": "không phải bản án"}, 0, TEN_TOI)
    assert nh.cat_phan_vks(dict(loai), TEN_TOI) == loai


def test_xu_ly_mot_chi_giu_dien_bien_vu_viec():
    nh.khoi_tao(TEN_TOI)
    van = _ban_an(su_viec=_DIEN_BIEN + "\n" + _PHAN_VKS.replace("[đã che]", "“Trộm cắp tài sản”", 1).replace("[đã che]", "khoản 1 Điều 173 Bộ luật hình sự"))
    b = nh.xu_ly_mot((0, {"ma": "vks", "tap": "train", "nhom_vu": "vks", "cap_cong_thong_tin": "phuc_tham", "van_ban": van}))
    assert b["dung_duoc"], b["ly_do"]
    assert b["cat_phan_vks"] is True and b["dieu"] == ["173"]       # nhãn vẫn lấy từ phần Quyết định của Tòa án
    assert b["dau_vao"].endswith("liên quan đến vụ việc.")
    assert not any(x in b["dau_vao"] for x in ("Viện kiểm sát", "cáo trạng", "173", "Trộm cắp tài sản", "xử phạt"))
    tk = nh.thong_ke([b], [], {"train": 1, "test": 0})
    assert tk["van_ban_da_cat_phan_vks"] == 1 and 0 < tk["ti_le_giu_lai_sau_cat_trung_vi"] < 1


# --------------------------------------------------------------------------------------------------------------------
# bổ sung sau anle_hf.xu_ly: câu phán quyết bị ngắt bằng dòng trống, tên tội sau «tội danh», loại văn bản còn lộ nhãn
# --------------------------------------------------------------------------------------------------------------------
_SU_VIEC_NGAT_DONG = ("Khoảng 20 giờ ngày 10/8/2024, Nguyễn Văn An lẻn vào nhà anh Trần Văn Bình lấy một chiếc xe máy trị giá 18.000.000 đồng rồi đem bán "
                      "lấy tiền tiêu xài cá nhân, sau đó bị người dân phát hiện và bắt giữ cùng tang vật.\n"
                      "Tại phiên tòa, đại diện Viện kiểm sát nhân dân giữ nguyên quan điểm truy tố. Đề nghị không\n\n"
                      " áp dụng hình phạt bổ sung đối với bị cáo. Bị cáo thừa nhận hành vi và xin được giảm nhẹ hình phạt.")


def test_bo_cau_phan_quyet_con_sot_sua_cau_ngat_bang_dong_trong():
    van = {"markdown": _ban_an(su_viec=_SU_VIEC_NGAT_DONG), "doc_name": "x", "instance_level": "Appellate"}
    b = hf.xu_ly(van, 0, TEN_TOI)
    assert b["dung_duoc"] and b["lo_nhan_con_lai"].get("cau_phan_quyet"), "đối chứng: anle_hf một lượt để sót câu này"
    b = nh.bo_cau_phan_quyet_con_sot(b, TEN_TOI)
    assert b["dung_duoc"] and b["lo_nhan_con_lai"] == {}
    assert b["cau_phan_quyet_bo_them"] >= 1 and "áp dụng hình phạt" not in b["dau_vao"].lower()
    assert b["hash_dau_vao"] == hf.hash_van(b["dau_vao"])
    assert b["da_che"]["cau_phan_quyet"] >= b["cau_phan_quyet_bo_them"]


def test_bo_cau_phan_quyet_con_sot_khong_dung_vao_ban_ghi_sach():
    nh.khoi_tao(TEN_TOI)
    b = hf.xu_ly({"id": "x", "content": _ban_an()}, 0, TEN_TOI)
    truoc = dict(b)
    assert nh.bo_cau_phan_quyet_con_sot(b, TEN_TOI) == truoc and "cau_phan_quyet_bo_them" not in b
    loai = hf.xu_ly({"id": "y", "content": "không phải bản án"}, 0, TEN_TOI)
    assert nh.bo_cau_phan_quyet_con_sot(dict(loai), TEN_TOI) == loai


@pytest.mark.parametrize("cum", ["về tội danh “Trộm cắp tài sản” theo quy định", "về tội «Trộm cắp tài sản» theo", "về tội danh: Trộm cắp tài sản.",
                                 "về tội ‘Trộm cắp tài sản’", "về tội Trộm cắp tài sản"])
def test_kiem_lo_them_bat_ten_toi_sau_chu_toi(cum):
    b = {"dung_duoc": True, "dau_vao": f"Viện kiểm sát truy tố bị cáo {cum} và đề nghị xét xử.", "toi_danh": ["Trộm cắp tài sản"], "lo_nhan_con_lai": {}}
    assert nh.kiem_lo_them(b)["lo_nhan_con_lai"] == {"ten_toi_sau_chu_toi": 1}


def test_kiem_lo_them_khong_bao_nham():
    b = {"dung_duoc": True, "dau_vao": "Viện kiểm sát truy tố bị cáo về tội [đã che] theo [đã che]. Bị cáo có hành vi trộm cắp tài sản của anh Bình.",
         "toi_danh": ["Trộm cắp tài sản"], "lo_nhan_con_lai": {"dieu_luat": 1}}
    assert nh.kiem_lo_them(b)["lo_nhan_con_lai"] == {"dieu_luat": 1}                    # giữ khóa cũ, không thêm khóa mới
    b = {"dung_duoc": False, "dau_vao": "về tội danh “Trộm cắp tài sản”", "toi_danh": ["Trộm cắp tài sản"], "lo_nhan_con_lai": {}}
    assert nh.kiem_lo_them(b)["lo_nhan_con_lai"] == {}                                 # bản ghi đã bị loại: không đụng


def test_loai_neu_lo():
    b = nh.loai_neu_lo({"dung_duoc": True, "ly_do": None, "lo_nhan_con_lai": {"dieu_luat": 1}})
    assert b["dung_duoc"] is False and b["ly_do"] == nh.LY_DO_LO_NHAN
    b = nh.loai_neu_lo({"dung_duoc": True, "ly_do": None, "lo_nhan_con_lai": {}})
    assert b["dung_duoc"] is True and b["ly_do"] is None
    b = nh.loai_neu_lo({"dung_duoc": False, "ly_do": "thieu_phan", "lo_nhan_con_lai": {"dieu_luat": 1}})
    assert b["ly_do"] == "thieu_phan"


def test_xu_ly_mot_loai_van_ban_con_lo_nhan():
    nh.khoi_tao(TEN_TOI)
    su_viec = ("Khoảng 20 giờ ngày 10/8/2024, Nguyễn Văn An lẻn vào nhà anh Trần Văn Bình lấy một chiếc xe máy trị giá 18.000.000 đồng rồi đem bán "
               "lấy tiền tiêu xài cá nhân, sau đó bị người dân phát hiện và bắt giữ cùng tang vật.\n"
               "Viện kiểm sát truy tố bị cáo về tội danh “Trộm cắp tài sản” và đề nghị xét xử theo quy định của pháp luật.")
    b = nh.xu_ly_mot((0, {"ma": "lo", "tap": "test", "nhom_vu": "lo", "cap_cong_thong_tin": "phuc_tham", "van_ban": _ban_an(su_viec=su_viec)}))
    assert b["dung_duoc"] is False and b["ly_do"] == nh.LY_DO_LO_NHAN
    assert "ten_toi_sau_chu_toi" in b["lo_nhan_con_lai"] and b["tap"] == "test"
    tk = nh.thong_ke([], [b], {"train": 0, "test": 1})
    assert tk["ly_do_loai"] == {nh.LY_DO_LO_NHAN: 1}
    assert tk["bi_loai_vi_lo_nhan_theo_kieu"] == b["lo_nhan_con_lai"]


# --------------------------------------------------------------------------------------------------------------------
# xử lý một văn bản
# --------------------------------------------------------------------------------------------------------------------
def test_xu_ly_mot_giu_tap_nhom_vu_va_che_dap_an():
    nh.khoi_tao(TEN_TOI)
    b = nh.xu_ly_mot((0, _dong("v1", "test", "nhom-A", dieu="173", toi="Trộm cắp tài sản")))
    assert b["dung_duoc"], b["ly_do"]
    assert (b["tap"], b["nhom_vu"], b["nam"], b["ma"]) == ("test", "nhom-A", 2025, "v1")
    assert b["dieu"] == ["173"] and b["toi_danh"]
    assert b["cap"] == "phuc_tham" and b["cap_dataset"] == "Appellate" and b["cap_dataset_khop"] is True
    assert b["lo_nhan_con_lai"] == {}
    assert "Điều 173" not in b["dau_vao"] and "Trộm cắp tài sản" not in b["dau_vao"]
    assert hf.CHE in b["dau_vao"]


def test_xu_ly_mot_cap_cong_thong_tin_la_hoac_thieu():
    nh.khoi_tao(TEN_TOI)
    b = nh.xu_ly_mot((0, _dong("v2", "train", cap_ct=None)))
    assert b["cap_dataset"] is None and b["cap_dataset_khop"] is None
    b = nh.xu_ly_mot((1, _dong("v3", "train", cap_ct="khong_ro")))
    assert b["cap_dataset"] is None


def test_xu_ly_mot_khong_nem_loi_va_loai_van_ban_ngan():
    nh.khoi_tao(TEN_TOI)
    b = nh.xu_ly_mot((0, _dong("rac", "train", van_ban="Chỉ là một đoạn văn không phải bản án.")))
    assert b["dung_duoc"] is False and b["ly_do"]
    assert (b["tap"], b["nhom_vu"]) == ("train", "rac")


def test_xu_ly_mot_nhan_dieu_khac_nhau_theo_van_ban():
    nh.khoi_tao(TEN_TOI)
    b = nh.xu_ly_mot((0, _dong("v4", "train", dieu="174", toi="Lừa đảo chiếm đoạt tài sản")))
    assert b["dung_duoc"] and b["dieu"] == ["174"]


# --------------------------------------------------------------------------------------------------------------------
# thống kê, ghi
# --------------------------------------------------------------------------------------------------------------------
def _hai_bang_ghi():
    nh.khoi_tao(TEN_TOI)
    rows = [_dong("a", "train", dieu="173"), _dong("b", "train", dieu="174", toi="Lừa đảo chiếm đoạt tài sản"),
            _dong("c", "test", dieu="173"), _dong("d", "test", van_ban="không phải bản án")]
    kq = [nh.xu_ly_mot((i, r)) for i, r in enumerate(rows)]
    return [b for b in kq if b["dung_duoc"]], [b for b in kq if not b["dung_duoc"]]


def test_thong_ke():
    ban_ghi, loai = _hai_bang_ghi()
    tk = nh.thong_ke(ban_ghi, loai, {"train": 2, "test": 2})
    assert tk["da_xu_ly"] == 4 and tk["dung_duoc"] == 3 and tk["ti_le_dung_duoc"] == 0.75
    assert tk["dung_duoc_theo_tap"] == {"train": 2, "test": 1}
    assert tk["so_dieu_khac_nhau"] == 2
    assert tk["so_dieu_chi_o_train"] == 1 and tk["dieu_chi_o_test"] == []
    assert sum(tk["ly_do_loai"].values()) == 1
    assert tk["van_ban_con_lo_nhan"] == 0


def test_thong_ke_rong_khong_chia_cho_khong():
    tk = nh.thong_ke([], [], {"train": 0, "test": 0})
    assert tk["ti_le_dung_duoc"] is None and tk["dung_duoc"] == 0


def test_ghi_jsonl_dung_cot(tmp_path):
    ban_ghi, _ = _hai_bang_ghi()
    p = tmp_path / "t.jsonl"
    nh.ghi_jsonl(p, ban_ghi)
    dong = [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines()]
    assert len(dong) == len(ban_ghi)
    assert all(tuple(d) == nh.COT_JSONL for d in dong)


def test_cot_jsonl_cung_cot_voi_xu_ly_anle_hf():
    spec = importlib.util.spec_from_file_location("xu_ly_anle_hf_cho_test", ROOT / "scripts" / "xu_ly_anle_hf.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert tuple(mod.COT_JSONL) == nh.COT_JSONL


# --------------------------------------------------------------------------------------------------------------------
# script đầu-cuối
# --------------------------------------------------------------------------------------------------------------------
def _nap_script(monkeypatch):
    spec = importlib.util.spec_from_file_location("xu_ly_cbba_blhs_cho_test", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(hf, "ten_toi_tu_luat", lambda *_a, **_k: list(TEN_TOI))
    return mod


def _chay(mod, monkeypatch, *args: str) -> int:
    monkeypatch.setattr(sys, "argv", ["xu_ly_cbba_blhs.py", *args])
    return mod.main()


@pytest.fixture
def thu_muc_vao(tmp_path):
    vao = tmp_path / "vao"
    vao.mkdir()
    _ghi_gz(vao / "train.jsonl.gz", [_dong(f"t{i}", "train", dieu="173" if i % 2 else "174",
                                           toi="Trộm cắp tài sản" if i % 2 else "Lừa đảo chiếm đoạt tài sản") for i in range(6)]
            + [_dong("tr-rac", "train", van_ban="không phải bản án")])
    _ghi_gz(vao / "test.jsonl.gz", [_dong(f"s{i}", "test") for i in range(3)])
    luat = tmp_path / "luat.sqlite"
    luat.write_bytes(b"")
    return vao, luat


def test_script_dau_cuoi(thu_muc_vao, tmp_path, monkeypatch, capsys):
    vao, luat = thu_muc_vao
    mod = _nap_script(monkeypatch)
    ra = tmp_path / "ra"
    assert _chay(mod, monkeypatch, "--vao", str(vao), "--ra", str(ra), "--luat", str(luat)) == 0
    capsys.readouterr()
    tr = [json.loads(x) for x in (ra / "train.jsonl").read_text(encoding="utf-8").splitlines()]
    te = [json.loads(x) for x in (ra / "test.jsonl").read_text(encoding="utf-8").splitlines()]
    assert len(tr) == 6 and len(te) == 3
    assert {d["tap"] for d in tr} == {"train"} and {d["tap"] for d in te} == {"test"}
    assert all(tuple(d) == nh.COT_JSONL for d in tr + te)
    assert {d["ma"] for d in tr}.isdisjoint({d["ma"] for d in te})
    assert all(d["nhom_vu"] == d["ma"] for d in tr + te)
    assert (ra / "loai_bo.tsv").read_text(encoding="utf-8").startswith("tr-rac\t")
    tt = json.loads((ra / "tom_tat_nhan.json").read_text(encoding="utf-8"))
    assert tt["thong_ke"]["dung_duoc"] == 9 and tt["thong_ke"]["da_xu_ly"] == 10
    assert tt["thong_ke"]["van_ban_con_lo_nhan"] == 0
    assert set(tt["sha256_ma_ra"]) == {"train", "test"} and set(tt["nguon"]["sha256_ma_vao"]) == {"train", "test"}


def test_script_chay_lai_cho_cung_noi_dung(thu_muc_vao, tmp_path, monkeypatch):
    vao, luat = thu_muc_vao
    mod = _nap_script(monkeypatch)
    a, b = tmp_path / "a", tmp_path / "b"
    assert _chay(mod, monkeypatch, "--vao", str(vao), "--ra", str(a), "--luat", str(luat)) == 0
    assert _chay(mod, monkeypatch, "--vao", str(vao), "--ra", str(b), "--luat", str(luat)) == 0
    for ten in ("train.jsonl", "test.jsonl", "loai_bo.tsv", "tom_tat_nhan.json"):
        assert (a / ten).read_bytes() == (b / ten).read_bytes(), ten


def test_script_song_song_cho_cung_ket_qua_voi_mot_tien_trinh(thu_muc_vao, tmp_path, monkeypatch):
    vao, luat = thu_muc_vao
    mod = _nap_script(monkeypatch)
    a, b = tmp_path / "a", tmp_path / "b"
    assert _chay(mod, monkeypatch, "--vao", str(vao), "--ra", str(a), "--luat", str(luat)) == 0
    assert _chay(mod, monkeypatch, "--vao", str(vao), "--ra", str(b), "--luat", str(luat), "--so-tien-trinh", "2") == 0
    for ten in ("train.jsonl", "test.jsonl", "loai_bo.tsv"):
        assert (a / ten).read_bytes() == (b / ten).read_bytes(), ten


def test_script_gioi_han_moi_tap(thu_muc_vao, tmp_path, monkeypatch):
    vao, luat = thu_muc_vao
    mod = _nap_script(monkeypatch)
    ra = tmp_path / "ra"
    assert _chay(mod, monkeypatch, "--vao", str(vao), "--ra", str(ra), "--luat", str(luat), "--gioi-han", "2") == 0
    tt = json.loads((ra / "tom_tat_nhan.json").read_text(encoding="utf-8"))
    assert tt["thong_ke"]["dau_vao"] == {"train": 2, "test": 2}
    assert tt["thong_ke"]["da_xu_ly"] == 4
    tr_mot = {json.loads(x)["ma"] for x in (ra / "train.jsonl").read_text(encoding="utf-8").splitlines()}
    ra2 = tmp_path / "ra2"
    assert _chay(mod, monkeypatch, "--vao", str(vao), "--ra", str(ra2), "--luat", str(luat), "--gioi-han", "2") == 0
    tr_hai = {json.loads(x)["ma"] for x in (ra2 / "train.jsonl").read_text(encoding="utf-8").splitlines()}
    assert tr_mot == tr_hai


def test_script_loc_theo_cap(thu_muc_vao, tmp_path, monkeypatch):
    vao, luat = thu_muc_vao
    mod = _nap_script(monkeypatch)
    ra = tmp_path / "ra"
    assert _chay(mod, monkeypatch, "--vao", str(vao), "--ra", str(ra), "--luat", str(luat), "--cap", "so_tham") == 0
    assert (ra / "train.jsonl").read_text(encoding="utf-8") == "" and (ra / "test.jsonl").read_text(encoding="utf-8") == ""
    ly_do = {x.split("\t")[1] for x in (ra / "loai_bo.tsv").read_text(encoding="utf-8").splitlines()}
    assert "cap_khong_giu" in ly_do
    ra2 = tmp_path / "ra2"
    assert _chay(mod, monkeypatch, "--vao", str(vao), "--ra", str(ra2), "--luat", str(luat), "--cap", "phuc_tham,so_tham") == 0
    assert len((ra2 / "train.jsonl").read_text(encoding="utf-8").splitlines()) == 6


def test_nam_ban_an():
    assert nh.nam_ban_an({"ngay": "2017-11-30", "nam": 2019}) == 2017           # ngày trong văn bản được ưu tiên
    assert nh.nam_ban_an({"ngay": None, "nam": 2019}) == 2019
    assert nh.nam_ban_an({"ngay": "không phải ngày", "nam": "2020"}) == 2020
    assert nh.nam_ban_an({"ngay": None, "nam": None}) is None
    assert nh.nam_ban_an({}) is None


def test_loai_truoc_nam():
    def b(**kw):
        return {"dung_duoc": True, "ly_do": None, **kw}
    x = nh.loai_truoc_nam(b(ngay="2017-11-30"))
    assert x["dung_duoc"] is False and x["ly_do"] == nh.LY_DO_TRUOC_NAM
    assert nh.loai_truoc_nam(b(ngay="2018-01-01"))["dung_duoc"] is True
    assert nh.loai_truoc_nam(b(ngay=None, nam=2016))["dung_duoc"] is False
    assert nh.loai_truoc_nam(b(ngay=None, nam=None))["dung_duoc"] is True          # không rõ năm: giữ
    assert nh.loai_truoc_nam(b(ngay="2010-01-01"), 0)["dung_duoc"] is True          # 0 = tắt
    assert nh.loai_truoc_nam(b(ngay="2010-01-01"), None)["dung_duoc"] is True
    thieu = nh.loai_truoc_nam({"dung_duoc": False, "ly_do": "thieu_phan", "ngay": "2010-01-01"})
    assert thieu["ly_do"] == "thieu_phan"                                          # lý do loại đầu tiên được giữ


def test_script_bo_ban_an_truoc_2018(tmp_path, monkeypatch):
    vao = tmp_path / "vao"
    vao.mkdir()
    cu = _dong("cu1", "train", van_ban=_ban_an().replace("03/02/2025", "03/02/2016"))
    cu["nam"] = 2016
    _ghi_gz(vao / "train.jsonl.gz", [cu, _dong("moi1", "train")])
    _ghi_gz(vao / "test.jsonl.gz", [_dong("moi2", "test")])
    luat = tmp_path / "luat.sqlite"
    luat.write_bytes(b"")
    mod = _nap_script(monkeypatch)
    base = ["--vao", str(vao), "--luat", str(luat)]
    ra = tmp_path / "ra"
    assert _chay(mod, monkeypatch, *base, "--ra", str(ra)) == 0
    assert {json.loads(x)["ma"] for x in (ra / "train.jsonl").read_text(encoding="utf-8").splitlines()} == {"moi1"}
    assert (ra / "loai_bo.tsv").read_text(encoding="utf-8").strip() == f"cu1\t{nh.LY_DO_TRUOC_NAM}"
    ra2 = tmp_path / "ra2"
    assert _chay(mod, monkeypatch, *base, "--ra", str(ra2), "--tu-nam", "0") == 0
    assert {json.loads(x)["ma"] for x in (ra2 / "train.jsonl").read_text(encoding="utf-8").splitlines()} == {"cu1", "moi1"}


def test_script_tham_so_sai(thu_muc_vao, tmp_path, monkeypatch, capsys):
    vao, luat = thu_muc_vao
    mod = _nap_script(monkeypatch)
    ra = tmp_path / "ra"
    base = ["--vao", str(vao), "--ra", str(ra), "--luat", str(luat)]
    assert _chay(mod, monkeypatch, *base, "--cap", "khong_co_cap_nay") == 1
    assert _chay(mod, monkeypatch, *base, "--so-tien-trinh", "0") == 1
    assert _chay(mod, monkeypatch, "--vao", str(tmp_path / "khong_co"), "--ra", str(ra), "--luat", str(luat)) == 1
    assert _chay(mod, monkeypatch, "--vao", str(vao), "--ra", str(ra), "--luat", str(tmp_path / "khong_co.sqlite")) == 1
    assert not ra.exists()
    assert "[LỖI]" in capsys.readouterr().out


def test_script_thoat_1_khi_con_lo_nhan(thu_muc_vao, tmp_path, monkeypatch):
    vao, luat = thu_muc_vao
    mod = _nap_script(monkeypatch)
    xu_ly_that = nh.xu_ly_mot

    def lo(args):
        b = xu_ly_that(args)
        if b["dung_duoc"]:
            b["lo_nhan_con_lai"] = {"dieu_luat": 1}
        return b

    monkeypatch.setattr(nh, "xu_ly_mot", lo)
    assert _chay(mod, monkeypatch, "--vao", str(vao), "--ra", str(tmp_path / "ra"), "--luat", str(luat)) == 1
