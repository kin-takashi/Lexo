"""Kiểm thử src/ban_an/cbba_blhs.py (dataset tmquan/cbba-toaan-gov-vn -> bản án hình sự có trích dẫn BLHS, chia train / test).

Toàn bộ dữ liệu là GIẢ LẬP (tên hư cấu, tự viết). Phần đọc / ghi parquet cần pyarrow, thiếu thì tự bỏ qua.
"""
from __future__ import annotations

import hashlib

import pytest

from src.ban_an import cbba_blhs as cb


# ----------------------------------------------------------------------------------------------------------------------
# Nhận biết BLHS
# ----------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("loai, ten, dung", [
    ("Bộ luật", "hình sự", True),
    ("Bộ luật", "Hình sự", True),
    ("Bộ luật", "hình sự xử phạt", True),       # regex của dataset dính chữ phía sau
    ("Bộ luật", "H ình sự", True),               # PDF tách chữ
    ("Bộ luật", "tố tụng hình sự", False),
    ("Bộ luật", "Tố tụng Hình sự", False),
    ("Bộ luật", "dân sự", False),
    ("Luật", "thi hành án hình sự", False),
    ("Luật", "hình sự", False),                  # không có «Luật hình sự» nào: loại phải là Bộ luật
    ("Nghị quyết", None, False),
    (None, None, False),
])
def test_la_ten_blhs_lop_regex(loai, ten, dung):
    assert cb.la_ten_blhs(loai, ten) is dung


@pytest.mark.parametrize("dich, dung", [
    ("Bộ luật hình sự", True), ("Bộ luật hình sự xử phạt", True), ("Bộ luật Hình sự", True),
    ("Bộ luật tố tụng hình sự", False), ("Luật thi hành án hình sự", False), ("", False),
])
def test_la_ten_blhs_lop_cau_truc(dich, dung):
    assert cb.la_ten_blhs(dich=dich) is dung


def _row(**kw):
    r = {"citations_law": [], "citations": []}
    r.update(kw)
    return r


def test_dan_chieu_blhs_gop_hai_lop_va_bo_tu_tung():
    r = _row(
        citations_law=[
            {"law_type": "Bộ luật", "law_name": "hình sự", "article": "173", "clause": "1", "point": None},
            {"law_type": "Bộ luật", "law_name": "tố tụng hình sự", "article": "106", "clause": None, "point": None},
            {"law_type": "Luật", "law_name": "thi hành án hình sự", "article": "5", "clause": None, "point": None},
        ],
        citations=[
            {"dieu": "51", "khoan": "1", "diem": "s", "target": "Bộ luật hình sự"},
            {"dieu": "173", "khoan": "1", "diem": None, "target": "Bộ luật hình sự"},     # trùng với lớp regex về Điều, khác điểm
            {"dieu": "99", "khoan": None, "diem": None, "target": "Bộ luật tố tụng hình sự"},
        ])
    assert cb.dan_chieu_blhs(r) == {("173", "1", ""), ("51", "1", "s")}


def test_dan_chieu_blhs_bo_so_dieu_vo_ly():
    r = _row(citations_law=[
        {"law_type": "Bộ luật", "law_name": "hình sự", "article": "9999", "clause": None, "point": None},
        {"law_type": "Bộ luật", "law_name": "hình sự", "article": "0", "clause": None, "point": None},
        {"law_type": "Bộ luật", "law_name": "hình sự", "article": "abc", "clause": None, "point": None},
        {"law_type": "Bộ luật", "law_name": "hình sự", "article": "426", "clause": None, "point": None},
    ])
    assert cb.dan_chieu_blhs(r) == {("426", "", "")}


def test_dan_chieu_blhs_khong_co_thi_rong():
    assert cb.dan_chieu_blhs(_row()) == set()
    assert cb.dan_chieu_blhs({"citations_law": None, "citations": None}) == set()


