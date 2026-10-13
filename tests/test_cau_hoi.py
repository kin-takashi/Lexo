"""Câu hỏi sinh sẵn (src/index/cau_hoi): gom chữ Điều, lọc đầu ra LLM, lưu/sinh lại theo mã băm, và nâng điểm khi tìm kiếm."""
import json

import pytest

from src.index.cau_hoi import (LLMGia, can_sinh, doc_ket_qua, don_cau_hoi_mo_coi, gom_dieu, loc_cau_hoi, luu_cau_hoi, sinh_mot)
from src.index.chunks import build_chunks
from src.index.embedder import HashEmbedder
from src.index.search import tim
from src.index.store import don_dep, luu_vector, open_index, sync_chunks, thieu_vector, thieu_vector_cau_hoi

from test_apply_rebuild import D1, P, env  # noqa: F401
from test_index import MOI, sua_dieu3  # noqa: F401


def moi_chi_muc(env, tmp_path):  # noqa: F811
    idx = open_index(tmp_path / "idx.sqlite")
    sync_chunks(idx, build_chunks(env.c, env.vb))
    return idx


def test_gom_dieu_ghep_khoan_diem_va_bo_dieu_chi_co_tieu_de(env, tmp_path):  # noqa: F811
    d = gom_dieu(moi_chi_muc(env, tmp_path))
    assert "Khoản 1:" in d["dieu 2"]["van_ban"]
    idx = moi_chi_muc(env, tmp_path / "b")
    idx.execute("INSERT INTO chunk VALUES (9999, 1, 'dieu 99', 'dieu', '2016-07-01', NULL, '', 'Điều 99. Chỉ có tiêu đề', 'x')")
    assert "dieu 99" not in gom_dieu(idx)                                          # Điều chỉ có tiêu đề: không có gì để hỏi
    vb = d["dieu 3"]["van_ban"].splitlines()
    assert vb[0] == "Điều 3. Tội trộm cắp" and any(x.startswith("Khoản 2:") for x in vb) and "Điểm a: có tổ chức;" in vb
    assert len(d["dieu 3"]["hash"]) == 64


def test_doc_ket_qua_json_va_dong_tu_do():
    assert doc_ket_qua('{"cau_hoi": ["a b c d e f", "g h i k l m"]}') == ["a b c d e f", "g h i k l m"]
    assert doc_ket_qua('rác {"cau_hoi": ["a b c d e f"]} rác') == ["a b c d e f"]
    assert doc_ket_qua('1. lén lấy xe của hàng xóm thì sao\n- bị bắt thì sao đây nhỉ\nxin chào') == ["lén lấy xe của hàng xóm thì sao", "bị bắt thì sao đây nhỉ"]


def test_loc_cau_hoi():
    td = "Điều 173. Tội trộm cắp tài sản"
    ds = ["lén lấy xe máy của hàng xóm bị phạt sao",
          "lén lấy xe máy của hàng xóm bị phạt sao",              # trùng
          "Điều 173 quy định gì",                                  # từ cấm
          "phạm tội gì khi lấy đồ người khác",                     # từ cấm: tội
          "trộm cắp tài sản thì bị phạt thế nào",                  # chép nguyên tên Điều
          "xe máy",                                                # quá ngắn
          "tôi bị truy cứu trách nhiệm hình sự chưa vậy trời",     # từ cấm
          "vào nhà lấy trộm laptop của bạn cùng phòng thì sao"]
    assert loc_cau_hoi(ds, td) == ["lén lấy xe máy của hàng xóm bị phạt sao", "vào nhà lấy trộm laptop của bạn cùng phòng thì sao"]
    assert loc_cau_hoi(["tội ác là gì vậy bạn ơi nhỉ"], td) == []    # 'tội' là từ cấm theo ranh giới từ
    assert loc_cau_hoi(["đi tới tối rồi mới về nhà nha"], td) == ["đi tới tối rồi mới về nhà nha"]   # 'tối' không bị nhầm với 'tội'


def test_sinh_luu_lai_theo_ma_bam_va_don_mo_coi(env, tmp_path):  # noqa: F811
    idx = moi_chi_muc(env, tmp_path)
    llm = LLMGia()
    d = gom_dieu(idx)
    thieu = can_sinh(idx, d, llm.name)
    assert "dieu 3" in thieu
    for k in thieu:
        ds = sinh_mot(llm, d[k], 5)
        assert len(ds) >= 3
        luu_cau_hoi(idx, k, d[k]["hash"], llm.name, ds)
    n_goi = llm.so_lan
    assert can_sinh(idx, d, llm.name) == []                                         # chạy lại: không còn gì để sinh
    assert can_sinh(idx, d, "ollama:khac") == list(d)                               # đổi LLM thì sinh lại
    sua_dieu3(env)                                                                  # Điều 3 đổi chữ
    sync_chunks(idx, build_chunks(env.c, env.vb))
    d2 = gom_dieu(idx)
    assert can_sinh(idx, d2, llm.name) == ["dieu 3"] and llm.so_lan == n_goi         # chỉ Điều đổi chữ phải sinh lại
    assert don_cau_hoi_mo_coi(idx, {"dieu 3": d2["dieu 3"]}) == (len(d) - 1) * 5   # Điều không còn trong danh sách bị xoá


