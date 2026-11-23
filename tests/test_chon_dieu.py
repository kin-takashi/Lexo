"""Kiểm thử việc «chọn Điều từ ứng viên» (src/ban_an/chon_dieu.py), dựng gói Kaggle (src/ban_an/goi_kaggle.py)
và script đo scripts/do_ban_an.py ở chế độ giả (không cần Ollama). Mọi dữ liệu ở đây là giả lập."""
from __future__ import annotations

import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from src.ban_an import chon_dieu as cd
from src.ban_an import goi_kaggle as gk
from src.index.chunks import Chunk, hash_text
from src.index.embedder import HashEmbedder
from src.index.store import luu_vector, open_index, sync_chunks

ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------------------------------------------------------
# chon_dieu: đầu vào
# --------------------------------------------------------------------------------------------------------------------


def test_cat_su_viec_giu_dau_cuoi_va_xuong_dong():
    chu = "\n".join(f"dòng {i} " + " ".join(f"t{i}_{j}" for j in range(9)) for i in range(50))   # 50 dòng x 10 từ
    ra, da_cat = cd.cat_su_viec(chu, dau=30, cuoi=20)
    assert da_cat
    dau, cuoi = ra.split(f"\n{cd.DAU_LUOC}\n")
    assert len(dau.split()) == 30 and len(cuoi.split()) == 20
    assert dau.startswith("dòng 0 ") and cuoi.endswith("t49_8")
    assert "\n" in dau                                           # xuống dòng của phần còn lại được giữ
    assert cd.cat_su_viec("  ngắn thôi  ", 30, 20) == ("ngắn thôi", False)


def test_chia_doan_gop_doan_cuoi_qua_ngan():
    chu = " ".join(str(i) for i in range(650))
    doan = cd.chia_doan(chu, 300)
    assert [len(d.split()) for d in doan] == [300, 350]            # 50 từ cuối < 300/3 nên gộp vào đoạn trước
    assert [len(d.split()) for d in cd.chia_doan(" ".join("x" * 1 for _ in range(700)), 300)] == [300, 300, 100]
    assert cd.chia_doan("   ") == []


def test_ngay_tra_cuu_khong_som_hon_blhs_2015():
    assert cd.ngay_tra_cuu("2016-05-01") == cd.NGAY_BLHS_2015
    assert cd.ngay_tra_cuu("2023-02-03") == "2023-02-03"
    assert cd.ngay_tra_cuu(None) is None


def test_so_dieu_sap_xep_va_pham_vi_toi_pham():
    assert cd.sap_xep(["251", "217a", "217", "123", "251"]) == ["123", "217", "217a", "251"]
    assert cd.la_dieu_toi_pham("108") and cd.la_dieu_toi_pham("425") and cd.la_dieu_toi_pham("217a")
    assert not cd.la_dieu_toi_pham("51") and not cd.la_dieu_toi_pham("426") and not cd.la_dieu_toi_pham("abc")
    with pytest.raises(cd.ChonError):
        cd.khoa_so("Điều x")


# --------------------------------------------------------------------------------------------------------------------
# chon_dieu: ứng viên, chọn K
# --------------------------------------------------------------------------------------------------------------------


def test_gop_rrf_cong_diem_cac_danh_sach():
    assert cd.gop_rrf([["173", "174"], ["174", "168"], ["174"]])[:2] == ["174", "173"]
    assert cd.gop_rrf([["200"], ["150"]]) == ["150", "200"]       # hòa điểm, hòa hạng: theo số Điều (xác định)


def test_bang_recall_va_chon_k():
    mau = [{"dieu": ["173"], "xep_hang": {"vector": ["173", "1"], "fts": ["9"] * 5 + ["173"], "hybrid": ["173"]}},
           {"dieu": ["174", "168"], "xep_hang": {"vector": ["174", "x", "y", "168"], "fts": ["174"], "hybrid": ["174", "168"]}}]
    bang = cd.bang_recall(mau, ks=(1, 3, 5, 10))
    assert bang["vector"][3] == {"recall": 0.75, "du": 0.5}
    assert bang["vector"][5]["du"] == 1.0 and bang["fts"][10]["du"] == 0.5
    chon = cd.chon_k(bang, muc=0.9, k_toi_da=10)
    assert (chon["che_do"], chon["k"], chon["dat_muc"]) == ("hybrid", 3, True)
    chon = cd.chon_k(cd.bang_recall(mau[:1] * 3 + [{"dieu": ["999"], "xep_hang": {c: [] for c in cd.CHE_DO_UV}}], ks=(1, 5)),
                     muc=0.9, k_toi_da=5)
    assert (chon["k"], chon["dat_muc"]) == (5, False) and chon["du_tai_k_toi_da"] == 0.75


