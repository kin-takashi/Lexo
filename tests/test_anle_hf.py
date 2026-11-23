"""Kiểm thử src/ban_an/anle_hf.py (dataset tmquan/anle-toaan-gov-vn -> tập train / test «sự việc -> Điều BLHS»).

Hai nhóm:
  * văn bản GIẢ LẬP (tên hư cấu, tự viết) - luôn chạy;
  * file parquet thật ở raw/anle/ (kể cả thư mục con) và 10 bản án ở inbox/ho_so_vu_an_txt/ - chỉ chạy khi có (cả hai thư mục bị git-ignore).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from src.ban_an import anle_hf as hf
from src.ban_an.tach import tach

ROOT = Path(__file__).resolve().parents[1]
PARQUET = hf.tim_parquet(ROOT / "raw" / "anle")
THU_MUC_THAT = ROOT / "inbox" / "ho_so_vu_an_txt"


def _ban_an(*, so: str = "12/2025/HS-PT", so_tham: str = "05/2024/HS-ST", ket_qua: str = "giu_nguyen",
            dieu: str = "173", toi: str = "Trộm cắp tài sản", bo_luat_cu: bool = False, su_viec: str | None = None) -> str:
    su_viec = su_viec or ("Khoảng 20 giờ ngày 10/8/2024, Nguyễn Văn An (sinh ngày 02/03/1995) lẻn vào nhà anh Trần Văn Bình lấy một chiếc "
                          "xe máy trị giá 18.000.000 đồng rồi đem bán, số điện thoại liên lạc 0912345678.\n"
                          f"Cáo trạng truy tố bị cáo về tội “{toi}” theo khoản 1 Điều {dieu} Bộ luật hình sự.")
    bl = "Bộ luật hình sự năm 1999" if bo_luat_cu else "Bộ luật hình sự"
    qd_cap_tren = {
        "giu_nguyen": f"Không chấp nhận kháng cáo của bị cáo Nguyễn Văn An. Giữ nguyên Bản án hình sự sơ thẩm số {so_tham}.",
        "sua": f"Chấp nhận kháng cáo của bị cáo. Sửa Bản án hình sự sơ thẩm số {so_tham}.\nÁp dụng khoản 1 Điều {dieu}; "
               f"điểm s khoản 1 Điều 51; Điều 38 của {bl}; Xử phạt bị cáo Nguyễn Văn An 9 (chín) tháng tù về tội “{toi}”.",
        "huy": f"Hủy Bản án hình sự sơ thẩm số {so_tham} để điều tra lại.",
    }[ket_qua]
    return f"""TÒA ÁN NHÂN DÂN TỈNH XYZ
CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM

Bản án số: {so}
Ngày: 03/02/2025

