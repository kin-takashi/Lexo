"""Chẩn đoán câu hỏi sinh sẵn (src/index/chan_doan): lọc trùng giữa các Điều, thống kê khứ hồi, so phiếu chữ luật / câu sinh, kết luận."""

import numpy as np
import pytest

from src.index.cau_hoi import loc_dieu_toi_pham, chon_trai_deu, dieu_dap_an, hang_dieu_cua_cau_hoi, luu_cau_hoi
from src.index.chan_doan import (chuan_chu, ket_luan, ket_luan_quet, loc_trung, so_phieu, thong_ke_cau_hoi, ti_le_cuu_pha)
from src.index.chunks import build_chunks, hash_text
from src.index.embedder import HashEmbedder
from src.index.store import luu_vector, open_index, sync_chunks, thieu_vector, thieu_vector_cau_hoi

from test_apply_rebuild import D1, P, env  # noqa: F401


def chi_muc_co_vec(env, tmp_path, emb):  # noqa: F811
    idx = open_index(tmp_path / "idx.sqlite")
    sync_chunks(idx, build_chunks(env.c, env.vb))
    t = thieu_vector(idx, emb.name)
    luu_vector(idx, emb.name, [r["hash"] for r in t], emb.embed([r["text"] for r in t]))
    return idx


def nhung_cau_hoi(idx, emb):
    tv = thieu_vector_cau_hoi(idx, emb.name)
    luu_vector(idx, emb.name, [r["hash"] for r in tv], emb.embed([r["text"] for r in tv]))


def test_chuan_chu_bo_dau_cau_va_hoa_thuong():
    assert chuan_chu("Xe máy hàng xóm mất tích?") == chuan_chu("xe máy  hàng xóm, mất tích")
    assert chuan_chu("lấy trộm") != chuan_chu("lay trom")                      # giữ dấu tiếng Việt: khác dấu là khác từ


def test_loc_trung_bo_ca_hai_phia_va_chi_bo_khi_khac_dieu(env, tmp_path):  # noqa: F811
    emb = HashEmbedder()
    idx = chi_muc_co_vec(env, tmp_path, emb)
    luu_cau_hoi(idx, "dieu 3", "h", "gia", ["xe máy hàng xóm mất tích", "lấy trộm điện thoại của bạn cùng phòng thì sao nhỉ",
                                            "nhặt điện thoại rơi giữa phố thì có phải trả không"])
    luu_cau_hoi(idx, "dieu 4", "h", "gia", ["Xe máy hàng xóm mất tích?", "bị lừa đưa tiền đầu tư rồi người ta biến mất luôn thì kiện ai"])
    nhung_cau_hoi(idx, emb)
    st = loc_trung(idx, emb.name)
    assert st["so_cau"] == 5 and st["trung"] == 2 and st["loai"] == 2                      # cùng chữ ở 2 Điều khác nhau: bỏ cả hai
    giu = {r["cau_hoi"] for r in idx.execute("SELECT cau_hoi FROM cau_hoi_sinh WHERE giu = 1")}
    assert giu == {"lấy trộm điện thoại của bạn cùng phòng thì sao nhỉ", "nhặt điện thoại rơi giữa phố thì có phải trả không",
                   "bị lừa đưa tiền đầu tư rồi người ta biến mất luôn thì kiện ai"}


def test_loc_trung_lap_trong_cung_dieu_khong_tinh(env, tmp_path):  # noqa: F811
    emb = HashEmbedder()
    idx = chi_muc_co_vec(env, tmp_path, emb)
    luu_cau_hoi(idx, "dieu 3", "h", "gia", ["cùng điều thì lặp cũng không sao nhé", "cùng điều thì lặp cũng không sao nhé"])
    nhung_cau_hoi(idx, emb)
    st = loc_trung(idx, emb.name)
    assert st["trung"] == 0 and st["loai"] == 0


def test_loc_trung_gan_trung_theo_cosine(env, tmp_path):  # noqa: F811
    emb = HashEmbedder()
    idx = chi_muc_co_vec(env, tmp_path, emb)
    luu_cau_hoi(idx, "dieu 3", "h", "gia", ["tôi lén lấy xe máy của hàng xóm có bị phạt không vậy"])
    luu_cau_hoi(idx, "dieu 4", "h", "gia", ["tôi lén lấy xe máy của hàng xóm có bị phạt nặng không vậy"])
    nhung_cau_hoi(idx, emb)
    assert loc_trung(idx, emb.name, nguong=0.99)["trung"] == 0
    assert loc_trung(idx, emb.name, nguong=0.7)["trung"] == 2