# ----------------------------------------------------------------------------------------------------------------------
# Tham chiếu bản án sơ thẩm, cấp xét xử, loại văn bản
# ----------------------------------------------------------------------------------------------------------------------
def test_tham_chieu_so_tham_cac_dang_ngay():
    vb = ("Xét xử phúc thẩm vụ án. Bản án hình sự sơ thẩm số 07/2017/HSST ngày 20/03/2017 của Tòa án nhân dân huyện A. "
          "Lại có Bản án sơ thẩm số: 12/2019/HS-ST ngày 5 tháng 4 năm 2019 của Tòa án khác. "
          "Và bản án số 3/2020/HSST ngày 01-02-2020.")
    assert cb.tham_chieu_so_tham(vb) == [(3, 2020, "2020-02-01"), (7, 2017, "2017-03-20"), (12, 2019, "2019-04-05")]


def test_tham_chieu_so_tham_bo_ngay_vo_ly_va_khong_co():
    assert cb.tham_chieu_so_tham("Bản án sơ thẩm số 07/2017/HSST ngày 45/13/2017") == []
    assert cb.tham_chieu_so_tham("Không nêu số bản án nào") == []
    assert cb.tham_chieu_so_tham("bản án phúc thẩm số 07/2017/HSPT ngày 20/03/2017") == []     # chỉ nhận số SƠ thẩm


def test_so_va_nam():
    assert cb.so_va_nam("47/2017/HSPT") == (47, 2017)
    assert cb.so_va_nam("007/2020/HS-ST") == (7, 2020)
    assert cb.so_va_nam("khong co so") is None
    assert cb.so_va_nam(None) is None


@pytest.mark.parametrize("dau, cap", [
    ("Thành phần Hội đồng xét xử sơ thẩm gồm có:", "so_tham"),
    ("- Thành phần Hội đồng xét xử phúc thẩm gồm có:", "phuc_tham"),
    ("Với thành phần Hội đồng xét xử  phúc \nthẩm gồm có", "phuc_tham"),
    ("Hội đồng xét xử giám đốc thẩm", "giam_doc_tham"),
    ("Hội đồng xét xử tái thẩm", "tai_tham"),
    ("Không có dòng thành phần", None),
])
def test_cap_theo_van_ban(dau, cap):
    assert cb.cap_theo_van_ban("TÒA ÁN\n" + dau + "\nThẩm phán ...") == cap


def test_cap_theo_van_ban_chi_xet_phan_dau():
    vb = "x" * 5000 + " Hội đồng xét xử phúc thẩm"
    assert cb.cap_theo_van_ban(vb) is None


def test_cap_cuoi_tin_van_ban_khi_mau_thuan():
    assert cb.cap_cuoi("First-instance", "phuc_tham") == ("phuc_tham", True)
    assert cb.cap_cuoi("Appellate", "phuc_tham") == ("phuc_tham", False)
    assert cb.cap_cuoi("First-instance", None) == ("so_tham", False)
    assert cb.cap_cuoi(None, "so_tham") == ("so_tham", False)
    assert cb.cap_cuoi(None, None) == ("khong_ro", False)
    assert cb.cap_cuoi("Cassation", None) == ("giam_doc_tham", False)


def test_loai_van_ban():
    ban_an = "TÒA ÁN NHÂN DÂN\nBản án số: 12/2024/HS-ST\nNgày 01/01/2024\n" + "..." * 50 + "\nQUYẾT ĐỊNH:\nTuyên bố bị cáo phạm tội"
    quyet_dinh = "TÒA ÁN NHÂN DÂN\nSố: 897/2020/HSPT-QĐ\nQUYẾT ĐỊNH\n(Đình chỉ việc xét xử phúc thẩm)\nNHẬN THẤY:"
    ban_an_hoa = "BẢN ÁN\nNHÂN DANH NƯỚC CỘNG HÒA\nQUYẾT ĐỊNH:"
    assert cb.loai_van_ban(ban_an) == "ban_an"
    assert cb.loai_van_ban(quyet_dinh) == "quyet_dinh"
    assert cb.loai_van_ban(ban_an_hoa) == "ban_an"
    assert cb.loai_van_ban("văn bản không có tiêu đề gì") == "ban_an"


