"""Kiểm thử src/ban_an/cbba_kaggle.py, scripts/dong_goi_cbba_kaggle.py và scripts/tao_notebook_cbba.py (mẫu con cbba cho Kaggle, kế hoạch V3).

Chỉ dùng văn bản GIẢ LẬP (từ «tuNNN» sinh theo hạt cố định) và chỉ mục nhỏ của tests/test_chon_dieu.py; không cần dữ liệu thật, Ollama hay mạng.
"""
from __future__ import annotations

import ast
import hashlib
import json
import random
import re
import shutil
import subprocess
import sys
import zlib
from collections import Counter
from pathlib import Path

import pytest

from src.ban_an import anle_hf as hf
from src.ban_an import cbba_kaggle as cb
from src.ban_an import chon_dieu as cd
from src.ban_an import goi_kaggle as gk
from tests.test_chon_dieu import TD, _chi_muc_nho

ROOT = Path(__file__).resolve().parents[1]
SCRIPT_GOI = ROOT / "scripts" / "dong_goi_cbba_kaggle.py"
SCRIPT_NB = ROOT / "scripts" / "tao_notebook_cbba.py"


def _van(i: int, n_tu: int = 160) -> str:
    rng = random.Random(i)
    return " ".join(f"tu{rng.randrange(2000)}" for _ in range(n_tu))


def _meta(ma: str, tap: str = "train", nhom: str | None = None, dieu: tuple = ("173",), ngay: str | None = "2022-05-10", cap: str = "so_tham",
          n: int = 1000, h: str | None = None) -> dict:
    return {"ma": ma, "tap": tap, "nhom_vu": nhom or ma, "dieu": list(dieu), "ngay": ngay, "cap": cap, "n_ky_tu": n, "hash": h or "h_" + ma}


# --------------------------------------------------------------------------------------------------------------------
# Chọn mẫu
# --------------------------------------------------------------------------------------------------------------------


def test_ngay_hop_le():
    assert cb.ngay_hop_le("2018-01-01") and cb.ngay_hop_le("2026-12-31")
    for x in (None, "", "2017-12-31", "2027-01-01", "2202-01-01", "2022-13-01", "2022-02-30", "22-1-1"):
        assert not cb.ngay_hop_le(x), x


def test_loc_pool_moi_van_ban_mot_ly_do_va_loai_trung_chu_train_test():
    metas = [_meta("a1", ngay=None), _meta("a2", ngay="2017-05-01"), _meta("a3", cap="phuc_tham"), _meta("a4", dieu=("300",)), _meta("a5", n=9000),
             _meta("a6"), _meta("a7", h="X"),
             _meta("t1", tap="test", n=99999), _meta("t2", tap="test", dieu=("300",)), _meta("t3", tap="test", h="X")]
    pool, loai = cb.loc_pool(metas, toi_da_ky_tu=7700, cap_giu={"so_tham"}, tra_cuu_duoc=lambda d, n: "300" not in d)
    assert [m["ma"] for m in pool["train"]] == ["a6"]
    assert [m["ma"] for m in pool["test"]] == ["t1"]                    # test không bị loại vì dài
    assert dict(loai["train"]) == {"thieu_hoac_sai_ngay": 2, "cap_khong_giu": 1, "dieu_khong_co_trong_chi_muc": 1, "qua_dai": 1,
                                   "trung_chu_train_test": 1}
    assert dict(loai["test"]) == {"dieu_khong_co_trong_chi_muc": 1, "trung_chu_train_test": 1}
    with pytest.raises(cb.CbbaKaggleError):
        cb.loc_pool([_meta("x", tap="val")])