def test_dung_ung_vien_chen_dap_an_giu_dung_k():
    xh = ["300", "200", "150", "173", "120"]
    assert cd.dung_ung_vien(xh, 3) == (["150", "200", "300"], 0)
    uv, chen = cd.dung_ung_vien(xh, 3, ["173"])
    assert (uv, chen) == (["173", "200", "300"], 1)                 # thay ứng viên hạng thấp nhất (150), vẫn đúng 3
    uv, chen = cd.dung_ung_vien(xh, 3, ["300", "120", "999"])
    assert len(uv) == 3 and set(uv) == {"300", "120", "999"} and chen == 2
    assert cd.dung_ung_vien(["300"], 3, ["173"]) == (["173", "300"], 1)    # ít hơn K ứng viên: thêm vào
    with pytest.raises(cd.ChonError):
        cd.dung_ung_vien(xh, 1, ["1", "2"])


def _chi_muc_nho(tmp_path: Path):
    """Chỉ mục 4 Điều (có một Điều ngoài phần tội phạm) + vector băm."""
    dl = [("51", "Điều 51. Các tình tiết giảm nhẹ trách nhiệm hình sự", "người phạm tội tự thú thành khẩn khai báo"),
          ("173", "Điều 173. Tội trộm cắp tài sản", "người nào trộm cắp tài sản của người khác lén lút lấy xe máy"),
          ("174", "Điều 174. Tội lừa đảo chiếm đoạt tài sản", "dùng thủ đoạn gian dối chiếm đoạt tài sản đưa tiền đầu tư"),
          ("251", "Điều 251. Tội mua bán trái phép chất ma túy", "mua bán trái phép chất ma túy heroin methamphetamine")]
    chunks, pid = [], 0
    for so, td, nd in dl:
        for loai, key, text, noi in (("dieu", f"dieu {so}", td, ""), ("khoan", f"dieu {so}/khoan 1", f"{td}\nKhoản 1: {nd}", nd)):
            pid += 1
            chunks.append(Chunk(pid, 1, key, loai, "2018-01-01", None, noi, text, hash_text(text)))
    idx = open_index(tmp_path / "idx.sqlite")
    sync_chunks(idx, chunks)
    emb = HashEmbedder()
    luu_vector(idx, emb.name, [c.hash for c in chunks], emb.embed([c.text for c in chunks]))
    return idx, emb


def test_xep_hang_dieu_va_tieu_de_tren_chi_muc_nho(tmp_path):
    idx, emb = _chi_muc_nho(tmp_path)
    chu = "Bị cáo lén lút lấy trộm xe máy của người khác. " * 80 + "Sau đó bị cáo mua bán trái phép chất ma túy heroin. " * 80
    xh = cd.xep_hang_dieu(idx, emb, chu, "2023-01-01")
    assert set(xh) == set(cd.CHE_DO_UV)
    for ds in xh.values():
        assert "51" not in ds                                         # chỉ Điều tội phạm
    assert {"173", "251"} <= set(xh["hybrid"][:3])
    td = cd.tieu_de_dieu(idx, "2023-01-01")
    assert td == {"173": "Điều 173. Tội trộm cắp tài sản", "174": "Điều 174. Tội lừa đảo chiếm đoạt tài sản",
                  "251": "Điều 251. Tội mua bán trái phép chất ma túy"}
    assert cd.tieu_de_dieu(idx, "2017-01-01") == {}


# --------------------------------------------------------------------------------------------------------------------
# chon_dieu: tin nhắn, đọc, chấm
# --------------------------------------------------------------------------------------------------------------------


TD = {"173": "Điều 173. Tội trộm cắp tài sản", "174": "Điều 174. Tội lừa đảo chiếm đoạt tài sản", "251": "Điều 251. Tội mua bán trái phép chất ma túy"}


def test_tin_nhan_va_dap_an():
    tn = cd.dung_tin_nhan("  Bị cáo lấy xe.  ", ["173", "251"], TD)
    assert tn[0] == {"role": "system", "content": cd.HE_THONG_CHON}
    assert tn[1]["content"] == ("Sự việc:\nBị cáo lấy xe.\n\nĐiều ứng viên:\nĐiều 173. Tội trộm cắp tài sản\n"
                                "Điều 251. Tội mua bán trái phép chất ma túy")
    assert cd.dich_chon(["251", "173"]) == '{"dieu": ["173", "251"]}'
    with pytest.raises(cd.ChonError):
        cd.dung_tin_nhan("x", ["999"], TD)
    sc = cd.schema_chon(["173", "251"])
    assert sc["properties"]["dieu"]["items"]["enum"] == ["173", "251"]