def test_thong_ke_cau_hoi(env, tmp_path):  # noqa: F811
    emb = HashEmbedder()
    idx = chi_muc_co_vec(env, tmp_path, emb)
    cau = ["trộm cắp tài sản của người khác", "lừa đảo chiếm đoạt tiền bạc thủ đoạn gian dối", "ly hôn không trả抚养费 cho con"]
    luu_cau_hoi(idx, "dieu 3", "h", "gia", cau)
    nhung_cau_hoi(idx, emb)
    tk = thong_ke_cau_hoi(idx, emb.name)
    hang = hang_dieu_cua_cau_hoi(idx, emb, ["dieu 3"] * 3, cau)
    assert tk["tong"] == 3 and tk["co_vec"] == 3 and tk["so_dieu"] == 1 and tk["chu_ngoai"] == 1
    assert tk["hang1"] == sum(1 for h in hang if h == 1) and tk["top3"] == sum(1 for h in hang if h is not None and h <= 3)
    assert tk["ti_hang1"] == pytest.approx(tk["hang1"] / 3) and tk["giu"] == 3 and tk["dieu_du_3"] == 1 and tk["trung"] == 0


def test_thong_ke_chi_tinh_dieu_duoc_chon(env, tmp_path):  # noqa: F811
    emb = HashEmbedder()
    idx = chi_muc_co_vec(env, tmp_path, emb)
    luu_cau_hoi(idx, "dieu 3", "h", "gia", ["trộm cắp tài sản của người khác", "lấy trộm xe máy hàng xóm mất tích"])
    luu_cau_hoi(idx, "dieu 4", "h", "gia", ["lừa đảo chiếm đoạt tiền bạc thủ đoạn gian dối"])
    nhung_cau_hoi(idx, emb)
    tk = thong_ke_cau_hoi(idx, emb.name, chi_dieu={"dieu 4"})
    assert tk["co_vec"] == 1 and tk["so_dieu"] == 1 and tk["tong"] == 3
    assert thong_ke_cau_hoi(idx, emb.name, chi_dieu={"dieu 99"})["co_vec"] == 0


def test_thong_ke_rong(env, tmp_path):  # noqa: F811
    emb = HashEmbedder()
    idx = chi_muc_co_vec(env, tmp_path, emb)
    tk = thong_ke_cau_hoi(idx, emb.name)
    assert tk["tong"] == 0 and tk["co_vec"] == 0 and tk["ti_hang1"] == 0.0
    assert ket_luan(tk, None)[0] == "THIEU"


class VecGia:
    """Embedder giả: chữ -> vector đặt tay (4 chiều), để dựng kịch bản so phiếu chính xác."""
    name = "gia4"

    def __init__(self, bang):
        self.bang = bang

    def embed(self, texts):
        return [self.bang[t] for t in texts]


def _u(v):
    v = np.asarray(v, dtype=np.float32)
    return v / np.linalg.norm(v)


def test_so_phieu_cuu_pha_va_dong_y(tmp_path):
    idx = open_index(tmp_path / "x.sqlite")
    e1, e2, e3 = _u([1, 0, 0, 0]), _u([0, 1, 0, 0]), _u([0, 0, 1, 0])
    for i, (v, k) in enumerate(((e1, "dieu 1"), (e2, "dieu 2"), (e3, "dieu 3")), 1):
        idx.execute("INSERT INTO chunk VALUES (?, 1, ?, 'dieu', '2016-07-01', NULL, '', ?, ?)", (i, k, f"Điều {i}. T\nnội dung {i}", f"h{i}"))
        luu_vector(idx, "gia4", [f"h{i}"], [v])
    a, b, c = _u([.9, .1, 0, .4]), _u([.7, 0, .3, .6]), _u([0, .9, .1, .4])
    luu_cau_hoi(idx, "dieu 2", "h", "gia", ["qa", "qc"])             # câu sinh của Điều 2 trùng đúng vector câu a và câu c
    luu_cau_hoi(idx, "dieu 3", "h", "gia", ["qb"])
    luu_cau_hoi(idx, "dieu 1", "h", "gia", ["qd1"])                  # Điều 1 cũng có câu sinh (nhưng xa mọi câu hỏi), nên câu a được tính
    for t, v in (("qa", a), ("qc", c), ("qb", b), ("qd1", _u([0, 0, 0, 1]))):
        luu_vector(idx, "gia4", [hash_text(t)], [v])
    emb = VecGia({"A": a, "B": b, "C": c})
    bo = [{"id": "a", "cau_hoi": "A", "dieu": ["1"]}, {"id": "b", "cau_hoi": "B", "dieu": ["3"]}, {"id": "c", "cau_hoi": "C", "dieu": ["2"]}]
    ph = so_phieu(idx, emb, bo, ngay="2026-10-02")
    assert ph["n"] == 3 and ph["n_tong"] == 3 and ph["dong_y"] == 1 and ph["bat_dong"] == 2
    assert ph["chu_dung_khi_bat_dong"] == 1 and ph["cau_hoi_dung_khi_bat_dong"] == 1
    assert ph["cuu"] == 1 and ph["pha"] == 1 and ti_le_cuu_pha(ph) == 1.0
    assert ph["chu"]["hit1"] == pytest.approx(2 / 3) and ph["cau_hoi"]["hit1"] == pytest.approx(2 / 3)
    idx.execute("UPDATE cau_hoi_sinh SET giu = 0 WHERE dieu = 'dieu 2'")                  # câu bị lọc không được tính phiếu; câu c mất phủ nên rời mẫu
    ph = so_phieu(idx, emb, bo, ngay="2026-10-02")
    assert ph["n"] == 2 and ph["n_tong"] == 3 and ph["cuu"] == 1 and ph["pha"] == 1 and ph["cau_hoi"]["hit1"] == pytest.approx(1 / 2)


