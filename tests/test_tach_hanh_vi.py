"""Tách tình huống thành hành vi bằng LLM (src/index/tach_hanh_vi, scripts/tach_hanh_vi.py): lời nhắc, ví dụ mẫu, đọc kết quả, thử lại, gọi Ollama."""
import importlib.util
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

from src.index.bo_cau_hoi import MAC_DINH, doc_bo
from src.index.tach_hanh_vi import (HE_THONG, KIEU, LLMGiaTach, SCHEMA, TachError, TachLLM, bo_tien_to, chon_vi_du, doc_hanh_vi, dong_ra,
                                    dung_tin_nhan, he_thong, tach_mot, tach_tien_to)
from src.index.tap_train import MAC_DINH as TRAIN, doc_train, tap_cua

ROOT = Path(__file__).resolve().parents[1]


def mau(id_, ds, loai="nhieu", **kw):
    """ds: danh sách (mô tả, Điều)."""
    x = {"id": id_, "tinh_huong": f"tình huống của {id_}", "hanh_vi": [{"mo_ta": m, "dieu": [d]} for m, d in ds], "loai": loai, "nguon": "claude", "trang_thai": "nhap"}
    x.update(kw)
    return x


def test_tach_tien_to():
    assert tach_tien_to("Hiếp dâm: dùng vũ lực ép nạn nhân") == ("Hiếp dâm", "dùng vũ lực ép nạn nhân")
    assert tach_tien_to("Lừa đảo chiếm đoạt 800 triệu đồng: dùng giấy tờ giả") == ("Lừa đảo chiếm đoạt 800 triệu đồng", "dùng giấy tờ giả")
    assert tach_tien_to("Dùng dao uy hiếp nữ công nhân để cướp") == (None, "Dùng dao uy hiếp nữ công nhân để cướp")
    assert tach_tien_to("A: b")[0] is None                                         # tiền tố quá ngắn (< 3 ký tự) không phải tên tội
    assert tach_tien_to("một hai ba " * 8 + ": x")[0] is None                     # > 20 từ: là câu thường có dấu hai chấm


def test_bo_tien_to_viet_hoa_chu_dau():
    assert bo_tien_to("Hiếp dâm: dùng vũ lực ép nạn nhân") == "Dùng vũ lực ép nạn nhân"
    assert bo_tien_to("Giết người") == "Giết người"


def test_he_thong_giu_nguyen_chu_cua_tap_train():
    assert he_thong("thuan") == HE_THONG                                           # so sánh công bằng với mô hình tinh chỉnh sau này
    assert he_thong("ten_toi").startswith(HE_THONG) and "tên tội" in he_thong("ten_toi")
    assert "Quy tắc tách" in he_thong("thuan", quy_tac=True) and "Quy tắc tách" not in he_thong("thuan")
    with pytest.raises(ValueError):
        he_thong("khac")


def test_chon_vi_du_loai_dieu_cam_va_phan_val_va_kieu():
    # chỉ giữ mẫu thuộc phần train (tap_cua theo băm id); tự dựng id để chắc chắn có cả train lẫn val
    ids_train = [f"x{i}" for i in range(400) if tap_cua(f"x{i}") == "train"][:6]
    ids_val = [f"x{i}" for i in range(400) if tap_cua(f"x{i}") == "val"][:1]
    ms = [mau(ids_train[0], [("Hiếp dâm: a", "141"), ("Cướp tài sản: b", "168")]), mau(ids_train[1], [("Dâm ô: a", "146")], loai="don"),
          mau(ids_train[2], [("Giết người: a", "123"), ("Che giấu tội phạm: b", "389")]), mau(ids_train[3], [("không tiền tố", "133"), ("Vu khống: x", "156")]),
          mau(ids_train[4], [("Trộm: a", "173"), ("Hủy hoại: b", "178")]), mau(ids_val[0], [("Đe dọa: a", "133"), ("Làm nhục: b", "155")])]
    ct = chon_vi_du(ms, 3, {"168"}, "ten_toi")
    ds = [{d for h in x["hanh_vi"] for d in h["dieu"]} for x in ct]
    assert [len(x["hanh_vi"]) for x in ct][1] == 1 and len(ct) == 3                 # mẫu thứ hai là mẫu một hành vi
    assert all("168" not in d for d in ds)                                          # Điều bị cấm không xuất hiện
    assert all(ids_val[0] != x["id"] for x in ct)                                   # không lấy phần val
    assert sum(len(d) for d in ds) == len(set().union(*ds))                         # các ví dụ không chung Điều
    assert ids_train[3] not in [x["id"] for x in ct]                                # kiểu ten_toi bỏ mẫu có hành vi thiếu tiền tố
    assert chon_vi_du(ms, 0, set(), "thuan") == []
    assert ids_train[3] in [x["id"] for x in chon_vi_du(ms, 5, set(), "thuan")]     # kiểu thuan thì lấy được
    assert [x["id"] for x in chon_vi_du(ms, 3, {"168"}, "ten_toi")] == [x["id"] for x in ct]            # xác định