def test_doc_chon_chiu_khoi_think_rao_va_loc_ngoai_ung_vien():
    uv = ["173", "174", "251"]
    assert cd.doc_chon('{"dieu": ["251", "173"]}', uv) == ["173", "251"]
    assert cd.doc_chon('<think>\n\n</think>\n\n```json\n{"dieu": ["Điều 174", "999"]}\n```', uv) == ["174"]
    assert cd.doc_chon('Đáp án: {"dieu": ["173"]} xong', uv) == ["173"]
    for hong in ('{"dieu": ["999"]}', '{"khac": 1}', "không phải JSON", ""):
        with pytest.raises(cd.ChonError):
            cd.doc_chon(hong, uv)


def test_cham_chon():
    r = cd.cham_chon(["173", "251"], ["173", "174"])
    assert (r["tim_du"], r["bao_phu"], r["chinh_xac"], r["khop_dung"], r["so_hien_thi"], r["thieu"]) == (0.0, 0.5, 0.5, 0.0, 2, ["251"])
    assert cd.cham_chon(["173"], ["173"])["khop_dung"] == 1.0
    assert cd.cham_chon(["173"], [])["tim_du"] == 0.0


def test_ket_hop_hop_va_loc():
    assert cd.ket_hop(["251", "173"], ["174", "173"], "hop") == (["173", "174", "251"], False)
    assert cd.ket_hop(["173", "251"], ["251", "134"], "loc_l") == (["251"], False)          # chỉ giữ Điều C0 chọn mà L cũng chọn
    assert cd.ket_hop(["173", "251"], ["251", "134"], "loc_c0") == (["251"], False)
    assert cd.ket_hop(["173", "251"], ["134"], "loc_l") == (["134"], True)                 # giao rỗng: lùi về L
    assert cd.ket_hop(["251", "173"], ["134"], "loc_c0") == (["173", "251"], True)         # giao rỗng: lùi về nguyên C0
    assert cd.ket_hop([], ["134"], "loc_c0") == (["134"], True)                            # một bên lỗi (rỗng): dùng bên còn lại
    assert cd.ket_hop(["173"], [], "loc_l") == (["173"], True)
    assert cd.ket_hop([], [], "loc_l") == ([], False) and cd.ket_hop([], [], "hop") == ([], False)
    with pytest.raises(cd.ChonError):
        cd.ket_hop(["173"], ["173"], "giao")


def test_chia_dev_theo_nhom_vu_co_dinh():
    bg = [{"ma": f"m{i}", "dieu": ["173"]} for i in range(30)]
    nhom = {f"m{i}": f"g{i // 2}" for i in range(30)}                  # 15 nhóm, mỗi nhóm 2 vụ
    a = cd.chia_dev(bg, nhom, so_dev=7, seed=2026)
    assert a == cd.chia_dev(bg, nhom, so_dev=7, seed=2026)
    assert sum(v == "dev" for v in a.values()) == 8                    # lấy trọn nhóm tới khi >= 7
    for g in set(nhom.values()):
        assert len({a[m] for m in nhom if nhom[m] == g}) == 1          # không tách nhóm vụ
    assert a != cd.chia_dev(bg, nhom, so_dev=7, seed=1)


# --------------------------------------------------------------------------------------------------------------------
# goi_kaggle
# --------------------------------------------------------------------------------------------------------------------


def _ban_an_gia() -> dict:
    mau = []
    for i in range(12):
        tap = "test" if i >= 8 else "train"
        dieu = ["173"] if i % 2 else ["174", "251"]
        if i == 11:
            dieu = ["123"]                                             # Điều chỉ có ở test
        mau.append({"ma": f"V{i:02d}", "tap": tap, "nhom_vu": f"N{i}", "ngay": "2022-03-04", "dieu": dieu,
                    "dau_vao": f"Vụ số {i}: " + " ".join(f"chữ{i}x{j}" for j in range(40)), "hash_dau_vao": f"h{i}",
                    "ten_toi_trong_loi_ke": i % 3})
    return {"nguon": {"dataset": "gia"}, "mau": mau}