def test_so_phieu_chi_tinh_cau_co_dap_an_duoc_phu(tmp_path):
    """Câu sinh chỉ phủ Điều 2: câu có đáp án ở Điều 1 và 3 không được tính (câu sinh không thể đúng ở đó)."""
    idx = open_index(tmp_path / "x.sqlite")
    e1, e2, e3 = _u([1, 0, 0, 0]), _u([0, 1, 0, 0]), _u([0, 0, 1, 0])
    for i, (v, k) in enumerate(((e1, "dieu 1"), (e2, "dieu 2"), (e3, "dieu 3")), 1):
        idx.execute("INSERT INTO chunk VALUES (?, 1, ?, 'dieu', '2016-07-01', NULL, '', ?, ?)", (i, k, f"Điều {i}. T\nnội dung {i}", f"h{i}"))
        luu_vector(idx, "gia4", [f"h{i}"], [v])
    c = _u([0, .9, .1, .4])
    luu_cau_hoi(idx, "dieu 2", "h", "gia", ["qc"])
    luu_vector(idx, "gia4", [hash_text("qc")], [c])
    emb = VecGia({"A": e1, "B": e3, "C": c})
    bo = [{"id": "a", "cau_hoi": "A", "dieu": ["1"]}, {"id": "b", "cau_hoi": "B", "dieu": ["3"]}, {"id": "c", "cau_hoi": "C", "dieu": ["2"]}]
    ph = so_phieu(idx, emb, bo, ngay="2026-10-02")
    assert ph["n"] == 1 and ph["n_tong"] == 3 and ph["cuu"] == 0 and ph["pha"] == 0 and ph["dong_y"] == 1
    bo2 = [{"id": "a", "cau_hoi": "A", "dieu": ["1"]}]
    ph = so_phieu(idx, emb, bo2, ngay="2026-10-02")
    assert ph["n"] == 0 and ph["n_tong"] == 1 and ph["pha"] == 0 and ph["cau_hoi"]["hit1"] == 0.0         # không câu nào đo được