def test_chon_train_tran_dieu_hiem_truoc_va_xac_dinh():
    pool = [_meta(f"a{i:03d}", dieu=("173",)) for i in range(100)]
    pool += [_meta(f"b{i}", dieu=("173", "174")) for i in range(3)] + [_meta(f"c{i}", dieu=("174",)) for i in range(2)]
    sel = cb.chon_train(pool, 10, seed=1)
    ma = {m["ma"] for m in sel}
    assert {"b0", "b1", "b2", "c0", "c1"} <= ma                          # Điều 174 hiếm: lấy hết
    assert sum("173" in m["dieu"] for m in sel) == 10                    # 3 văn bản nhiều Điều đã được tính cho 173 → chỉ lấy thêm 7
    assert len(sel) == 12 and [m["ma"] for m in sel] == sorted(ma)
    assert [m["ma"] for m in cb.chon_train(pool, 10, seed=1)] == [m["ma"] for m in sel]
    assert {m["ma"] for m in cb.chon_train(pool, 10, seed=2)} != ma
    assert len(cb.chon_train(pool[:5], 50)) == 5                         # ít hơn trần: lấy hết
    with pytest.raises(cb.CbbaKaggleError):
        cb.chon_train(pool, 0)


def test_chon_so_bo_dev_nguyen_nhom_va_hoc_khong_giao_dev():
    pool = {"train": [_meta(f"v{i:02d}", nhom=f"G{i // 2}", dieu=("173" if i % 3 else "174",)) for i in range(40)],
            "test": [_meta(f"w{i}", tap="test", nhom=f"T{i // 3}") for i in range(12)]}
    kq = cb.chon_so_bo(pool, tran=50, so_dev=6, seed=5)
    nhom_dev = {m["nhom_vu"] for m in kq["dev"]}
    assert len(kq["dev"]) == 6 and len(nhom_dev) == 3
    assert all(sum(m["nhom_vu"] == g for m in kq["dev"]) == 2 for g in nhom_dev)         # nhóm vào trọn dev
    assert not nhom_dev & {m["nhom_vu"] for m in kq["hoc"]}
    assert len(kq["hoc"]) == 34                                                          # trần 50 > số văn bản: lấy hết phần còn lại
    # test: mỗi nhóm vụ đúng một văn bản
    assert sorted(m["nhom_vu"] for m in kq["ung_test"]) == sorted({f"T{i // 3}" for i in range(12)})
    assert [m["ma"] for m in cb.thu_tu_test(pool["test"], 5)] == [m["ma"] for m in kq["ung_test"]]
    assert [m["ma"] for m in cb.thu_tu_test(pool["test"], 6)] != [m["ma"] for m in kq["ung_test"]]


# --------------------------------------------------------------------------------------------------------------------
# Gần-trùng
# --------------------------------------------------------------------------------------------------------------------


def test_chi_muc_gan_trung_khop_anle_hf_trung_voi():
    cu = {f"D{i}": _van(i) for i in range(25)}
    tu = cu["D0"].split()
    gan = " ".join(("doi" + str(i)) if i % 12 == 5 else w for i, w in enumerate(tu))          # thay 1/12 số từ: độ chứa ≈ 0,58
    nhe = " ".join(("doi" + str(i)) if i % 7 == 3 else w for i, w in enumerate(tu))           # thay 1/7: ≈ 0,29, dưới ngưỡng
    trich = " ".join(cu["D3"].split()[:60])                                                   # đoạn ngắn chép từ bản dài: 1,0
    truy_van = {"gan": gan, "nhe": nhe, "trich": trich, "moi": _van(999), "y_het": cu["D7"]}
    chi_muc = cb.ChiMucGanTrung()
    for m, v in cu.items():
        chi_muc.them(m, v)
    mong = {(c["ma"], c["ma_cu"]): c["do_chua"] for c in hf.trung_voi(
        [{"ma": k, "dau_vao": v, "hash_dau_vao": hf.hash_van(v)} for k, v in truy_van.items()], cu, 0.5)}
    co = {(k, ma): dc for k, v in truy_van.items() for ma, dc in chi_muc.tim(v, 0.5)}
    assert co == mong
    assert set(mong) == {("gan", "D0"), ("trich", "D3"), ("y_het", "D7")} and mong[("y_het", "D7")] == 1.0
    assert chi_muc.tim(truy_van["moi"]) == []