def test_dong_ra_giu_hoac_bo_tien_to():
    x = mau("t1", [("Hiếp dâm: dùng vũ lực", "141"), ("Dùng dao cướp", "168")])
    assert json.loads(dong_ra(x, "ten_toi"))["hanh_vi"] == ["Hiếp dâm: dùng vũ lực", "Dùng dao cướp"]
    assert json.loads(dong_ra(x, "thuan"))["hanh_vi"] == ["Dùng vũ lực", "Dùng dao cướp"]


def test_dung_tin_nhan_thu_tu_vai_tro():
    vd = [mau("t1", [("Hiếp dâm: a", "141"), ("Cướp tài sản: b", "168")])]
    tn = dung_tin_nhan("tình huống cần tách", "ten_toi", vd)
    assert [m["role"] for m in tn] == ["system", "user", "assistant", "user"] and tn[-1]["content"] == "tình huống cần tách"
    assert [m["role"] for m in dung_tin_nhan("x", "thuan")] == ["system", "user"]


def test_doc_hanh_vi_chiu_duoc_dinh_dang_khac_nhau():
    assert doc_hanh_vi('{"hanh_vi": ["a", "b"]}') == ["a", "b"]
    assert doc_hanh_vi('<think>nghĩ...</think>\n```json\n{"hanh_vi": [" a ", "a", "", "b"]}\n```') == ["a", "b"]           # gỡ khối nghĩ, rào mã, trùng, rỗng
    assert doc_hanh_vi('Đây là kết quả: {"hanh_vi": ["a"]} xin cảm ơn') == ["a"]
    assert len(doc_hanh_vi(json.dumps({"hanh_vi": [f"h{i}" for i in range(20)]}))) == 8                     # tối đa 8 hành vi
    for xau in ("", "không phải json", '{"khac": [1]}', '{"hanh_vi": []}', '{"hanh_vi": "abc"}', '{"hanh_vi": [1, 2]}'):
        with pytest.raises(TachError):
            doc_hanh_vi(xau)


class LLMKichBan:
    """LLM giả theo kịch bản: trả lần lượt các câu cho trước, ghi lại seed / nhiệt độ mỗi lần gọi."""

    def __init__(self, tra):
        self.tra, self.goi, self.seed, self.nhiet = list(tra), [], 0, 0.0

    def hoi(self, tn):
        self.goi.append((self.seed, self.nhiet))
        return self.tra.pop(0)


def test_tach_mot_thu_lai_doi_seed_va_nhiet_do():
    llm = LLMKichBan(["rác", '{"hanh_vi": ["a", "b"]}'])
    r = tach_mot(llm, "tình huống", "thuan")
    assert r["hanh_vi"] == ["a", "b"] and r["so_lan"] == 2 and r["loi"] is None
    assert llm.goi == [(0, 0.0), (1, 0.3)]


def test_tach_mot_het_lan_thu_thi_tra_nguyen_tinh_huong_va_ghi_loi():
    llm = LLMKichBan(["rác", "rác", "rác"])
    r = tach_mot(llm, "tình huống gốc", "thuan")
    assert r["hanh_vi"] == ["tình huống gốc"] and r["loi"] and r["so_lan"] == 3                              # không giấu lỗi, không bỏ câu


def test_llm_gia_tach_theo_cau():
    r = tach_mot(LLMGiaTach(), "Việc một. Việc hai! Việc ba?", "thuan")
    assert r["hanh_vi"] == ["Việc một.", "Việc hai!", "Việc ba?"]


def test_body_gui_ollama_dung_dinh_dang():
    llm = TachLLM("qwen3:4b", "http://x")
    tn = dung_tin_nhan("tình huống", "thuan")
    b = llm._body(tn)
    assert b["format"] == SCHEMA and b["think"] is False and b["stream"] is False and b["options"]["temperature"] == 0.0
    assert b["messages"][-1]["content"].endswith("/no_think") and tn[-1]["content"] == "tình huống"                # không sửa hội thoại gốc của người gọi
    assert TachLLM("qwen3:4b", "http://x", dinh_dang="json")._body(tn)["format"] == "json"
    assert "think" not in TachLLM("llama3.2:3b", "http://x")._body(tn)                                          # không phải họ Qwen3: không gửi think


