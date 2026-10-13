"""Chỉ mục tìm kiếm (src/index): chia đoạn có ngữ cảnh, cache vector theo mã băm, tìm kiếm lai có lọc theo ngày.
Dùng HashEmbedder (vector giả theo băm từ) nên không cần Ollama; chỉ kiểm đường ống, không đo chất lượng thật."""
import sqlite3

import numpy as np
import pytest

from src.apply.rebuild import rebuild
from src.index.chunks import build_chunks, van_tay
from src.index.embedder import EmbedError, HashEmbedder, OllamaEmbedder
from src.index.search import gop_theo_dieu, tim
from src.index.store import luu_vector, open_index, sync_chunks, thieu_vector, thong_ke

from test_apply_rebuild import D1, P, env  # noqa: F401  (env là fixture)

CU = "Người nào trộm cắp tài sản thì bị phạt tù từ 01 năm đến 03 năm."
MOI = "1. Người nào trộm cắp tài sản của người khác thì bị phạt tù từ 02 năm đến 05 năm."


def dung_chi_muc(env, tmp_path, emb=None):  # noqa: F811
    emb = emb or HashEmbedder()
    idx = open_index(tmp_path / "idx.sqlite")
    sync_chunks(idx, build_chunks(env.c, env.vb))
    thieu = thieu_vector(idx, emb.name)
    luu_vector(idx, emb.name, [r["hash"] for r in thieu], emb.embed([r["text"] for r in thieu]))
    return idx, emb


def sua_dieu3(env):  # noqa: F811
    env.cmd("sua_doi", {"muc_tieu": [{"duong_dan": P("dieu", "3", "khoan", "1")}]}, tu=D1, noi_dung=MOI)
    env.c.commit()
    assert rebuild(env.c, env.vb).n_ok == 1


def test_chia_doan_co_ngu_canh(env):  # noqa: F811
    cs = {c.key: c for c in build_chunks(env.c, env.vb) if c.hieu_luc_den is None}
    assert not [c for c in cs.values() if c.loai in ("phan", "chuong", "muc")]                       # khung không thành đoạn
    d4 = cs["dieu 4"]
    assert d4.text.splitlines()[0] == "Điều 4. Tội lừa đảo" and "lừa đảo thì bị phạt" in d4.text   # Điều có chữ riêng: tiêu đề + chữ
    diem = cs["dieu 3/khoan 2/diem a"]
    assert diem.text.splitlines() == ["Điều 3. Tội trộm cắp",
                                      "Khoản 2: Phạm tội thuộc một trong các trường hợp sau đây thì bị phạt tù từ 03 năm đến 07 năm:",
                                      "Điểm a: có tổ chức;"]                                          # điểm mang tên Điều + câu dẫn khoản
    assert diem.noi_dung == "có tổ chức;" and diem.hash and len(diem.hash) == 64
    assert cs["dieu 3/khoan 1"].text.startswith("Điều 3. Tội trộm cắp\nKhoản 1: ")
    dieu2 = cs["dieu 2"]                                                                              # Điều chỉ có khung: chỉ còn tiêu đề
    assert dieu2.text == "Điều 2. Nguyên tắc" and dieu2.noi_dung == ""


def test_phien_ban_lich_su_va_khoang_rong(env):  # noqa: F811
    sua_dieu3(env)
    cs = [c for c in build_chunks(env.c, env.vb) if c.key == "dieu 3/khoan 1"]
    assert [(c.hieu_luc_tu, c.hieu_luc_den) for c in sorted(cs, key=lambda c: c.hieu_luc_tu)] == [("2016-07-01", D1), (D1, None)]
    assert len({c.hash for c in cs}) == 2                                                             # chữ đổi thì mã băm đổi
    assert all(c.hieu_luc_den is None or c.hieu_luc_den > c.hieu_luc_tu for c in build_chunks(env.c, env.vb))   # bỏ khoảng rỗng


def test_van_tay_doi_khi_du_lieu_doi(env):  # noqa: F811
    a = van_tay(build_chunks(env.c, env.vb))
    assert a == van_tay(build_chunks(env.c, env.vb))
    sua_dieu3(env)
    assert van_tay(build_chunks(env.c, env.vb)) != a