def test_mau_ban_an_chia_va_danh_dau():
    ba = gk.mau_ban_an(_ban_an_gia(), so_dev=3, seed=2026)
    assert sum(x["tap"] == "dev" for x in ba) >= 3 and sum(x["tap"] == "test" for x in ba) == 4
    assert [x["dieu_chua_gap"] for x in ba if x["tap"] == "test"] == [False, False, False, True]
    assert all(x["ngay_tra_cuu"] == "2022-03-04" and not x["da_cat"] for x in ba)
    with pytest.raises(gk.GoiError):
        gk.mau_ban_an({"mau": [x for x in _ban_an_gia()["mau"] if x["tap"] == "train"]})


def test_mau_tong_hop_hop_dieu_va_bo_dieu_ngoai_pham_vi():
    th = {"mau": [{"id": "t1", "tinh_huong": "Lấy xe rồi lừa tiền.", "hanh_vi": [{"mo_ta": "a", "dieu": ["173"]}, {"mo_ta": "b", "dieu": ["174", "290"]}]},
                  {"id": "t2", "tinh_huong": "Tự thú.", "hanh_vi": [{"mo_ta": "c", "dieu": ["51"]}]},
                  {"id": "t3", "tinh_huong": "Mua bán ma túy.", "hanh_vi": [{"mo_ta": "d", "dieu": ["251"]}]}]}
    mau, cb = gk.mau_tong_hop(th, ["t1", "t2"], ["t3"])
    assert [(x["id"], x["tap"], x["dieu"]) for x in mau] == [("t1", "tong_hop_hoc", ["173", "174", "290"]), ("t3", "tong_hop_val", ["251"])]
    assert any("t2" in c for c in cb)
    with pytest.raises(gk.GoiError):
        gk.mau_tong_hop(th, ["t9"], [])


def test_dong_sft_dap_an_va_ung_vien():
    x = {"id": "V1", "nguon": "ban_an", "su_viec": "Bị cáo lấy xe.", "da_cat": False, "dieu": ["251"],
         "xep_hang": {"vector": ["173", "174", "300"]}}
    td = TD | {"300": "Điều 300. Tội tài trợ khủng bố"}
    d = gk.dong_sft(x, "vector", 2, td)
    assert d["chen"] == 1 and d["so_ung_vien"] == 2
    assert [m["role"] for m in d["messages"]] == ["system", "user", "assistant"]
    assert d["messages"][2]["content"] == '{"dieu": ["251"]}'
    assert d["messages"][1]["content"].endswith("Điều 173. Tội trộm cắp tài sản\nĐiều 251. Tội mua bán trái phép chất ma túy")


def test_kiem_giao_bat_id_nhom_va_chu_trung():
    chu = " ".join(f"từ{j}" for j in range(60))
    test = [{"id": "T1", "nhom_vu": "G1", "dau_vao_goc": chu, "hash_dau_vao": "x", "su_viec": chu}]
    sach = [{"id": "H1", "nhom_vu": "G2", "su_viec": "khác hẳn " * 20}]
    assert gk.kiem_giao(test, sach) == []
    assert any("id" in l for l in gk.kiem_giao(test, sach + [{"id": "T1", "nhom_vu": "G9", "su_viec": "zzz"}]))
    assert any("nhóm vụ" in l for l in gk.kiem_giao(test, sach + [{"id": "H2", "nhom_vu": "G1", "su_viec": "zzz"}]))
    assert any("độ chứa" in l for l in gk.kiem_giao(test, sach + [{"id": "H3", "su_viec": " ".join(chu.split()[10:40])}]))


def test_sha256sums_va_zip_xac_dinh(tmp_path):
    d = tmp_path / "goi"
    (d / "con").mkdir(parents=True)
    (d / "a.txt").write_text("một", encoding="utf-8")
    (d / "con" / "b.json").write_text("{}", encoding="utf-8")
    gk.ghi_sha256sums(d)
    assert gk.kiem_sha256sums(d) == []
    assert (d / "SHA256SUMS").read_text(encoding="utf-8").splitlines()[1].endswith("  con/b.json")
    s1 = gk.nen_zip(d, tmp_path / "1.zip")
    s2 = gk.nen_zip(d, tmp_path / "2.zip")
    assert s1 == s2
    assert sorted(zipfile.ZipFile(tmp_path / "1.zip").namelist()) == ["goi/SHA256SUMS", "goi/a.txt", "goi/con/b.json"]
    (d / "a.txt").write_text("hai", encoding="utf-8")
    assert gk.kiem_sha256sums(d) == ["sai mã băm a.txt"]