def test_vector_cau_hoi_song_sot_don_dep(env, tmp_path):  # noqa: F811
    idx = moi_chi_muc(env, tmp_path)
    emb = HashEmbedder()
    luu_cau_hoi(idx, "dieu 3", "h", "gia", ["lấy trộm xe máy hàng xóm thì sao", "bị bắt vì lấy đồ người khác"])
    t = thieu_vector_cau_hoi(idx, emb.name)
    assert len(t) == 2
    luu_vector(idx, emb.name, [r["hash"] for r in t], emb.embed([r["text"] for r in t]))
    assert thieu_vector_cau_hoi(idx, emb.name) == []
    don_dep(idx)                                                                    # dọn vector mồ côi không được xoá vector câu hỏi
    assert thieu_vector_cau_hoi(idx, emb.name) == []


def test_tim_nang_diem_nho_cau_hoi(env, tmp_path):  # noqa: F811
    from src.index.cau_hoi import lam_moi_theo_phien_ban_lenh
    idx = moi_chi_muc(env, tmp_path)
    lam_moi_theo_phien_ban_lenh(idx)                                                # ghi phiên bản lời nhắc hiện hành
    emb = HashEmbedder()
    t = thieu_vector(idx, emb.name)
    luu_vector(idx, emb.name, [r["hash"] for r in t], emb.embed([r["text"] for r in t]))
    q = "lấy trộm xe máy hàng xóm"                                                  # chữ này không có trong luật thử
    truoc = tim(idx, q, embedder=emb, ngay="2026-10-02", che_do="vector", k=50)
    d3 = [h for h in truoc.hits if h.dieu == "dieu 3"]
    luu_cau_hoi(idx, "dieu 3", "h", "gia", ["lấy trộm xe máy hàng xóm", "bị bắt vì lấy đồ người khác"])
    tv = thieu_vector_cau_hoi(idx, emb.name)
    luu_vector(idx, emb.name, [r["hash"] for r in tv], emb.embed([r["text"] for r in tv]))
    sau = tim(idx, q, embedder=emb, ngay="2026-10-02", che_do="vector", k=50, he_so_cau_hoi=1.0)
    assert sau.hits[0].dieu == "dieu 3" and sau.hits[0].cosine > 0.9                 # câu hỏi trùng -> cosine ~1
    assert max(h.cosine for h in d3) < sau.hits[0].cosine
    tam = tim(idx, q, embedder=emb, ngay="2026-10-02", che_do="vector", k=50, he_so_cau_hoi=0.5)
    d3_tam = next(h for h in tam.hits if h.dieu == "dieu 3")
    assert d3_tam.cosine >= 0.5 and d3_tam.cosine < sau.hits[0].cosine               # hệ số 0.5 co điểm câu hỏi xuống còn ~0.5
    kq = tim(idx, q, embedder=emb, ngay="2026-10-02", che_do="vector", he_so_cau_hoi=0)
    assert [h.phien_ban_id for h in kq.hits] == [h.phien_ban_id for h in tim(idx, q, embedder=emb, ngay="2026-10-02", che_do="vector").hits]


def test_tim_canh_bao_khi_chua_co_cau_hoi(env, tmp_path):  # noqa: F811
    idx = moi_chi_muc(env, tmp_path)
    emb = HashEmbedder()
    t = thieu_vector(idx, emb.name)
    luu_vector(idx, emb.name, [r["hash"] for r in t], emb.embed([r["text"] for r in t]))
    kq = tim(idx, "trộm cắp", embedder=emb, ngay="2026-10-02", che_do="vector", he_so_cau_hoi=0.9)
    assert kq.hits and any("câu hỏi sinh sẵn" in w for w in kq.canh_bao)