def test_cache_vector_chi_tinh_lai_phan_doi(env, tmp_path):  # noqa: F811
    idx, emb = dung_chi_muc(env, tmp_path)
    st = thong_ke(idx, emb.name)
    assert st["chua_co_vector"] == 0 and st["da_co_vector"] == st["so_chu_khac_nhau"] > 0
    sua_dieu3(env)                                                                                    # đồng bộ lại: id phiên bản đổi, chữ phần lớn giữ nguyên
    sync_chunks(idx, build_chunks(env.c, env.vb))
    thieu = thieu_vector(idx, emb.name)
    assert len(thieu) == 1 and "02 năm đến 05 năm" in thieu[0]["text"]                                # chỉ đoạn mới phải tính
    luu_vector(idx, emb.name, [r["hash"] for r in thieu], emb.embed([r["text"] for r in thieu]))
    assert thong_ke(idx, emb.name)["chua_co_vector"] == 0
    assert thieu_vector(idx, "mo-hinh-khac")                                                          # đổi mô hình thì phải tính lại hết


def test_vector_luu_chuan_hoa_float32(env, tmp_path):  # noqa: F811
    idx, emb = dung_chi_muc(env, tmp_path)
    r = idx.execute("SELECT dim, vec FROM vec_cache LIMIT 1").fetchone()
    v = np.frombuffer(r["vec"], dtype="<f4")
    assert v.shape[0] == r["dim"] == 256 and abs(float(np.linalg.norm(v)) - 1.0) < 1e-4


def test_tim_loc_theo_ngay_truoc_khi_xep_hang(env, tmp_path):  # noqa: F811
    sua_dieu3(env)
    idx, emb = dung_chi_muc(env, tmp_path)
    hien_nay = tim(idx, "trộm cắp tài sản của người khác phạt tù 02 năm đến 05 năm", embedder=emb, ngay="2026-10-02", k=3)
    assert hien_nay.hits[0].key == "dieu 3/khoan 1" and "02 năm đến 05 năm" in hien_nay.hits[0].noi_dung and not hien_nay.canh_bao
    cu = tim(idx, "trộm cắp tài sản của người khác phạt tù 02 năm đến 05 năm", embedder=emb, ngay="2017-12-31", k=10)
    assert all(h.hieu_luc_tu <= "2017-12-31" and (h.hieu_luc_den is None or "2017-12-31" < h.hieu_luc_den) for h in cu.hits)
    khoan1 = [h for h in cu.hits if h.key == "dieu 3/khoan 1"]
    assert khoan1 and "01 năm đến 03 năm" in khoan1[0].noi_dung                                       # bản cũ, không lẫn bản mới
    assert tim(idx, "trộm cắp", embedder=emb, ngay="2016-06-30").hits == []                           # trước ngày hiệu lực


def test_che_do_va_gop_theo_dieu(env, tmp_path):  # noqa: F811
    idx, emb = dung_chi_muc(env, tmp_path)
    for che_do in ("hybrid", "vector", "fts"):
        kq = tim(idx, "trộm cắp tài sản", embedder=emb, ngay="2026-10-02", k=20, che_do=che_do)
        assert kq.hits and kq.hits[0].dieu == "dieu 3"
    kq = tim(idx, "lừa đảo", embedder=emb, ngay="2026-10-02", k=20, che_do="fts")
    assert all(h.hang_vector is None for h in kq.hits) and kq.hits[0].dieu == "dieu 4"
    d = gop_theo_dieu(tim(idx, "trộm cắp tài sản", embedder=emb, ngay="2026-10-02", k=20).hits, 3)
    assert d[0].dieu == "dieu 3" and d[0].tieu_de == "Điều 3. Tội trộm cắp" and d[0].so_doan >= 2
    assert d[0].doan_noi_dung is None or d[0].doan_noi_dung.noi_dung
    with pytest.raises(ValueError):
        tim(idx, "x", embedder=emb, che_do="sai")