def test_so_phieu_the_gioi_dong_chu_luat_khong_chon_dieu_chua_sinh(tmp_path):
    """Chữ luật chọn nhầm Điều 1 (chưa có câu sinh) cho câu có đáp án Điều 2. Câu sinh phủ Điều 2 và 3 nên chỉ chọn giữa hai Điều đó.
    So lệch (chữ luật chọn giữa cả 3, câu sinh chỉ giữa 2) sẽ ghi 'cứu 1' cho câu sinh chỉ vì Điều 1 bị cấm với nó. So công bằng: cả hai chọn giữa {2, 3}."""
    idx = open_index(tmp_path / "x.sqlite")
    e1, e2, e3 = _u([1, 0, 0, 0]), _u([0, 1, 0, 0]), _u([0, 0, 1, 0])
    for i, (v, k) in enumerate(((e1, "dieu 1"), (e2, "dieu 2"), (e3, "dieu 3")), 1):
        idx.execute("INSERT INTO chunk VALUES (?, 1, ?, 'dieu', '2016-07-01', NULL, '', ?, ?)", (i, k, f"Điều {i}. T\nnội dung {i}", f"h{i}"))
        luu_vector(idx, "gia4", [f"h{i}"], [v])
    x = _u([.8, .5, 0, .3])                                                   # gần chữ Điều 1 hơn chữ Điều 2, nhưng đáp án là Điều 2
    luu_cau_hoi(idx, "dieu 2", "h", "gia", ["q2"])
    luu_cau_hoi(idx, "dieu 3", "h", "gia", ["q3"])
    luu_vector(idx, "gia4", [hash_text("q2")], [_u([.6, .6, 0, .3])])
    luu_vector(idx, "gia4", [hash_text("q3")], [e3])
    emb = VecGia({"X": x})
    ph = so_phieu(idx, emb, [{"id": "x", "cau_hoi": "X", "dieu": ["2"]}], ngay="2026-10-02")
    assert ph["n"] == 1 and ph["n_ung_vien"] == 2
    assert ph["chu"]["hit1"] == 1.0 and ph["cau_hoi"]["hit1"] == 1.0
    assert ph["cuu"] == 0 and ph["pha"] == 0 and ph["dong_y"] == 1 and ph["bat_dong"] == 0


def test_so_phieu_bao_loi_khi_thieu_du_lieu(tmp_path):
    idx = open_index(tmp_path / "x.sqlite")
    with pytest.raises(ValueError, match="vector đoạn"):
        so_phieu(idx, VecGia({}), [], ngay="2026-10-02")


def test_ti_le_cuu_pha():
    assert ti_le_cuu_pha({"cuu": 0, "pha": 0}) is None
    assert ti_le_cuu_pha({"cuu": 3, "pha": 0}) == float("inf")
    assert ti_le_cuu_pha({"cuu": 9, "pha": 64}) == pytest.approx(0.140625)


TOT = {"co_vec": 900, "so_dieu": 300, "ti_hang1": 0.5, "ti_top3": 0.8, "ti_trung": 0.01, "chu_ngoai": 0}
PH_DU = {"n": 40, "n_tong": 70, "cuu": 6, "pha": 8}


def test_ket_luan():
    assert ket_luan(TOT, PH_DU) == ("DAT", [])
    tt, ly = ket_luan({**TOT, "ti_hang1": 0.38, "ti_top3": 0.5}, {**PH_DU, "cuu": 9, "pha": 64})   # cỡ số liệu lần chạy đầu (rank-1 38%)
    assert tt == "CHUA_DAT" and "50%" in ly[0]                                                # mẫu rộng mà khứ hồi đã hỏng: kết luận luôn
    assert ket_luan({**TOT, "ti_hang1": 0.3}, PH_DU)[0] == "DAT"                              # hạng 1 thấp nhưng top 3 tốt: không loại (chỉ tham khảo)
    assert ket_luan({**TOT, "ti_trung": 0.08}, PH_DU)[0] == "CHUA_DAT"
    assert ket_luan({**TOT, "chu_ngoai": 8}, PH_DU)[0] == "CHUA_DAT"
    tt, ly = ket_luan(TOT, {**PH_DU, "cuu": 9, "pha": 64})                                    # thống kê tốt nhưng câu sinh phá nhiều hơn cứu
    assert tt == "CHUA_DAT" and "cứu 9" in ly[0]
    assert ket_luan(TOT, {**PH_DU, "cuu": 0, "pha": 0})[0] == "CHUA_DAT"                      # câu sinh không có tác dụng gì
    assert ket_luan(TOT, {**PH_DU, "cuu": 2, "pha": 0})[0] == "DAT"


def test_ket_luan_dat_so_bo_khi_phu_it():
    """Qua mọi ngưỡng nhưng mới phủ 65/315 Điều tội phạm (đúng cỡ lần chạy qwen3:8b trên 70 câu dev): chưa phải ĐẠT, chưa cho quét hệ số."""
    assert ket_luan(TOT, PH_DU, (300, 315))[0] == "DAT"
    tt, ly = ket_luan(TOT, PH_DU, (65, 315))
    assert tt == "DAT_SO_BO" and "65/315" in ly[0]
    assert ket_luan(TOT, PH_DU, None)[0] == "DAT"
    assert ket_luan({**TOT, "ti_top3": 0.4}, PH_DU, (65, 315))[0] == "CHUA_DAT"                # trượt ngưỡng vẫn là CHƯA ĐẠT dù phủ ít