def test_loi_nhac_khong_chua_noi_dung_bo_kiem_tra():
    """Chặn rò rỉ: không một cụm 4 từ liên tiếp nào của câu trong eval/bo_cau_hoi.json (mọi tập) xuất hiện trong lời nhắc gửi cho LLM."""
    import re

    from src.index.bo_cau_hoi import MAC_DINH, doc_bo
    from src.index.cau_hoi import PROMPT
    if not MAC_DINH.exists():
        pytest.skip("chưa có bộ kiểm tra")
    f = lambda t: re.findall(r"\w+", t.lower())  # noqa: E731
    nhac = " ".join(f(PROMPT))
    for x in doc_bo(MAC_DINH, None, None):
        w = f(x["cau_hoi"])
        for i in range(len(w) - 3):
            assert " ".join(w[i:i + 4]) not in nhac, f"lời nhắc chứa cụm của câu {x['id']}: {' '.join(w[i:i + 4])}"


def test_tim_khong_dung_cau_sinh_bang_loi_nhac_cu(env, tmp_path):  # noqa: F811
    """Chỉ mục cũ (không ghi phiên bản lời nhắc) vẫn chứa câu chép ví dụ; dùng chúng làm Hit@1 giảm từ 64% xuống 26%. Phải bỏ qua và báo."""
    idx = moi_chi_muc(env, tmp_path)
    emb = HashEmbedder()
    t = thieu_vector(idx, emb.name)
    luu_vector(idx, emb.name, [r["hash"] for r in t], emb.embed([r["text"] for r in t]))
    q = "lấy trộm xe máy hàng xóm"
    luu_cau_hoi(idx, "dieu 3", "h", "gia", [q])
    tv = thieu_vector_cau_hoi(idx, emb.name)
    luu_vector(idx, emb.name, [r["hash"] for r in tv], emb.embed([r["text"] for r in tv]))
    co = tim(idx, q, embedder=emb, ngay="2026-10-02", che_do="vector", k=50, he_so_cau_hoi=1.0)
    khong = tim(idx, q, embedder=emb, ngay="2026-10-02", che_do="vector", k=50)
    assert any("lời nhắc cũ" in w for w in co.canh_bao)
    assert [h.phien_ban_id for h in co.hits] == [h.phien_ban_id for h in khong.hits]      # y như không dùng


def test_loc_bo_chu_nuoc_ngoai():
    td = "Điều 186. Tội từ chối hoặc trốn tránh nghĩa vụ cấp dưỡng"
    assert loc_cau_hoi(["hôn nhân ly hôn không trả抚养费 cho con", "ly hôn rồi chồng không chịu gửi tiền cho con"], td) == \
        ["ly hôn rồi chồng không chịu gửi tiền cho con"]


def test_loc_vong_va_tim_chi_dung_cau_giu(env, tmp_path):  # noqa: F811
    from src.index.cau_hoi import hang_dieu_cua_cau_hoi, lam_moi_theo_phien_ban_lenh, loc_vong
    idx = moi_chi_muc(env, tmp_path)
    lam_moi_theo_phien_ban_lenh(idx)
    emb = HashEmbedder()
    t = thieu_vector(idx, emb.name)
    luu_vector(idx, emb.name, [r["hash"] for r in t], emb.embed([r["text"] for r in t]))
    tot, la = "trộm cắp tài sản của người khác", "lừa đảo chiếm đoạt tiền bạc thủ đoạn gian dối"       # câu thứ hai lạc sang Điều 4
    h = hang_dieu_cua_cau_hoi(idx, emb, ["dieu 3", "dieu 3", "dieu 999"], [tot, la, tot])
    assert h[0] == 1 and h[1] > 1 and h[2] is None
    luu_cau_hoi(idx, "dieu 3", "h", "gia", [tot, la])
    tv = thieu_vector_cau_hoi(idx, emb.name)
    luu_vector(idx, emb.name, [r["hash"] for r in tv], emb.embed([r["text"] for r in tv]))
    st = loc_vong(idx, emb.name, top=1)
    assert st == {"so_cau": 2, "giu": 1, "hang1": 1}
    giu = [r["cau_hoi"] for r in idx.execute("SELECT cau_hoi FROM cau_hoi_sinh WHERE giu = 1")]
    assert giu == [tot]
    kq = tim(idx, la, embedder=emb, ngay="2026-10-02", che_do="vector", k=50, he_so_cau_hoi=1.0)   # câu bị lọc không được nâng điểm Điều 3
    d3 = next(h for h in kq.hits if h.dieu == "dieu 3")
    assert d3.cosine < 0.99
    assert loc_vong(idx, emb.name, top=0)["giu"] == 2