NHÂN DANH NƯỚC CỘNG HÒA XÃ HỘI CHỦ NGHĨA VIỆT NAM
Bị cáo có kháng cáo: Nguyễn Văn An.
NỘI DUNG VỤ ÁN:
{su_viec}
Tại Bản án hình sự sơ thẩm số {so_tham} ngày 12/12/2024, Tòa án nhân dân huyện ABC quyết định:
Áp dụng khoản 1 Điều {dieu}; điểm s khoản 1 Điều 51; Điều 38 {bl}. Xử phạt bị cáo Nguyễn Văn An 12 (mười hai) tháng tù
về tội “{toi}”.
Ngày 20/12/2024, bị cáo Nguyễn Văn An có đơn kháng cáo xin giảm nhẹ hình phạt.
NHẬN ĐỊNH CỦA TÒA ÁN:
[1] Đơn kháng cáo của bị cáo Nguyễn Văn An làm trong thời hạn luật định nên hợp lệ, được xem xét theo thủ tục phúc thẩm.
[2] Xét kháng cáo: Tòa án cấp sơ thẩm đã đánh giá đúng tính chất, mức độ hành vi phạm tội và nhân thân của bị cáo.
QUYẾT ĐỊNH:
Căn cứ điểm a khoản 1 Điều 355, Điều 356 Bộ luật Tố tụng hình sự;
{qd_cap_tren}
Bản án phúc thẩm có hiệu lực pháp luật kể từ ngày tuyên án.
Nơi nhận:
- VKSND tỉnh XYZ;
"""


def _ban_ghi(ma: str, **kw) -> dict:
    return hf.xu_ly({"id": ma, "content": _ban_an(**kw)})


# --------------------------------------------------------------------------------------------------------------------
# 1. lọc hình sự
# --------------------------------------------------------------------------------------------------------------------
def test_la_hinh_su_theo_truong_loai_an():
    assert hf.la_hinh_su({"case_type": "Hình sự", "content": ""})
    assert not hf.la_hinh_su({"case_type": "Dân sự", "content": "Bản án số: 12/2025/HS-PT"})


def test_la_hinh_su_theo_so_ban_an_khi_khong_co_truong_loai():
    assert hf.la_hinh_su({"content": _ban_an()})
    assert not hf.la_hinh_su({"content": "TÒA ÁN NHÂN DÂN TỈNH XYZ\nBản án số: 07/2025/DS-PT\nV/v tranh chấp hợp đồng"})


# --------------------------------------------------------------------------------------------------------------------
# 2. nhãn dùng được
# --------------------------------------------------------------------------------------------------------------------
def test_dieu_toi_pham_chi_lay_phan_cac_toi_pham_cua_blhs():
    dc = [{"bo_luat": "hinh_su", "dieu": [{"dieu": 173, "chu": None}, {"dieu": 51, "chu": None}, {"dieu": 217, "chu": "a"}]},
          {"bo_luat": "tttt_hinh_su", "dieu": [{"dieu": 355, "chu": None}]}]
    assert hf.dieu_toi_pham(dc) == ["173", "217a"]


def test_giu_nguyen_lay_nhan_tu_doan_chep_so_tham():
    b = _ban_ghi("a")
    assert b["dung_duoc"] and b["nguon_nhan"] == "so_tham_trich"
    assert b["dieu"] == ["173"] and b["toi_danh"] == ["Trộm cắp tài sản"]


def test_sua_an_lay_nhan_tu_quyet_dinh_cap_tren():
    b = _ban_ghi("a", ket_qua="sua", dieu="134", toi="Cố ý gây thương tích")
    assert b["dung_duoc"] and b["nguon_nhan"] == "quyet_dinh_cap_tren" and b["dieu"] == ["134"]


def test_huy_an_bi_loai_vi_chua_co_nhan_cuoi():
    b = _ban_ghi("a", ket_qua="huy")
    assert not b["dung_duoc"] and b["ly_do"] == "nguon_nhan_khong_co_nhan_cuoi"


def test_nhac_blhs_1999_o_phan_nhan_bi_loai():
    b = _ban_ghi("a", ket_qua="sua", bo_luat_cu=True)
    assert not b["dung_duoc"] and b["ly_do"] == "nhac_blhs_1999" and b["nhac_blhs_1999"]


def test_danh_gia_khong_co_dieu_toi_pham():
    kq = tach(_ban_an(dieu="51"))
    assert hf.danh_gia(kq)["ly_do"] == "khong_co_dieu_toi_pham"


def test_cap_lay_tu_so_ban_an_khong_lay_truong_dataset():
    b = hf.xu_ly({"content": _ban_an(), "instance_level": "Sơ thẩm"})
    assert b["cap"] == "phuc_tham" and b["cap_dataset"] == "Sơ thẩm"


# --------------------------------------------------------------------------------------------------------------------
# 3. che đáp án
# --------------------------------------------------------------------------------------------------------------------
def test_che_toi_danh_dieu_luat_va_du_lieu_ca_nhan():
    b = _ban_ghi("a")
    t = b["dau_vao"]
    assert "Trộm cắp tài sản" not in t and "Điều 173" not in t
    assert "02/03/1995" not in t and "0912345678" not in t
    assert "18.000.000 đồng" in t and "xe máy" in t            # giữ nguyên tình tiết của vụ án
    assert b["lo_nhan_con_lai"] == {}
    assert b["ro_ri_truoc_che"] and b["ro_ri_sau_che"].get("truy_to")   # chữ «truy tố» còn, nhưng không còn tội / Điều


def test_che_nhieu_dang_dan_chieu():
    t, dem = hf.che_dap_an("bị truy tố theo điểm a, b khoản 2 Điều 134; điểm s khoản 1 Điều 51 của Bộ luật Hình sự năm 2015 "
                           "(sửa đổi, bổ sung năm 2017). Sau đó phạm tội trộm cắp tài sản theo Điều 173.", ["134", "173"], ["Trộm cắp tài sản"])
    assert t == "bị truy tố theo [đã che]. Sau đó phạm tội [đã che] theo [đã che]."
    assert dem == {"dan_chieu_blhs": 1, "toi_danh_tran": 1, "dieu_le": 1}


def test_che_khong_dung_vao_cum_khong_phai_dan_chieu():
    van = "Cơ quan điều tra Công an huyện thu giữ 150000000 đồng và khoản tiền 2.000.000 đồng."
    assert hf.che_dap_an(van, ["173"], ["Trộm cắp tài sản"]) == (van, {})


def test_che_dieu_co_chu():
    t, _ = hf.che_dap_an("hành vi quy định tại Điều 217a BLHS, khác Điều 2170", ["217a"], [])
    assert "217a" not in t and "Điều 2170" in t


def test_che_chu_va_so_bi_vo_khi_trich_pdf():
    t, _ = hf.che_dap_an("Căn cứ vào khoản 1 Đi ều 1 41 c ủa B ộ luật H ình sự để truy tố bị cáo.", ["141"], [])
    assert "41" not in t and hf.con_lo(t, ["141"], []) == {}


def test_bo_cau_phan_quyet_giu_cau_su_viec():
    van = ("Ngày 05/01/2024 bị cáo lấy chiếc xe của anh B. Tòa án huyện X quyết định: Tuyên bố bị cáo A phạm tội [đã che].\n"
           "Áp dụng [đã che]; Xử phạt bị cáo A 02 năm tù. Kiểm sát viên đề nghị Hội đồng xét xử xử phạt bị cáo từ 2 đến 3 năm tù.\n"
           "Căn cứ vào các tài liệu có trong hồ sơ, bị cáo đã bán xe. Ngày 6/1 Thanh tra ra Quyết định xử\nphạt vi phạm hành chính đối với C.")
    t, n = hf.bo_cau_phan_quyet(van)
    assert n == 3
    assert "Ngày 05/01/2024 bị cáo lấy chiếc xe của anh B." in t and "Căn cứ vào các tài liệu" in t and "vi phạm hành chính" in t
    assert "Xử phạt bị cáo" not in t and "Tuyên bố" not in t and "đề nghị" not in t


def test_che_ten_moi_toi_cua_blhs_va_ten_toi_viet_hoa():
    ten = ["tàng trữ trái phép chất ma túy", "trộm cắp tài sản"]
    t, dem = hf.che_dap_an("Trước đó A đã phạm tội tàng trữ trái phép chất ma túy. B phạm tội Mua bán người. C phạm tội lần đầu.\n"
                           "Về tội danh:\nThời hạn tù tính từ ngày bắt.", ["173"], ["Trộm cắp tài sản"], ten)
    assert "tàng trữ" not in t and "Mua bán người" not in t
    assert "phạm tội lần đầu" in t and "Thời hạn tù" in t
    assert dem["ten_toi_blhs"] == 1 and dem["toi_danh_viet_hoa"] == 1


def test_dau_vao_qua_ngan_bi_loai():
    b = _ban_ghi("a", su_viec="Bị cáo trộm xe máy của anh B rồi đem bán lấy tiền tiêu xài.")
    assert not b["dung_duoc"] and b["ly_do"] == "dau_vao_qua_ngan"


def test_dem_ten_toi_con_trong_loi_ke():
    b = _ban_ghi("a", su_viec="Kết quả điều tra xác định bị cáo đã thực hiện 02 hành vi trộm cắp tài sản: lẻn vào nhà anh B lấy một "
                              "chiếc xe máy trị giá 18.000.000 đồng, rồi lẻn vào nhà chị C lấy một điện thoại di động trị giá 6.000.000 đồng "
                              "và đem bán cho một người không rõ lai lịch lấy tiền tiêu xài cá nhân.")
    assert b["dung_duoc"] and b["ten_toi_trong_loi_ke"] == 1


def test_ten_toi_tu_luat(tmp_path):
    import sqlite3
    p = tmp_path / "luat.sqlite"
    c = sqlite3.connect(p)
    c.executescript("""CREATE TABLE van_ban (id INTEGER PRIMARY KEY, so_hieu TEXT);
        CREATE TABLE don_vi_luat (id INTEGER PRIMARY KEY, van_ban_id INTEGER, loai TEXT);
        CREATE TABLE phien_ban_noi_dung (id INTEGER PRIMARY KEY, don_vi_id INTEGER, ky_hieu TEXT, tieu_de TEXT);
        INSERT INTO van_ban VALUES (1, '100/2015/QH13'), (2, '15/1999/QH10');
        INSERT INTO don_vi_luat VALUES (1, 1, 'dieu'), (2, 1, 'dieu'), (3, 1, 'dieu'), (4, 2, 'dieu');
        INSERT INTO phien_ban_noi_dung VALUES (1, 1, '173', 'Tội trộm cắp tài sản'), (2, 2, '51', 'Các tình tiết giảm nhẹ trách nhiệm hình sự'),
            (3, 3, '217a', 'Tội vi phạm quy định về kinh doanh theo phương thức đa cấp'), (4, 4, '138', 'Tội trộm cắp tài sản cũ');""")
    c.commit()
    c.close()
    assert hf.ten_toi_tu_luat(p) == ["trộm cắp tài sản", "vi phạm quy định về kinh doanh theo phương thức đa cấp"]


# --------------------------------------------------------------------------------------------------------------------
# 4. gom vụ, chia tập
# --------------------------------------------------------------------------------------------------------------------
def _gia(ma, dieu, so_tham=None, dau_vao=None, cap="phuc_tham", so=None):
    return {"ma": ma, "dieu": dieu, "so_tham_tham_chieu": so_tham, "so_ban_an": so, "cap": cap,
            "dau_vao": dau_vao or f"sự việc riêng của văn bản {ma} " + " ".join(f"tu{ma}{i}" for i in range(30))}


def test_gom_vu_cung_ban_an_so_tham_va_gan_trung():
    chung = "bị cáo dùng dao đâm anh B nhiều nhát vào bụng tại quán nước ven đường lúc khuya rồi bỏ chạy về nhà " * 3
    ds = [_gia("p1", ["123"], "05/2024/HS-ST"), _gia("g1", ["123"], "05/2024/HS-ST"),
          _gia("x1", ["134"], dau_vao=chung), _gia("x2", ["134"], dau_vao=chung + " thêm một câu"), _gia("k", ["173"])]
    nhom = hf.gom_vu(ds)
    assert nhom["p1"] == nhom["g1"] and nhom["x1"] == nhom["x2"]
    assert len({nhom["p1"], nhom["x1"], nhom["k"]}) == 3


def test_ban_an_so_tham_noi_voi_ban_phuc_tham_trich_no():
    ds = [_gia("st", ["173"], cap="so_tham", so="05/2024/HS-ST"), _gia("pt", ["173"], "05/2024/HS-ST")]
    nhom = hf.gom_vu(ds)
    assert nhom["st"] == nhom["pt"]


def test_chia_tap_co_dinh_khong_tach_vu_va_dieu_hiem_vao_test():
    ds = [_gia(f"a{i}", ["173"]) for i in range(10)] + [_gia(f"b{i}", ["134"]) for i in range(4)] + [_gia("c0", ["299"])]
    ds += [_gia("p1", ["123"], "09/2024/HS-ST"), _gia("p2", ["123"], "09/2024/HS-ST")]
    nhom = hf.gom_vu(ds)
    t1 = hf.chia_tap(ds, nhom, 0.5, 7)
    assert t1 == hf.chia_tap(list(reversed(ds)), nhom, 0.5, 7)      # không phụ thuộc thứ tự đầu vào
    assert t1["p1"] == t1["p2"]                                      # cùng vụ cùng tập
    assert t1["c0"] == "test"                                        # Điều chỉ có một vụ -> test
    assert sum(t1[f"a{i}"] == "test" for i in range(10)) == 5
    assert sum(t1[f"b{i}"] == "test" for i in range(4)) == 2


def test_them_van_ban_moi_khong_xao_lai_nhom_cu_cung_tang_lon():
    ds = [_gia(f"a{i}", ["173"]) for i in range(20)]
    t1 = hf.chia_tap(ds, hf.gom_vu(ds), 0.5, 1)
    ds2 = ds + [_gia("moi", ["173"])]
    t2 = hf.chia_tap(ds2, hf.gom_vu(ds2), 0.5, 1)
    assert sum(t1[m] != t2[m] for m in t1) <= 1


def test_tim_parquet_trong_thu_muc_con(tmp_path):
    assert hf.tim_parquet(tmp_path / "khong_co") is None
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "documents-00000-of-00001.parquet").write_bytes(b"")
    assert hf.tim_parquet(tmp_path).name == "documents-00000-of-00001.parquet"


def test_chia_tap_tu_choi_ti_le_sai():
    with pytest.raises(ValueError):
        hf.chia_tap([], {}, 1.0)


# --------------------------------------------------------------------------------------------------------------------
# 5. kiểm trùng với tập huấn luyện cũ
# --------------------------------------------------------------------------------------------------------------------
def test_trung_voi_bat_doan_ngan_chep_tu_ban_an():
    dai = "ngày 10 tháng 8 bị cáo lẻn vào nhà anh B lấy một chiếc xe máy trị giá mười tám triệu đồng rồi đem bán cho người khác " * 4
    b = {"ma": "x", "dau_vao": dai, "hash_dau_vao": hf.hash_van(dai)}
    ngan = "bị cáo lẻn vào nhà anh B lấy một chiếc xe máy trị giá mười tám triệu đồng rồi đem bán"
    assert [r["ma_cu"] for r in hf.trung_voi([b], {"t1": ngan, "t2": "Anh Hùng đâm hàng xóm một nhát vào ngực bằng dao bầu."})] == ["t1"]


# --------------------------------------------------------------------------------------------------------------------
# dữ liệu thật (chỉ chạy khi có file)
# --------------------------------------------------------------------------------------------------------------------
@pytest.mark.skipif(not THU_MUC_THAT.exists(), reason="không có inbox/ho_so_vu_an_txt/")
def test_10_ban_an_that_khong_con_lo_nhan_sau_khi_che():
    for f in sorted(THU_MUC_THAT.glob("*.txt")):
        b = hf.xu_ly({"id": f.stem, "content": f.read_text(encoding="utf-8")})
        if b["dung_duoc"]:
            assert not {k: v for k, v in b["ro_ri_sau_che"].items() if k in hf.LO_NHAN}, f.name


@pytest.mark.skipif(PARQUET is None, reason="không có raw/anle/**/documents-*.parquet")
def test_parquet_that_chia_tap_khong_ro_ri():
    pytest.importorskip("pyarrow")
    import sys
    sys.path.insert(0, str(ROOT / "scripts"))
    from xu_ly_anle_hf import xu_ly_tat_ca  # noqa: PLC0415

    luat = ROOT / "db" / "luat.sqlite"
    kq = xu_ly_tat_ca(hf.doc_parquet(PARQUET), 0.5, 2026, False, {}, hf.ten_toi_tu_luat(luat) if luat.exists() else [])
    bg = kq["ban_ghi"]
    assert kq["so_hinh_su"] > 400 and len(bg) > 150
    tap_cua_nhom: dict[str, set[str]] = {}
    for b in bg:
        tap_cua_nhom.setdefault(b["nhom_vu"], set()).add(b["tap"])
        assert b["dieu"] and b["dau_vao"].strip()
    assert all(len(t) == 1 for t in tap_cua_nhom.values())
    assert not [b["ma"] for b in bg if b["lo_nhan_con_lai"]]
    assert len({b["hash_dau_vao"] for b in bg if b["tap"] == "train"} & {b["hash_dau_vao"] for b in bg if b["tap"] == "test"}) == 0