def test_body_khong_no_think_van_gui_think_false():
    tn = dung_tin_nhan("tình huống", "thuan")
    b = TachLLM("qwen3-8b-lexo-tach", "http://x", no_think_mem=False)._body(tn)
    assert b["think"] is False and b["messages"][-1]["content"] == "tình huống"                                 # lời nhắc y như lúc học
    assert tn == dung_tin_nhan("tình huống", "thuan")


def test_goi_ollama_that_qua_may_chu_gia():
    nhan = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            nhan.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            ra = json.dumps({"message": {"content": '{"hanh_vi": ["Việc một", "Việc hai"]}'}}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(ra)))
            self.end_headers()
            self.wfile.write(ra)

        def log_message(self, *a):
            pass

    sv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=sv.serve_forever, daemon=True).start()
    try:
        llm = TachLLM("qwen3:4b", f"http://127.0.0.1:{sv.server_port}", timeout=10)
        r = tach_mot(llm, "tình huống", "ten_toi")
    finally:
        sv.shutdown()
    assert r["hanh_vi"] == ["Việc một", "Việc hai"] and nhan[0][0] == "/api/chat"
    assert nhan[0][1]["model"] == "qwen3:4b" and nhan[0][1]["format"] == SCHEMA and nhan[0][1]["messages"][0]["role"] == "system"


def nap_script():
    spec = importlib.util.spec_from_file_location("tach_hanh_vi_script", ROOT / "scripts" / "tach_hanh_vi.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def chay(mod, monkeypatch, *argv):
    monkeypatch.setattr("sys.argv", ["tach_hanh_vi.py", *argv])
    return mod.main()


def test_script_tap_dong_bang_can_da_chot_va_khong_ghi_de(tmp_path, monkeypatch):
    if not MAC_DINH.exists() or not TRAIN.exists():
        pytest.skip("chưa có eval/bo_cau_hoi.json hoặc train/tinh_huong.json")
    mod = nap_script()
    ra = tmp_path / "kq.json"
    with pytest.raises(SystemExit, match="đóng băng"):
        chay(mod, monkeypatch, "--tap", "kiem_tra", "--ra", str(ra))
    assert chay(mod, monkeypatch, "--tap", "kiem_tra", "--ra", str(ra), "--da-chot", "--gia") == 0         # chạy giả hợp lệ
    assert set(json.loads(ra.read_text(encoding="utf-8"))) == {c["id"] for c in doc_bo(MAC_DINH, "kiem_tra", "nhieu_dieu")}
    assert (tmp_path / "kq.log.jsonl").exists()
    with pytest.raises(SystemExit, match="đã có"):
        chay(mod, monkeypatch, "--tap", "kiem_tra", "--ra", str(ra), "--da-chot", "--gia")
    assert chay(mod, monkeypatch, "--tap", "kiem_tra", "--ra", str(ra), "--da-chot", "--gia", "--ghi-de") == 0


def test_script_dev_chay_gia_va_danh_gia_doc_duoc_file(tmp_path, monkeypatch):
    if not MAC_DINH.exists() or not TRAIN.exists():
        pytest.skip("chưa có eval/bo_cau_hoi.json hoặc train/tinh_huong.json")
    mod = nap_script()
    ra = tmp_path / "dev.json"
    assert chay(mod, monkeypatch, "--tap", "dev", "--gia", "--ra", str(ra), "--kieu", "thuan", "--vi-du", "3") == 0
    kq = json.loads(ra.read_text(encoding="utf-8"))
    bo = doc_bo(MAC_DINH, "dev", "nhieu_dieu")
    assert set(kq) == {c["id"] for c in bo} and all(isinstance(v, list) and v for v in kq.values())
    spec = importlib.util.spec_from_file_location("danh_gia_nhieu_s", ROOT / "scripts" / "danh_gia_nhieu.py")
    dg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dg)
    assert dg.doc_du_doan(ra, bo)[bo[0]["id"]] == kq[bo[0]["id"]]                  # file do tach_hanh_vi.py tạo ra đúng định dạng --du-doan


def test_vi_du_mau_khong_trung_dieu_voi_bo_do_nhieu_dieu():
    if not MAC_DINH.exists() or not TRAIN.exists():
        pytest.skip("chưa có eval/bo_cau_hoi.json hoặc train/tinh_huong.json")
    cam = {d for c in doc_bo(MAC_DINH, None, "nhieu_dieu") for d in c["dieu"]}
    for kieu in KIEU:
        vd = chon_vi_du(doc_train(TRAIN), 3, cam, kieu)
        assert len(vd) == 3, kieu
        assert not ({d for x in vd for h in x["hanh_vi"] for d in h["dieu"]} & cam), kieu