def test_loc_gan_trung_test_bo_ban_sao_va_bao_loi_khi_thieu():
    hoc = {f"D{i}": _van(i) for i in range(5)}
    chi_muc = cb.ChiMucGanTrung()
    for m, v in hoc.items():
        chi_muc.them(m, v)
    ung = [_meta(f"T{i}", tap="test") for i in range(4)]
    van = {"T0": _van(100), "T1": " ".join(hoc["D2"].split()[:110]) + " " + _van(101, 50), "T2": _van(102), "T3": _van(103)}
    test, bo = cb.loc_gan_trung_test(ung, van, chi_muc, 3)
    assert [m["ma"] for m in test] == ["T0", "T2", "T3"] and [b["ma"] for b in bo] == ["T1"] and bo[0]["ma_hoc"] == "D2" and bo[0]["do_chua"] >= 0.5
    test, bo = cb.loc_gan_trung_test(ung, van, chi_muc, 2)             # đủ rồi thì không xét tiếp: T1 vẫn bị bỏ vì nằm trước T2
    assert [m["ma"] for m in test] == ["T0", "T2"]
    with pytest.raises(cb.CbbaKaggleError):
        cb.loc_gan_trung_test(ung, van, chi_muc, 4)
    giu, bo = cb.loc_dev_gan_trung([_meta("dv1"), _meta("dv2")], {"dv1": hoc["D1"], "dv2": _van(55)}, chi_muc)
    assert [m["ma"] for m in giu] == ["dv2"] and bo[0]["ma_hoc"] == "D1"


def test_mau_cbba_dong_sft_va_kiem_giao_cbba():
    van_hoc = {"h1": _van(1), "h2": _van(2)}
    hoc = [cb.mau_cbba(_meta("h1", dieu=("173",), nhom="N1", h=hf.hash_van(van_hoc["h1"])), van_hoc["h1"], "hoc"),
           cb.mau_cbba(_meta("h2", dieu=("174", "251"), nhom="N2", h=hf.hash_van(van_hoc["h2"])), van_hoc["h2"], "hoc")]
    x = hoc[1]
    assert x["id"] == "cbba_h2" and x["nguon"] == "ban_an" and x["tap"] == "hoc" and x["dieu"] == ["174", "251"] and x["nam"] == 2022
    x["xep_hang"] = {c: ["173", "300"] for c in cd.CHE_DO_UV}
    r = gk.dong_sft(x, "hybrid", 2, {**TD, "300": "Điều 300. Tội gì đó"})
    assert [m["role"] for m in r["messages"]] == ["system", "user", "assistant"] and r["chen"] == 2
    assert json.loads(r["messages"][2]["content"]) == {"dieu": ["174", "251"]}
    # test: gặp Điều chưa có ở học → cờ; kiểm giao bắt id, nhóm vụ, băm và chữ gần-trùng
    test_ok = cb.mau_cbba(_meta("t1", tap="test", dieu=("999",), nhom="N9", h="ht1"), _van(300), "test", {"173", "174", "251"})
    assert test_ok["dieu_chua_gap"] is True and test_ok["tap"] == "test"
    chi_muc = cb.ChiMucGanTrung()
    for m, v in van_hoc.items():
        chi_muc.them(m, v)
    assert cb.kiem_giao_cbba([test_ok], hoc, chi_muc, {test_ok["id"]: test_ok["dau_vao_goc"]}) == []
    xau = dict(test_ok, id="cbba_h1", nhom_vu="N2", hash_dau_vao=hoc[0]["hash_dau_vao"], dau_vao_goc=van_hoc["h1"])
    loi = cb.kiem_giao_cbba([xau], hoc, chi_muc, {xau["id"]: xau["dau_vao_goc"]})
    assert len(loi) == 4 and any("id vụ test" in x for x in loi) and any("nhóm vụ N2" in x for x in loi) and any("băm" in x for x in loi) \
        and any("5-gram" in x for x in loi)
    with pytest.raises(cb.CbbaKaggleError):
        cb.mau_cbba(_meta("z"), "x", "train")