def test_chep_ma_nguon_bo_pycache(tmp_path):
    goc = tmp_path / "goc"
    for r in ("src/a.py", "src/con/b.sql", "src/__pycache__/a.cpython-310.pyc", "src/con/c.txt", "scripts/x.py", "config.yaml"):
        (goc / r).parent.mkdir(parents=True, exist_ok=True)
        (goc / r).write_text("x", encoding="utf-8")
    da = gk.chep_ma_nguon(goc, tmp_path / "dich", ["x.py"])
    assert da == ["src/a.py", "src/con/b.sql", "scripts/x.py", "config.yaml"]
    assert (tmp_path / "dich" / "scripts" / "x.py").exists()


# --------------------------------------------------------------------------------------------------------------------
# scripts/do_ban_an.py (chế độ giả)
# --------------------------------------------------------------------------------------------------------------------


def _goi_do_gia(tmp_path: Path) -> Path:
    goi = tmp_path / "goi"
    goi.mkdir()
    mau = []
    for i, (tap, dieu) in enumerate((("dev", ["173"]), ("dev", ["174", "251"]), ("test", ["251"]), ("test", ["173"]))):
        mau.append({"id": f"V{i}", "tap": tap, "su_viec": f"Vụ {i}. Bị cáo làm việc xấu.", "da_cat": False, "so_tu_goc": 6, "dieu": dieu,
                    "nhom_vu": f"N{i}", "ngay": "2022-01-01", "ngay_tra_cuu": "2022-01-01", "ten_toi_trong_loi_ke": 0,
                    "dieu_chua_gap": False, "xep_hang": {c: ["173", "251", "174"] for c in cd.CHE_DO_UV}, "tieu_de": TD})
    gk.ghi_json(goi / "ban_an_do.json", {"phien_ban": 1, "mau": mau})
    gk.ghi_json(goi / "cau_hinh.json", {"ung_vien": {"che_do": "vector", "k": 2}, "gia": True})
    return goi


def _chay(goi: Path, *tham_so: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(ROOT / "scripts" / "do_ban_an.py"), "--goi", str(goi), "--gia", *tham_so],
                          capture_output=True, text=True, encoding="utf-8", cwd=ROOT)