def test_nhac_phien_ban():
    assert cb.nhac_phien_ban("áp dụng Bộ luật hình sự năm 1999") == (True, False)
    assert cb.nhac_phien_ban("theo Bộ luật Hình sự năm 2015, sửa đổi") == (False, True)
    assert cb.nhac_phien_ban("Bộ luật hình sự nước Cộng hòa xã hội chủ nghĩa Việt Nam năm 1999") == (True, False)
    assert cb.nhac_phien_ban("Bộ luật Hình\nsự năm 2015 và Bộ luật hình sự năm 1999") == (True, True)
    assert cb.nhac_phien_ban("điều 100/2015/QH13") == (False, True)
    assert cb.nhac_phien_ban("chỉ viết Bộ luật hình sự") == (False, False)


# ----------------------------------------------------------------------------------------------------------------------
# Loại bỏ, gom vụ, chia tập
# ----------------------------------------------------------------------------------------------------------------------
def _b(ma, *, cap="so_tham", so="1/2020/HS-ST", toa="Tòa A", ngay="2020-05-01", loai="ban_an", n=5000, md5=None, dieu=("173",),
       tc=(), dieu_toi_pham=True):
    return {"ma": ma, "cap": cap, "so_chuan": so, "toa_an": toa, "ngay": ngay, "loai_van_ban": loai, "so_ky_tu": n,
            "md5": md5 or f"md5-{ma}", "dieu_blhs": list(dieu), "tham_chieu_so_tham": list(tc), "cap_toa": "District", "nam": 2020,
            "co_dieu_toi_pham": dieu_toi_pham, "nhac_blhs_1999": False, "nhac_blhs_2015": False, "mau_thuan_cap": False}


def test_loai_bo_ly_do_va_thu_tu():
    bg = [
        _b("a"),
        _b("qd", loai="quyet_dinh"),
        _b("ngan", n=100),
        _b("pt", cap="phuc_tham"),
        _b("a", md5="khac"),                       # trùng mã với «a»
        _b("c", md5="md5-a"),                       # trùng nguyên văn với «a»
        _b("kdtp", dieu_toi_pham=False),
    ]
    giu, bo = cb.loai_bo(bg, so_ky_tu_toi_thieu=3000, cap_giu={"so_tham"}, chi_co_dieu_toi_pham=True)
    assert [b["ma"] for b in giu] == ["a"]
    assert bo == [("qd", "quyet_dinh"), ("ngan", "qua_ngan"), ("pt", "cap_khong_giu"), ("a", "trung_ma"),
                  ("c", "trung_nguyen_van"), ("kdtp", "khong_co_dieu_toi_pham")]


def test_loai_bo_mac_dinh_giu_het_cap():
    giu, bo = cb.loai_bo([_b("a"), _b("b", cap="phuc_tham"), _b("c", cap="khong_ro")])
    assert len(giu) == 3 and not bo


def test_gom_vu_noi_phuc_tham_voi_so_tham_khop_ngay():
    st = _b("st", so="7/2017/HS-ST", ngay="2017-03-20")
    pt = _b("pt", cap="phuc_tham", so="45/2017/HS-PT", ngay="2017-07-10", tc=["7|2017|2017-03-20"])
    khac = _b("khac", so="7/2017/HS-ST", toa="Tòa B", ngay="2017-09-09")       # cùng số, khác ngày -> không phải bản án được nêu
    nhom, tk = cb.gom_vu([st, pt, khac])
    assert nhom["st"] == nhom["pt"] and nhom["khac"] != nhom["st"]
    assert tk["da_noi_voi_so_tham"] == 1


def test_gom_vu_khong_noi_khi_mo_ho_hoac_khong_thay():
    sts = [_b(f"st{i}", so="7/2017/HS-ST", toa=f"Tòa {i}", ngay="2017-03-20") for i in range(cb.NGUONG_UNG_VIEN + 1)]
    pt = _b("pt", cap="phuc_tham", so="1/2017/HS-PT", tc=["7|2017|2017-03-20", "99|2017|2017-01-01"])
    nhom, tk = cb.gom_vu(sts + [pt])
    assert len({nhom[f"st{i}"] for i in range(cb.NGUONG_UNG_VIEN + 1)}) == cb.NGUONG_UNG_VIEN + 1
    assert nhom["pt"] == "pt"
    assert tk["mo_ho"] == 1 and tk["khong_tim_thay_so_tham"] == 1 and tk["khong_noi_duoc"] == 1 and tk["cap_tren"] == 1