def test_cache_xep_hang_ghi_noi_chiu_dong_ghi_do(tmp_path):
    p = tmp_path / "t" / "xh.jsonl"
    c = cb.CacheXepHang(p)
    c["k1"] = {"vector": ["173"]}
    c.dong()
    with p.open("a", encoding="utf-8") as f:
        f.write('{"k": "k2", "v": {"vect')                               # ngắt giữa chừng, không xuống dòng
    c = cb.CacheXepHang(p)
    assert dict(c) == {"k1": {"vector": ["173"]}}
    c["k2"] = {"fts": ["174"]}
    c.dong()
    assert dict(cb.CacheXepHang(p)) == {"k1": {"vector": ["173"]}, "k2": {"fts": ["174"]}}


def test_doc_van_ban_bo_qua_dong_khong_can_va_bao_thieu(tmp_path):
    p = tmp_path / "x.jsonl"
    p.write_text("".join(json.dumps({"ma": m, "dau_vao": f"văn bản {m}", "dieu": ["173"]}, ensure_ascii=False) + "\n" for m in "1234"), encoding="utf-8")
    assert cb.doc_van_ban(p, {"2", "4"}) == {"2": "văn bản 2", "4": "văn bản 4"}
    assert cb.doc_van_ban(p, set()) == {}
    with pytest.raises(cb.CbbaKaggleError):
        cb.doc_van_ban(p, {"2", "9"})
    assert cb.phan_bo(Counter({"173": 50, "174": 5})) == {"so_dieu": 2, "nho_nhat": 5, "trung_vi": 50, "lon_nhat": 50, "top5": [("173", 50), ("174", 5)],
                                                          "duoi_10": 1}


# --------------------------------------------------------------------------------------------------------------------
# Script đóng gói: từ đầu đến cuối với vector giả
# --------------------------------------------------------------------------------------------------------------------


def _dong(ma: str, tap: str, dieu, *, ngay: str | None = "2022-05-10", nhom: str | None = None, van: str | None = None, cap: str = "so_tham") -> dict:
    return {"ma": ma, "tap": tap, "nhom_vu": nhom or ma, "dau_vao": _van(zlib.crc32(ma.encode())) if van is None else van, "dieu": list(dieu),
            "toi_danh": ["x"], "nguon_nhan": "quyet_dinh", "cap": cap, "so_ban_an": "1/2022/HS-ST", "ngay": ngay}


def _du_lieu_gia(vao: Path) -> None:
    train = [_dong(f"tr{i:03d}", "train", ["173"] if i < 30 else ["174"] if i < 50 else ["251"]) for i in range(58)]
    train += [_dong("tr058", "train", ["173", "174"]), _dong("tr059", "train", ["173"], ngay=None), _dong("trold", "train", ["173"], ngay="2016-01-01"),
              _dong("trlong", "train", ["174"], van=_van(7, 700)), _dong("trdieu", "train", ["300"]), _dong("trdup", "train", ["251"], van=_van(8))]
    train[2]["nhom_vu"] = train[1]["nhom_vu"] = "G1"
    gan = " ".join(_van(zlib.crc32(b"tr010")).split()[:120]) + " " + _van(555, 40)
    test = [_dong(f"te{i:03d}", "test", [["173", "174", "251"][i % 3]], cap="phuc_tham" if i % 5 == 0 else "so_tham") for i in range(30)]
    test += [_dong("tenear", "test", ["173"], van=gan), _dong("tedup", "test", ["251"], van=_van(8)), _dong("tecode", "test", ["300"])]
    for t, ds in (("train", train), ("test", test)):
        (vao / f"{t}.jsonl").write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in ds), encoding="utf-8", newline="\n")


def _chay(*tham_so: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT_GOI), *tham_so], capture_output=True, text=True, encoding="utf-8", cwd=ROOT)


@pytest.fixture()
def moi_truong(tmp_path):
    vao = tmp_path / "nhan"
    vao.mkdir()
    _du_lieu_gia(vao)
    idx, _ = _chi_muc_nho(tmp_path)
    idx.close()
    return vao, tmp_path / "ra", tmp_path / "idx.sqlite"


THAM_SO = ("--tran", "5", "--so-dev", "8", "--so-dev-do", "4", "--so-test", "30", "--toi-da-ky-tu", "3000", "--gia", "--khong-kiem-anle")
THAM_SO_CHON = ("--tran", "100", "--so-dev", "8", "--so-dev-do", "4", "--so-test", "30", "--toi-da-ky-tu", "3000", "--gia",
                "--khong-kiem-anle")                                                                 # trần cao: mọi văn bản hợp lệ vào học / dev