def test_do_ban_an_gia_chay_tiep_khong_ghi_de(tmp_path):
    goi = _goi_do_gia(tmp_path)
    r = _chay(goi, "--tap", "dev", "--cau-hinh", "A,C0,L", "--mo-hinh-chon", "lora")
    assert r.returncode == 0, r.stderr
    dong = (goi / "ket_qua" / "dev" / "C0.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(dong) == 2 and json.loads(dong[0])["ung_vien"] == ["173", "251"]
    bao_cao = (goi / "ket_qua" / "dev" / "bao_cao.md").read_text(encoding="utf-8")
    assert "| A3 |" in bao_cao and "| L so với C0 |" in bao_cao
    r = _chay(goi, "--tap", "dev", "--cau-hinh", "C0")
    assert r.returncode == 0 and len((goi / "ket_qua" / "dev" / "C0.jsonl").read_text(encoding="utf-8").splitlines()) == 2


def test_do_ban_an_tap_test_can_file_chot(tmp_path):
    goi = _goi_do_gia(tmp_path)
    assert _chay(goi, "--tap", "test").returncode != 0
    chot = tmp_path / "cau_hinh_chot.json"
    chot.write_text(json.dumps({"cau_hinh": ["A", "C0"], "mo_hinh_goc": "qwen3:8b", "k": 2, "che_do_uv": "vector", "num_ctx": 8192}),
                    encoding="utf-8")
    assert _chay(goi, "--tap", "test", "--da-chot", "--chot", str(chot), "--k", "3").returncode != 0     # không nhận tham số ngoài file chốt
    r = _chay(goi, "--tap", "test", "--da-chot", "--chot", str(chot))
    assert r.returncode == 0, r.stderr
    assert all(json.loads(x)["sha_chot"] for x in (goi / "ket_qua" / "test" / "C0.jsonl").read_text(encoding="utf-8").splitlines())
    chot.write_text(json.dumps({"cau_hinh": ["C0"], "mo_hinh_goc": "qwen3:4b", "k": 2, "che_do_uv": "vector", "num_ctx": 8192}), encoding="utf-8")
    r = _chay(goi, "--tap", "test", "--da-chot", "--chot", str(chot))
    assert r.returncode != 0 and "cấu hình chốt khác" in r.stderr


def test_binom_hai_phia():
    sys.path.insert(0, str(ROOT / "scripts"))
    import do_ban_an
    assert do_ban_an.binom_hai_phia(8, 8) == pytest.approx(0.0078125)
    assert do_ban_an.binom_hai_phia(0, 0) == 1.0
    assert do_ban_an.binom_hai_phia(15, 20) < 0.05 < do_ban_an.binom_hai_phia(14, 20)


def test_hoi_lap_qua_gio_ghi_loi_va_di_tiep():
    sys.path.insert(0, str(ROOT / "scripts"))
    import do_ban_an

    class Cham:
        so_lan = 0

        def chat(self, *a, **k):
            Cham.so_lan += 1
            raise do_ban_an.QuaGio("quá 900s chờ m")

    r = do_ban_an.hoi_lap(Cham(), "m", [], {}, 10, lambda t: t)
    assert r["ket_qua"] is None and r["loi"] == "quá 900s chờ m" and Cham.so_lan == 1


def test_do_ban_an_ket_hop_tu_ket_qua_da_co_khong_goi_mo_hinh(tmp_path):
    goi = _goi_do_gia(tmp_path)
    ra = goi / "ket_qua" / "dev"
    ra.mkdir(parents=True)
    chon = {"C0": {"V0": ["173", "251"], "V1": ["174", "251"]}, "L": {"V0": ["173"], "V1": ["173"]}}
    vang = {"V0": ["173"], "V1": ["174", "251"]}
    for c, theo in chon.items():
        (ra / f"{c}.jsonl").write_text("".join(json.dumps(
            {"id": i, "cau_hinh": c, "mo_hinh": c.lower(), "dieu": vang[i], "hien_thi": h, "cham": cd.cham_chon(vang[i], h),
             "loi": None, "giay": 1.0, "co_the_bi_cat": False}) + "\n" for i, h in theo.items()), encoding="utf-8")
    # không --gia, không --mo-hinh-chon, endpoint không tồn tại: chỉ chạy được nếu không gọi Ollama
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "do_ban_an.py"), "--goi", str(goi), "--tap", "dev",
                        "--cau-hinh", "HOP,LOC,LOC0", "--endpoint", "http://127.0.0.1:9"],
                       capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    assert r.returncode == 0, r.stderr
    doc = lambda c: {x["id"]: x for x in map(json.loads, (ra / f"{c}.jsonl").read_text(encoding="utf-8").splitlines())}
    assert len(doc("C0")) == 2 and len(doc("L")) == 2                                      # không ghi thêm vào kết quả cũ
    hop, loc, loc0 = doc("HOP"), doc("LOC"), doc("LOC0")
    assert hop["V0"]["hien_thi"] == ["173", "251"] and hop["V1"]["hien_thi"] == ["173", "174", "251"]
    assert loc["V0"]["hien_thi"] == ["173"] and not loc["V0"]["lui"]
    assert loc["V1"]["hien_thi"] == ["173"] and loc["V1"]["lui"] and loc["V1"]["cham"]["tim_du"] == 0
    assert loc0["V1"]["hien_thi"] == ["174", "251"] and loc0["V1"]["cham"]["khop_dung"] == 1
    assert loc["V0"]["tu"] == {"C0": ["173", "251"], "L": ["173"]} and loc["V0"]["giay"] == 2.0
    bao_cao = (ra / "bao_cao.md").read_text(encoding="utf-8")
    assert "| HOP | 2/2 (100%) |" in bao_cao and "| LOC | 1/2 (50%) |" in bao_cao and "| LOC0 | 2/2 (100%) |" in bao_cao
    assert "LOC 1/2, LOC0 1/2" in bao_cao and "| HOP so với C0 |" in bao_cao


def test_do_ban_an_ket_hop_thieu_l_can_mo_hinh(tmp_path):
    goi = _goi_do_gia(tmp_path)
    r = _chay(goi, "--tap", "dev", "--cau-hinh", "HOP")
    assert r.returncode != 0 and "--mo-hinh-chon" in r.stderr
    r = _chay(goi, "--tap", "dev", "--cau-hinh", "HOP", "--mo-hinh-chon", "lora")         # thiếu thì C0, L được chạy như thường
    assert r.returncode == 0, r.stderr
    assert all(len((goi / "ket_qua" / "dev" / f"{c}.jsonl").read_text(encoding="utf-8").splitlines()) == 2 for c in ("C0", "L", "HOP"))