def test_lam_moi_theo_phien_ban_lenh(env, tmp_path):  # noqa: F811
    from src.index import cau_hoi as ch
    idx = moi_chi_muc(env, tmp_path)
    luu_cau_hoi(idx, "dieu 3", "h", "gia", ["a b c d e f"])
    assert ch.lam_moi_theo_phien_ban_lenh(idx) == 1          # chưa ghi phiên bản (sinh trước khi có cơ chế) -> bỏ
    luu_cau_hoi(idx, "dieu 3", "h", "gia", ["a b c d e f"])
    assert ch.lam_moi_theo_phien_ban_lenh(idx) == 0          # cùng phiên bản: giữ
    cu = ch.PHIEN_BAN_LENH
    try:
        ch.PHIEN_BAN_LENH = "v-moi"
        assert ch.lam_moi_theo_phien_ban_lenh(idx) == 1      # đổi lời nhắc: xoá để sinh lại
    finally:
        ch.PHIEN_BAN_LENH = cu


def test_chi_muc_cu_chua_co_cot_giu_van_mo_duoc(tmp_path):
    import sqlite3
    p = tmp_path / "cu.sqlite"
    c = sqlite3.connect(p)
    c.executescript("CREATE TABLE cau_hoi_sinh (dieu TEXT NOT NULL, hash_dieu TEXT NOT NULL, mo_hinh TEXT NOT NULL, stt INTEGER NOT NULL, "
                    "cau_hoi TEXT NOT NULL, hash TEXT NOT NULL, PRIMARY KEY (dieu, mo_hinh, stt)); "
                    "INSERT INTO cau_hoi_sinh VALUES ('dieu 1','h','m',1,'x','hh');")
    c.commit()
    c.close()
    idx = open_index(p)
    assert idx.execute("SELECT giu FROM cau_hoi_sinh").fetchone()[0] == 1


class _Resp:
    def __init__(self, obj):
        self.b = json.dumps(obj).encode("utf-8")

    def read(self):
        return self.b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _bat_yeu_cau(monkeypatch, tra_ve):
    got = {}

    def gia(req, timeout=None):
        got["body"] = json.loads(req.data.decode("utf-8"))
        got["url"] = req.full_url
        return _Resp(tra_ve)

    monkeypatch.setattr("urllib.request.urlopen", gia)
    return got


def test_qwen3_tat_think(monkeypatch):
    from src.index.cau_hoi import OllamaLLM
    got = _bat_yeu_cau(monkeypatch, {"message": {"content": '{"cau_hoi": ["a b c d e f"]}'}})
    llm = OllamaLLM("qwen3:8b")
    assert llm.hoi("viết câu hỏi") == '{"cau_hoi": ["a b c d e f"]}'
    b = got["body"]
    assert got["url"].endswith("/api/chat") and b["think"] is False and b["format"] == "json" and b["stream"] is False
    assert b["messages"][0]["content"].endswith("/no_think") and b["options"]["top_k"] == 20
    assert not llm.da_thay_think


def test_qwen3_gỡ_khoi_think_va_bao_khi_van_nghi(monkeypatch):
    from src.index.cau_hoi import OllamaLLM
    _bat_yeu_cau(monkeypatch, {"message": {"content": '<think>nghĩ {linh tinh}</think>{"cau_hoi": ["a b c d e f"]}'}})
    llm = OllamaLLM("qwen3:8b")
    assert llm.hoi("x") == '{"cau_hoi": ["a b c d e f"]}'
    assert llm.da_thay_think                                              # Ollama cũ bỏ qua think: phải báo
    _bat_yeu_cau(monkeypatch, {"message": {"content": '{"cau_hoi": []}', "thinking": "đang nghĩ"}})
    llm = OllamaLLM("qwen3:8b")
    llm.hoi("x")
    assert llm.da_thay_think


def test_model_khac_khong_gui_think(monkeypatch):
    from src.index.cau_hoi import OllamaLLM
    got = _bat_yeu_cau(monkeypatch, {"message": {"content": "{}"}})
    OllamaLLM("qwen2.5:3b").hoi("viết")
    assert "think" not in got["body"] and not got["body"]["messages"][0]["content"].endswith("/no_think")   # qwen2.5 không hỗ trợ think
    got = _bat_yeu_cau(monkeypatch, {"message": {"content": "{}"}})
    OllamaLLM("qwen3:8b", think=True).hoi("viết")                          # bật tường minh thì tôn trọng
    assert got["body"]["think"] is True and not got["body"]["messages"][0]["content"].endswith("/no_think")


def test_chon_mo_hinh_uu_tien_qwen3_8b(monkeypatch):
    from src.index import cau_hoi as ch
    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp({"models": [{"name": "qwen2.5:3b"}, {"name": "qwen3:8b"}, {"name": "llama3.2:3b"}]}))
    assert ch.chon_mo_hinh()[0] == "qwen3:8b"