THAM_SO_ANLE = tuple(x for x in THAM_SO_CHON if x != "--khong-kiem-anle")


def test_dong_goi_chi_chon_loc_dung_ly_do_va_bo_ban_sao(moi_truong):
    vao, ra, idx = moi_truong
    r = _chay("--vao", str(vao), "--ra", str(ra), "--index", str(idx), "--chi-chon", *THAM_SO_CHON)
    assert r.returncode == 0, r.stdout + r.stderr
    cm = json.loads((ra / "chon_mau.json").read_text(encoding="utf-8"))
    assert cm["loai"]["train"] == {"thieu_hoac_sai_ngay": 2, "dieu_khong_co_trong_chi_muc": 1, "qua_dai": 1, "trung_chu_train_test": 1}
    assert cm["loai"]["test"] == {"dieu_khong_co_trong_chi_muc": 1, "trung_chu_train_test": 1}
    ma = cm["id"]
    assert not {"tr059", "trold", "trdieu", "trlong", "trdup"} & set(ma["hoc"] + ma["dev"])
    assert len(ma["test"]) == 30 and not {"tenear", "tedup", "tecode"} & set(ma["test"])           # đủ 30 buộc phải gặp và bỏ «tenear»
    assert [b["ma"] for b in cm["bo_gan_trung"]["test"]] == ["tenear"] and cm["bo_gan_trung"]["test"][0]["ma_hoc"] == "tr010"
    assert not set(ma["hoc"]) & set(ma["dev"]) and ma["dev_do"] == ma["dev"][:4]
    nhom = {d["ma"]: d["nhom_vu"] for d in map(json.loads, (vao / "train.jsonl").read_text(encoding="utf-8").splitlines())}
    assert not {nhom[m] for m in ma["hoc"]} & {nhom[m] for m in ma["dev"]}                          # nhóm vụ không bị tách
    assert cm["g0"]["loi"] == [] and "G0: 0 vụ test" in r.stdout
    assert not (ra / "lexo_hoc_chon_dieu_cbba_GIA.zip").exists()                                     # --chi-chon không đóng gói
    r2 = _chay("--vao", str(vao), "--ra", str(ra), "--index", str(idx), "--chi-chon", *THAM_SO_CHON)  # dùng cache siêu dữ liệu, cùng kết quả
    assert r2.returncode == 0 and "dùng cache" in r2.stdout
    assert json.loads((ra / "chon_mau.json").read_text(encoding="utf-8"))["id"] == ma