def test_thieu_vector_canh_bao_va_sai_mo_hinh(env, tmp_path):  # noqa: F811
    idx = open_index(tmp_path / "i.sqlite")
    sync_chunks(idx, build_chunks(env.c, env.vb))
    emb = HashEmbedder()
    kq = tim(idx, "trộm cắp", embedder=emb, ngay="2026-10-02", che_do="vector")
    assert kq.hits == [] and any("chưa có vector" in w for w in kq.canh_bao)
    kq = tim(idx, "trộm cắp", embedder=emb, ngay="2026-10-02", che_do="hybrid")                        # hybrid vẫn chạy bằng từ khoá
    assert kq.hits and kq.canh_bao
    idx2, _ = dung_chi_muc(env, tmp_path / "x", HashEmbedder(64))
    with pytest.raises(ValueError):                                                                     # vector 64 chiều trong kho, 256 chiều của mô hình
        sqlite3.connect  # (giữ import dùng)
        idx2.execute("UPDATE vec_cache SET model = 'hash:256'")
        tim(idx2, "trộm cắp", embedder=HashEmbedder(256), ngay="2026-10-02", che_do="vector")


def test_fts_khong_vo_vi_ky_tu_dac_biet(env, tmp_path):  # noqa: F811
    idx, emb = dung_chi_muc(env, tmp_path)
    for q in ['trộm "cắp" (tài sản)', "AND OR NOT *", "   ", "Điều 3; khoản 1 -- drop table"]:
        tim(idx, q, embedder=emb, ngay="2026-10-02", che_do="fts")                                      # không được ném lỗi cú pháp FTS


def test_ollama_loi_ro_rang(monkeypatch):
    import urllib.error

    def sap(*a, **k):
        raise urllib.error.URLError("refused")

    monkeypatch.setattr("urllib.request.urlopen", sap)
    monkeypatch.setattr("time.sleep", lambda s: None)
    with pytest.raises(EmbedError, match="không kết nối được Ollama"):
        OllamaEmbedder(retries=2).embed(["x"])


def test_danh_gia_xep_hang_dap_an(env, tmp_path):  # noqa: F811
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "scripts"))
    from danh_gia import NhoTam, hang_dap_an

    idx, emb = dung_chi_muc(env, tmp_path)
    nho = NhoTam(emb)
    r, top1 = hang_dap_an(idx, {"cau_hoi": "trộm cắp tài sản", "dieu": ["3"]}, nho, "hybrid", "2026-10-02")
    assert r == 1 and top1.startswith("Điều 3.")
    r, _ = hang_dap_an(idx, {"cau_hoi": "trộm cắp tài sản", "dieu": ["999"]}, nho, "fts", "2026-10-02")
    assert r is None                                                                                   # đáp án không có -> không hạng
    r, _ = hang_dap_an(idx, {"cau_hoi": "trộm cắp tài sản", "dieu": ["4", "3"]}, nho, "fts", "2026-10-02")
    assert r == 1                                                                                      # chấp nhận nhiều Điều
    assert len(nho.cache) == 1                                                                         # nhúng câu hỏi 1 lần


def test_tu_dung_va_trong_so_fts(env, tmp_path):  # noqa: F811
    from src.index.search import _tu_khoa

    assert _tu_khoa("lấy của người khác") == '"lấy" OR "của" OR "người" OR "khác"'                    # mặc định giữ nguyên
    assert _tu_khoa("lấy của người khác", bo_tu_dung=True) == '"lấy" OR "khác"'
    idx, emb = dung_chi_muc(env, tmp_path)
    a = tim(idx, "trộm cắp tài sản", embedder=emb, ngay="2026-10-02", k=5, trong_fts=0.0)
    b = tim(idx, "trộm cắp tài sản", embedder=emb, ngay="2026-10-02", k=5, che_do="vector")
    assert [h.phien_ban_id for h in a.hits] == [h.phien_ban_id for h in b.hits]                       # trọng số 0 = chỉ vector
    tim(idx, "của và là", embedder=emb, ngay="2026-10-02", che_do="fts", bo_tu_dung=True)              # toàn từ dừng: không lỗi