def test_gom_vu_noi_hai_ung_vien_va_nhieu_phuc_tham_chung_so_tham():
    st1 = _b("st1", so="7/2017/HS-ST", toa="Tòa A", ngay="2017-03-20")
    st2 = _b("st2", so="7/2017/HS-ST", toa="Tòa B", ngay="2017-03-20")        # cùng số + ngày ở hai tòa: nối cả hai (an toàn)
    pt1 = _b("pt1", cap="phuc_tham", so="1/2017/HS-PT", tc=["7|2017|2017-03-20"])
    pt2 = _b("pt2", cap="phuc_tham", so="2/2017/HS-PT", tc=["7|2017|2017-03-20"])
    nhom, _ = cb.gom_vu([st1, st2, pt1, pt2])
    assert len({nhom[m] for m in ("st1", "st2", "pt1", "pt2")}) == 1


def test_gom_vu_khong_noi_so_tham_voi_so_tham_khac():
    """Bản án sơ thẩm nêu số bản án sơ thẩm khác (tiền án, số thụ lý) thì KHÔNG nối: không phải cùng một vụ."""
    a = _b("a", so="5/2020/HS-ST", toa="Tòa A", ngay="2020-03-01", tc=["9|2019|2019-04-04"])
    b = _b("b", so="9/2019/HS-ST", toa="Tòa B", ngay="2019-04-04")
    c = _b("c", so="5/2020/HS-ST", toa="Tòa C", ngay="2020-03-01", tc=["5|2020|2020-03-01"])      # số thụ lý trùng số bản án của tòa khác
    nhom, tk = cb.gom_vu([a, b, c])
    assert len({nhom["a"], nhom["b"], nhom["c"]}) == 3
    assert tk.get("cap_tren", 0) == 0


def test_gom_vu_noi_giam_doc_tham_voi_so_tham():
    st = _b("st", so="7/2017/HS-ST", ngay="2017-03-20")
    gdt = _b("gdt", cap="giam_doc_tham", so="3/2018/HS-GĐT", ngay="2018-06-01", tc=["7|2017|2017-03-20"])
    nhom, _ = cb.gom_vu([st, gdt])
    assert nhom["st"] == nhom["gdt"]


def test_gom_vu_noi_cung_so_toa_ngay():
    a = _b("a", so="3/2020/HS-ST", toa="Tòa A", ngay="2020-01-02", md5="x1")
    b = _b("b", so="3/2020/HS-ST", toa="Tòa A", ngay="2020-01-02", md5="x2")          # cùng bản án đăng lại, chữ trích khác
    c = _b("c", so="3/2020/HS-ST", toa="Tòa B", ngay="2020-01-02", md5="x3")
    nhom, _ = cb.gom_vu([a, b, c])
    assert nhom["a"] == nhom["b"] != nhom["c"]


def test_chia_tap_xac_dinh_va_nguyen_nhom():
    nhom = {f"m{i}": f"g{i // 3}" for i in range(300)}                 # 100 nhóm, mỗi nhóm 3 văn bản
    t1, t2 = cb.chia_tap(nhom, 0.3, 2026), cb.chia_tap(nhom, 0.3, 2026)
    assert t1 == t2
    for g in set(nhom.values()):
        assert len({t1[m] for m, k in nhom.items() if k == g}) == 1
    assert cb.chia_tap(nhom, 0.3, 7) != t1                              # seed khác -> chia khác


def test_chia_tap_ti_le_va_on_dinh_khi_them_van_ban():
    nhom = {f"m{i}": f"g{i}" for i in range(20000)}
    tap = cb.chia_tap(nhom, 0.3, 2026)
    ti_le = sum(t == "test" for t in tap.values()) / len(tap)
    assert 0.285 < ti_le < 0.315
    them = dict(nhom, **{f"moi{i}": f"gm{i}" for i in range(500)})
    tap2 = cb.chia_tap(them, 0.3, 2026)
    assert all(tap2[m] == t for m, t in tap.items())                   # thêm văn bản không xáo lại nhóm cũ