def test_dong_goi_day_du_hai_goi_dung_dinh_dang_v2_va_xac_dinh(moi_truong):
    vao, ra, idx = moi_truong
    r = _chay("--vao", str(vao), "--ra", str(ra), "--index", str(idx), "--bo-qua-cong", *THAM_SO)
    assert r.returncode == 0, r.stdout + r.stderr
    goi_hoc, goi_do = ra / "lexo_hoc_chon_dieu_cbba", ra / "lexo_do_ban_an_cbba"
    for g in (goi_hoc, goi_do):
        assert gk.kiem_sha256sums(g) == []
    assert (goi_hoc / gk.DAU_GOI_HOC).exists() and (goi_do / gk.DAU_GOI_DO).exists()
    assert (ra / "lexo_hoc_chon_dieu_cbba_GIA.zip").exists() and (ra / "lexo_do_ban_an_cbba_GIA.zip").exists()
    tt = json.loads((goi_hoc / "thong_tin_du_lieu.json").read_text(encoding="utf-8"))
    kg = json.loads((goi_hoc / "kiem_giao.json").read_text(encoding="utf-8"))
    cm = json.loads((ra / "chon_mau.json").read_text(encoding="utf-8"))
    assert tt["gia"] is True and len(kg["ma_test"]) == 30 and tt["so_dong"] == {"train": len(cm["id"]["hoc"]), "val": len(cm["id"]["dev"])}
    # các kiểm tra G0 của notebook học (cùng logic), trên gói vừa dựng
    train = [json.loads(x) for x in (goi_hoc / "sft_chon_train.jsonl").read_text(encoding="utf-8").splitlines()]
    val = [json.loads(x) for x in (goi_hoc / "sft_chon_val.jsonl").read_text(encoding="utf-8").splitlines()]
    ma_test, bam_test = set(kg["ma_test"]), set(kg["sha256_su_viec_test"])
    for d in train + val:
        m = d["messages"]
        assert [x["role"] for x in m] == ["system", "user", "assistant"] and m[0]["content"] == tt["he_thong_chon"]
        u = m[1]["content"]
        assert u.startswith("Sự việc:\n") and "\n\nĐiều ứng viên:\n" in u
        su, uv = u[len("Sự việc:\n"):u.rindex("\n\nĐiều ứng viên:\n")], u[u.rindex("\n\nĐiều ứng viên:\n") + len("\n\nĐiều ứng viên:\n"):]
        ung_vien = [re.match(r"Điều (\d+[a-z]?)\.", x).group(1) for x in uv.split("\n")]
        assert 1 <= len(ung_vien) <= tt["ung_vien"]["k"]
        assert set(json.loads(m[2]["content"])["dieu"]) <= set(ung_vien)
        assert d["id"] not in ma_test and hashlib.sha256(su.encode("utf-8")).hexdigest() not in bam_test
    assert not {d["id"] for d in train} & {d["id"] for d in val}
    # gói đo: cùng định dạng với V2, chạy được với scripts/do_ban_an.py
    do = json.loads((goi_do / "ban_an_do.json").read_text(encoding="utf-8"))
    assert Counter(x["tap"] for x in do["mau"]) == {"dev": 4, "test": 30}
    assert all(x["xep_hang"].keys() == set(cd.CHE_DO_UV) and x["tieu_de"] for x in do["mau"])
    assert not any("dau_vao_goc" in x for x in do["mau"])
    rd = subprocess.run([sys.executable, str(ROOT / "scripts" / "do_ban_an.py"), "--goi", str(goi_do), "--gia", "--tap", "dev", "--cau-hinh", "A,C0,L",
                         "--mo-hinh-chon", "lora"], capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    assert rd.returncode == 0, rd.stdout + rd.stderr
    assert len((goi_do / "ket_qua" / "dev" / "C0.jsonl").read_text(encoding="utf-8").splitlines()) == 4
    assert subprocess.run([sys.executable, str(ROOT / "scripts" / "do_ban_an.py"), "--goi", str(goi_do), "--gia", "--tap", "test"],
                          capture_output=True, text=True, cwd=ROOT).returncode != 0           # test cần file chốt
    # chạy lại: cùng zip (xác định); cache ứng viên được dùng
    sha = {z: gk.sha256_file(ra / z) for z in ("lexo_hoc_chon_dieu_cbba_GIA.zip", "lexo_do_ban_an_cbba_GIA.zip")}
    r2 = _chay("--vao", str(vao), "--ra", str(ra), "--index", str(idx), "--bo-qua-cong", *THAM_SO)
    assert r2.returncode == 0 and "đã nhớ sẵn" in r2.stdout
    assert {z: gk.sha256_file(ra / z) for z in sha} == sha


def test_dong_goi_loi_dau_vao(moi_truong):
    vao, ra, idx = moi_truong
    assert _chay("--vao", str(vao / "khong_co"), "--ra", str(ra), "--index", str(idx), "--chi-chon").returncode != 0
    assert _chay("--vao", str(vao), "--ra", str(ra), "--index", str(idx), "--chi-chon", "--so-dev", "8", "--so-dev-do", "9").returncode != 0
    r = _chay("--vao", str(vao), "--ra", str(ra), "--index", str(idx), "--chi-chon", "--tran", "5", "--so-dev", "8", "--so-dev-do", "4", "--so-test", "400",
              "--khong-kiem-anle")
    assert r.returncode != 0 and "cần 400" in r.stderr


def _anle(p: Path, *vu: tuple[str, str, str]) -> Path:
    """File bản án án lệ giả: mỗi vụ là (mã, tập, đầu vào)."""
    p.write_text(json.dumps({"mau": [{"ma": m, "tap": t, "dau_vao": v} for m, t, v in vu]}, ensure_ascii=False), encoding="utf-8")
    return p


def test_loc_giao_anle_bat_ban_sao_o_hoc_dev():
    hoc = {f"D{i}": _van(i) for i in range(5)}
    chi_muc = cb.ChiMucGanTrung()
    for m, v in hoc.items():
        chi_muc.them(m, v)
    vu = {"AL1": " ".join(hoc["D3"].split()[:100]) + " " + _van(901, 60), "AL2": _van(902), "AL3": hoc["D1"]}
    kq = cb.loc_giao_anle(chi_muc, vu)
    assert set(kq) == {"D3", "D1"} and kq["D3"]["ma_anle"] == "AL1" and kq["D1"] == {"ma_anle": "AL3", "do_chua": 1.0}
    assert cb.loc_giao_anle(chi_muc, {"AL2": vu["AL2"]}) == {} and cb.loc_giao_anle(chi_muc, {}) == {}


def test_dong_goi_bo_van_ban_hoc_trung_test_anle(moi_truong):
    vao, ra, idx = moi_truong
    nam = vao.parent
    r0 = _chay("--vao", str(vao), "--ra", str(ra), "--index", str(idx), "--chi-chon", *THAM_SO_CHON)
    ma0 = json.loads((ra / "chon_mau.json").read_text(encoding="utf-8"))["id"]
    assert "tr010" in ma0["hoc"] + ma0["dev"] and r0.returncode == 0
    van010 = _van(zlib.crc32(b"tr010"))
    ap = _anle(nam / "anle.json", ("AL1", "test", " ".join(van010.split()[:110]) + " " + _van(777, 60)), ("AL2", "test", _van(778)),
               ("AL3", "train", _van(zlib.crc32(b"tr020"))))                    # vụ tập train của án lệ KHÔNG được dùng để lọc
    r = _chay("--vao", str(vao), "--ra", str(ra), "--index", str(idx), "--chi-chon", "--ban-an-anle", str(ap), *THAM_SO_ANLE)
    assert r.returncode == 0, r.stdout + r.stderr
    cm = json.loads((ra / "chon_mau.json").read_text(encoding="utf-8"))
    assert cm["anle"]["da_kiem"] is True and cm["anle"]["so_vu_test_anle"] == 2 and list(cm["anle"]["bi_loai"]) == ["tr010"]
    assert cm["anle"]["bi_loai"]["tr010"]["ma_anle"] == "AL1" and cm["anle"]["bi_loai"]["tr010"]["do_chua"] >= 0.5
    ma = cm["id"]
    assert "tr010" not in ma["hoc"] + ma["dev"] and "tr020" in ma["hoc"] + ma["dev"]
    assert len(ma["test"]) == 30 and cm["g0"]["loi"] == []
    assert "vụ test án lệ" in (ra / "bao_cao_chon.md").read_text(encoding="utf-8")
    # tắt kiểm / thiếu file / file không có vụ trùng
    r = _chay("--vao", str(vao), "--ra", str(ra), "--index", str(idx), "--chi-chon", *THAM_SO_CHON)
    assert r.returncode == 0 and json.loads((ra / "chon_mau.json").read_text(encoding="utf-8"))["anle"]["da_kiem"] is False
    r = _chay("--vao", str(vao), "--ra", str(ra), "--index", str(idx), "--chi-chon", "--ban-an-anle", str(nam / "khong_co.json"), *THAM_SO_ANLE)
    assert r.returncode != 0 and "không thấy" in r.stderr
    sach = _anle(nam / "sach.json", ("AL9", "test", _van(999)))
    r = _chay("--vao", str(vao), "--ra", str(ra), "--index", str(idx), "--chi-chon", "--ban-an-anle", str(sach), *THAM_SO_ANLE)
    assert r.returncode == 0 and json.loads((ra / "chon_mau.json").read_text(encoding="utf-8"))["anle"]["bi_loai"] == {}


# --------------------------------------------------------------------------------------------------------------------
# Notebook V3
# --------------------------------------------------------------------------------------------------------------------


def _nb_v2(tmp: Path) -> Path:
    kaggle = tmp / "kaggle"
    kaggle.mkdir()
    for t in ("lexo_hoc_chon_dieu", "lexo_gop_gguf", "lexo_do_ban_an"):
        shutil.copyfile(ROOT / "kaggle" / f"{t}.ipynb", kaggle / f"{t}.ipynb")
    return kaggle


def test_tao_notebook_cbba_thay_dung_cho_va_ghi_epoch(tmp_path):
    kaggle = _nb_v2(tmp_path)
    r = subprocess.run([sys.executable, str(SCRIPT_NB), "--kaggle", str(kaggle), "--epoch", "2"], capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    nb = {t: json.loads((kaggle / f"{t}.ipynb").read_text(encoding="utf-8")) for t in ("lexo_hoc_cbba", "lexo_gop_gguf_cbba", "lexo_do_ban_an_cbba")}
    chu = {t: "\n".join("".join(c["source"]) for c in d["cells"]) for t, d in nb.items()}
    assert "EPOCH = 1, 8, 2" in chu["lexo_hoc_cbba"] and "EPOCH = 1, 8, 3" not in chu["lexo_hoc_cbba"]
    assert 'TEN = "lexo-qwen3-8b-chon-dieu-cbba-v1"' in chu["lexo_hoc_cbba"] and "lexo_hoc_chon_dieu_cbba.zip" in chu["lexo_hoc_cbba"]
    assert 'TEN = "lexo-qwen3-8b-chon-dieu-cbba-v1"' in chu["lexo_gop_gguf_cbba"]
    do = chu["lexo_do_ban_an_cbba"]
    assert "CHAY_VONG_1 = False" in do and 'MO_HINH_LORA = "qwen3-8b-lexo-chon-dieu-cbba-v1"' in do and "99 vụ" not in do
    assert '"cau_hinh": ["A", "C0", "L"]' in do and "tot_nhat_cu" not in do
    for d in nb.values():
        assert d["cells"][0]["cell_type"] == "markdown" and d["cells"][0]["source"][0].startswith("# V3")
        ids = [c["id"] for c in d["cells"]]
        assert len(set(ids)) == len(ids)
        for c in d["cells"]:
            if c["cell_type"] == "code":
                ast.parse("".join(c["source"]))
    # còn lại giống V2 từng ô (trừ chỗ đã thay): số ô V3 = số ô V2 + 1
    for t3, t2 in (("lexo_hoc_cbba", "lexo_hoc_chon_dieu"), ("lexo_gop_gguf_cbba", "lexo_gop_gguf"), ("lexo_do_ban_an_cbba", "lexo_do_ban_an")):
        assert len(nb[t3]["cells"]) == len(json.loads((kaggle / f"{t2}.ipynb").read_text(encoding="utf-8"))["cells"]) + 1


def test_tao_notebook_cbba_dung_khi_v2_doi_va_khong_ghi_file(tmp_path):
    kaggle = _nb_v2(tmp_path)
    p = kaggle / "lexo_hoc_chon_dieu.ipynb"
    p.write_text(p.read_text(encoding="utf-8").replace("EPOCH = 1, 8, 3", "EPOCH = 1, 8, 4"), encoding="utf-8")
    r = subprocess.run([sys.executable, str(SCRIPT_NB), "--kaggle", str(kaggle)], capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    assert r.returncode != 0 and "xuất hiện 0 lần" in r.stderr
    assert not list(kaggle.glob("*_cbba.ipynb")) and not (kaggle / "lexo_hoc_cbba.ipynb").exists()
    shutil.copyfile(ROOT / "kaggle" / "lexo_hoc_chon_dieu.ipynb", p)
    (kaggle / "lexo_gop_gguf.ipynb").unlink()
    r = subprocess.run([sys.executable, str(SCRIPT_NB), "--kaggle", str(kaggle)], capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    assert r.returncode != 0 and "tao_notebook_kaggle.py" in r.stderr