def test_ket_luan_thieu_du_lieu_khong_ket_luan_bua():
    """Lần chạy --thu 40: câu sinh chỉ phủ Điều 1–41 (Phần chung), bộ dev toàn Điều về tội phạm -> không được kết luận 'chưa đạt'."""
    mau_lech = {"co_vec": 184, "so_dieu": 40, "ti_hang1": 0.15, "ti_top3": 0.23, "ti_trung": 0.1, "chu_ngoai": 0}
    tt, ly = ket_luan(mau_lech, {"n": 0, "n_tong": 70, "cuu": 0, "pha": 0})
    assert tt == "THIEU" and any("0 câu dev" in x for x in ly)
    assert ket_luan(mau_lech, None)[0] == "THIEU"
    assert ket_luan({**mau_lech, "so_dieu": 150}, None)[0] == "CHUA_DAT"                      # mẫu rộng thì thống kê tự đủ để loại
    assert ket_luan({"co_vec": 0}, None)[0] == "THIEU"


def test_ket_luan_quet():
    cu = [(0.0, .638, .753), (0.6, .638, .753), (0.7, .655, .764), (0.8, .534, .688), (0.9, .379, .542), (1.0, .259, .399)]   # bảng lần đầu
    co, ly = ket_luan_quet(cu)
    assert not co and "GIỮ hệ số 0" in ly
    tot = [(0.0, .60, .70), (0.6, .66, .74), (0.7, .69, .76), (0.8, .64, .72)]
    co, ly = ket_luan_quet(tot)
    assert co and "0.6–0.7" in ly
    don_le = [(0.0, .60, .70), (0.6, .60, .70), (0.7, .70, .75), (0.8, .60, .69)]            # chỉ MỘT ô cao: nhiễu, không phải dải ổn định
    assert not ket_luan_quet(don_le)[0]
    assert not ket_luan_quet([(0.6, .7, .8)])[0]


def test_bo_dev_hop_le_va_khong_trung_dap_an_bo_kiem_tra():
    from src.index.bo_cau_hoi import MAC_DINH, doc_bo
    if not MAC_DINH.exists():
        pytest.skip("chưa có bộ câu hỏi")
    dev, thu = doc_bo(MAC_DINH, "dev"), doc_bo(MAC_DINH, "kiem_tra")
    assert len({x["id"] for x in dev}) == len(dev) >= 60
    assert all(x["cau_hoi"].strip() and x["dieu"] and all(d.isdigit() for d in x["dieu"]) for x in dev)
    assert all(x["trang_thai"] in ("nhap", "da_duyet") for x in dev)
    chung = {d for x in dev for d in x["dieu"]} & {d for x in thu for d in x["dieu"]}
    assert not chung, f"bộ dev nên dùng Điều khác bộ kiểm tra, trùng: {sorted(chung)}"
    assert not ({x["cau_hoi"].lower() for x in dev} & {x["cau_hoi"].lower() for x in thu})


def test_chon_trai_deu_va_dieu_dap_an():
    ds = [f"dieu {i}" for i in range(1, 401)]
    m = chon_trai_deu(ds, 40)
    assert len(m) == len(set(m)) == 40 and m[0] == "dieu 1" and m == sorted(m, key=ds.index)
    assert any(int(x.split()[1]) > 300 for x in m) and sum(1 for x in m if int(x.split()[1]) < 123) < 20     # trải khắp, không dồn vào Phần chung
    assert chon_trai_deu(ds[:3], 10) == ds[:3] and chon_trai_deu(ds, 0) == [] and chon_trai_deu([], 5) == []
    assert dieu_dap_an([{"cau_hoi": "x", "dieu": ["173"]}, {"cau_hoi": "y", "dieu": ["174", "175"]}]) == {"dieu 173", "dieu 174", "dieu 175"}


def test_loc_dieu_toi_pham_bo_phan_chung():
    d = {f"dieu {n}": {"tieu_de": t, "van_ban": "x", "hash": "h"} for n, t in (
        (1, "Điều 1. Nhiệm vụ của Bộ luật hình sự"), (12, "Điều 12. Tuổi chịu trách nhiệm hình sự"), (123, "Điều 123. Tội giết người"),
        (173, "Điều 173. Tội trộm cắp tài sản"), (338, "Điều 338. Tội vô ý làm lộ bí mật nhà nước; tội làm mất vật"),
        (352, "Điều 352. Khái niệm tội phạm về chức vụ"), (999, "Điều 999a. Tội gì đó"))}
    assert list(loc_dieu_toi_pham(d)) == ["dieu 123", "dieu 173", "dieu 338", "dieu 999"]