def test_kiem_ro_ri_bat_duoc_cap_bi_tach_tap():
    st = _b("st", so="7/2017/HS-ST", ngay="2017-03-20")
    pt = _b("pt", cap="phuc_tham", so="45/2017/HS-PT", tc=["7|2017|2017-03-20"])
    xau = cb.kiem_ro_ri([st, pt], {"st": "train", "pt": "test"})
    tot = cb.kiem_ro_ri([st, pt], {"st": "test", "pt": "test"})
    assert xau["cap_tren_so_tham_kiem"] == 1 and xau["cap_tren_so_tham_khac_tap"] == 1
    assert tot["cap_tren_so_tham_khac_tap"] == 0


def test_kiem_ro_ri_bat_trung_nguyen_van_giua_hai_tap():
    a, b = _b("a", md5="same"), _b("b", md5="same")
    assert cb.kiem_ro_ri([a, b], {"a": "train", "b": "test"})["md5_o_ca_hai_tap"] == 1
    assert cb.kiem_ro_ri([a, b], {"a": "train", "b": "train"})["md5_o_ca_hai_tap"] == 0


def test_chia_toan_bo_khong_ro_ri_voi_du_lieu_gia():
    bg, pt_ids = [], []
    for i in range(400):
        ngay = f"2021-{(i % 12) + 1:02d}-{(i % 27) + 1:02d}"
        st = _b(f"st{i}", so=f"{i + 1}/2021/HS-ST", toa=f"Tòa {i % 7}", ngay=ngay)
        bg.append(st)
        if i % 4 == 0:
            bg.append(_b(f"pt{i}", cap="phuc_tham", so=f"{i + 1}/2021/HS-PT", ngay="2021-12-30", tc=[f"{i + 1}|2021|{ngay}"]))
            pt_ids.append(i)
    nhom, _ = cb.gom_vu(bg)
    tap = cb.chia_tap(nhom, 0.3, 1)
    kq = cb.kiem_ro_ri(bg, tap)
    assert kq["cap_tren_so_tham_kiem"] == len(pt_ids) and kq["cap_tren_so_tham_khac_tap"] == 0
    for i in pt_ids:
        assert tap[f"st{i}"] == tap[f"pt{i}"]


# ----------------------------------------------------------------------------------------------------------------------
# Đọc / ghi parquet (cần pyarrow)
# ----------------------------------------------------------------------------------------------------------------------
def _hang(ma, *, dieu="173", loai="hình sự", ten="Bộ luật", categ="Criminal", nam=2020, so=None, vb=None, cap="First-instance",
          cau_truc=True):
    so = so or f"{ma}/2020/HS-ST"
    vb = vb or (f"TÒA ÁN NHÂN DÂN\nBản án số: {so}\nThành phần Hội đồng xét xử sơ thẩm gồm có:\n" + f"Nguyễn Văn {ma} trộm cắp tài sản. " * 200
                + f"\nQUYẾT ĐỊNH: áp dụng khoản 1 Điều {dieu} Bộ luật hình sự năm 2015.")
    return {
        "doc_name": ma, "official_document_id": so, "official_document_id_normalized": so, "code": "HS-ST", "category": categ,
        "instance_level": cap, "court": "Tòa án nhân dân huyện A", "court_level": "District", "issued_date": "2020-05-01", "year": float(nam),
        "citations_law": [{"law_type": ten, "law_name": loai, "article": dieu, "clause": "1", "point": None}],
        "citations": [{"dieu": "51", "khoan": "1", "diem": "s", "target": "Bộ luật hình sự"}] if cau_truc else [],
        "web_url": f"https://example.invalid/{ma}", "pdf_url": f"https://example.invalid/{ma}.pdf", "markdown": vb,
    }


def _ghi_parquet(path, hangs):
    pa = pytest.importorskip("pyarrow")
    pq = pytest.importorskip("pyarrow.parquet")
    pq.write_table(pa.Table.from_pylist(hangs), str(path))


def test_loc_shard_chi_giu_hinh_su_co_blhs(tmp_path):
    hangs = [
        _hang("1"),                                               # Điều 173 (lớp regex) + Điều 51 (lớp cấu trúc)
        _hang("2", categ="Civil"),                                # không phải hình sự
        _hang("3", loai="tố tụng hình sự", cau_truc=False),       # chỉ trích Bộ luật Tố tụng hình sự
        {**_hang("4"), "citations_law": [], "citations": []},     # không trích gì
        _hang("5", dieu="999", cau_truc=False),                   # số Điều vô lý
        _hang("6", loai="tố tụng hình sự"),                       # TTHS ở lớp regex nhưng Điều 51 BLHS ở lớp cấu trúc -> giữ
    ]
    _ghi_parquet(tmp_path / "nguon.parquet", hangs)
    tk = cb.loc_shard(tmp_path / "nguon.parquet", tmp_path / "loc.parquet", kich_thuoc_lo=4)
    assert tk == {"tong": 6, "hinh_su": 5, "co_blhs": 2}
    import pyarrow.parquet as pq
    ds = pq.read_table(str(tmp_path / "loc.parquet")).to_pylist()
    assert sorted(d["ma"] for d in ds) == ["1", "6"]
    d1 = next(d for d in ds if d["ma"] == "1")
    assert d1["dieu_blhs"] == ["51", "173"] and d1["cap"] == "so_tham" and d1["loai_van_ban"] == "ban_an"
    assert d1["dieu_khoan_diem_blhs"] == ["173|1|", "51|1|s"]
    assert d1["co_dieu_toi_pham"] is True and d1["nhac_blhs_2015"] is True and d1["mau_thuan_cap"] is False
    assert d1["md5"] and d1["so_ky_tu"] == len(d1["van_ban"])
    assert next(d for d in ds if d["ma"] == "6")["co_dieu_toi_pham"] is False          # chỉ có Điều 51


def test_loc_shard_mau_thuan_cap_va_ghi_tap_xac_dinh(tmp_path):
    hangs = [_hang(str(i), cap="First-instance" if i % 2 else "Appellate") for i in range(1, 41)]
    hangs[0]["instance_level"] = "Appellate"                           # văn bản nói «sơ thẩm», cổng ghi «phúc thẩm»
    _ghi_parquet(tmp_path / "nguon.parquet", hangs)
    cb.loc_shard(tmp_path / "nguon.parquet", tmp_path / "loc.parquet", kich_thuoc_lo=7)
    import pyarrow.parquet as pq
    ds = pq.read_table(str(tmp_path / "loc.parquet")).to_pylist()
    assert len(ds) == 40
    d1 = next(d for d in ds if d["ma"] == "1")
    assert d1["cap_theo_van_ban"] == "so_tham" and d1["cap_cong_thong_tin"] == "phuc_tham"
    assert d1["mau_thuan_cap"] is True and d1["cap"] == "so_tham"

    nhe = [{k: v for k, v in d.items() if k != "van_ban"} for d in ds]
    giu, _ = cb.loai_bo(nhe)
    nhom, _ = cb.gom_vu(giu)
    tap = cb.chia_tap(nhom, 0.3, 2026)
    hashes = []
    for lan in ("a", "b"):
        ra = tmp_path / lan
        ra.mkdir()
        kq = cb.ghi_tap([tmp_path / "loc.parquet"], {b["ma"] for b in giu}, tap, nhom, ra)
        assert kq["train"] + kq["test"] == 40
        hashes.append([hashlib.sha256((ra / f).read_bytes()).hexdigest() for f in ("train.jsonl.gz", "test.jsonl.gz")])
        tong = [d for t in ("train", "test") for d in cb.doc_jsonl_gz(ra / f"{t}.jsonl.gz")]
        assert sorted(d["ma"] for d in tong) == sorted(str(i) for i in range(1, 41))
        assert all(d["tap"] == tap[d["ma"]] and d["van_ban"].startswith("TÒA ÁN") for d in tong)
        assert set(tong[0]) == set(cb.COT_JSONL)
    assert hashes[0] == hashes[1]                                       # chạy lại cho đúng từng byte


def test_sha256_ma_khong_phu_thuoc_thu_tu():
    assert cb.sha256_ma(["b", "a", "c"]) == cb.sha256_ma(["c", "b", "a"])
    assert cb.sha256_ma(["a", "b"]) != cb.sha256_ma(["a", "c"])
    assert cb.sha256_ma([]) == hashlib.sha256(b"").hexdigest()


def test_ten_va_url_shard():
    assert cb.ten_shard(0) == "documents-00000-of-00016.parquet"
    assert cb.url_shard(15) == "https://huggingface.co/datasets/tmquan/cbba-toaan-gov-vn/resolve/main/documents-00015-of-00016.parquet"
