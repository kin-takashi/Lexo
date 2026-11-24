"""scripts/baseline_tfidf.py: đọc đúng tập, chấm đúng, chạy trọn trên dữ liệu giả nhỏ."""
from __future__ import annotations

import gzip
import importlib.util
import json
from pathlib import Path

import pytest

pytest.importorskip("sklearn")

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "baseline_tfidf.py"
_spec = importlib.util.spec_from_file_location("baseline_tfidf", SCRIPT)
bt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bt)

CHU = {
    "173": "bị cáo lén lút lấy trộm xe máy của người bị hại khi chủ nhà đi vắng rồi đem bán",
    "134": "bị cáo dùng dao đâm người bị hại gây thương tích tỷ lệ tổn thương cơ thể",
    "251": "bị cáo mua bán trái phép chất ma tuý heroin thu lợi bất chính",
}


def _ghi(p, dong):
    with gzip.open(p, "wt", encoding="utf-8") as f:
        for r in dong:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


@pytest.fixture()
def du_lieu(tmp_path):
    train, test = [], []
    i = 0
    for d, c in CHU.items():
        for k in range(6):
            i += 1
            train.append({"ma": str(i), "tap": "train", "nhom_vu": f"g{i}", "dau_vao": f"{c} lần {k}", "dieu": [d, "51"],
                          "ngay": "2020-05-01"})
    train.append({"ma": "cu", "tap": "train", "nhom_vu": "gcu", "dau_vao": CHU["173"], "dieu": ["138"], "ngay": "2016-01-01"})
    train.append({"ma": "dev1", "tap": "train", "nhom_vu": "g1", "dau_vao": CHU["134"], "dieu": ["134"], "ngay": "2021-01-01"})
    for j, (d, c) in enumerate(CHU.items()):
        test.append({"ma": f"t{j}", "tap": "test", "nhom_vu": f"tg{j}", "dau_vao": c, "dieu": [d], "ngay": "2022-01-01"})
    _ghi(tmp_path / "train.jsonl.gz", train)
    _ghi(tmp_path / "test.jsonl.gz", test)
    hoc = [str(x) for x in range(2, 19)]
    chon = {"id": {"hoc": hoc, "dev": ["dev1"], "dev_do": ["dev1"], "test": ["t0", "t1", "t2"]}}
    (tmp_path / "chon.json").write_text(json.dumps(chon), encoding="utf-8")
    return tmp_path


def test_nhan_chi_giu_dieu_toi_pham():
    assert bt.nhan({"dieu": ["51", "173", "52", "38"]}) == ["173"]
    assert bt.nhan({"dieu": "134"}) == ["134"]


def test_doc_train_toan_bo_bo_nhom_dev_va_ngay_cu(du_lieu):
    chu, y, tk = bt.doc_train(du_lieu / "train.jsonl.gz", "toan_bo", set(), {"dev1"})
    assert tk["nhom_dev"] == 2          # dev1 và văn bản 1 cùng nhóm g1
    assert tk["sai_ngay"] == 1
    assert len(chu) == 17 and all(len(n) == 1 for n in y)


def test_doc_train_hoc_thieu_ma_bao_loi(du_lieu):
    with pytest.raises(bt.BaselineError):
        bt.doc_train(du_lieu / "train.jsonl.gz", "hoc", {"2", "khong_co"}, set())


def test_cham_va_chi_so():
    assert bt.cham(["173"], ["173"])["khop_dung"] == 1.0
    c = bt.chi_so([(["173"], ["173"]), (["134"], ["134", "135"]), (["251"], ["249"])])
    assert c["micro_p"] == pytest.approx(2 / 4) and c["micro_r"] == pytest.approx(2 / 3)
    assert c["khop_dung"] == pytest.approx(1 / 3) and c["tim_du"] == pytest.approx(2 / 3)
    assert bt.recall_k([(["1"], ["2", "1"]), (["3"], ["3"])], 1) == 0.5


def test_mcnemar():
    assert bt.mcnemar_p(0, 0) == 1.0
    assert bt.mcnemar_p(29, 9) == pytest.approx(0.00166, abs=1e-4)


def test_test_can_da_chot(du_lieu):
    assert bt.main(["--train", str(du_lieu / "train.jsonl.gz"), "--chon", str(du_lieu / "chon.json"), "--tap", "test"]) == 2


def test_chay_tron(du_lieu):
    ra = du_lieu / "ra"
    so_voi = du_lieu / "so_voi"
    so_voi.mkdir()
    (so_voi / "C0.jsonl").write_text(json.dumps({"id": "cbba_t0", "dieu": ["173"], "hien_thi": ["173", "323"]}) + "\n", encoding="utf-8")
    rc = bt.main(["--train", str(du_lieu / "train.jsonl.gz"), "--test", str(du_lieu / "test.jsonl.gz"), "--chon", str(du_lieu / "chon.json"),
                  "--muc", "hoc", "--tap", "test", "--da-chot", "--so-voi", str(so_voi), "--ra", str(ra)])
    assert rc == 0
    dong = [json.loads(x) for x in (ra / "T_hoc.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["id"] for r in dong] == ["cbba_t0", "cbba_t1", "cbba_t2"]
    assert all(r["hien_thi"] == r["dieu"] for r in dong)
    md = (ra / "bao_cao_T_hoc.md").read_text(encoding="utf-8")
    assert "C0 (cùng 1 vụ)" in md and "McNemar" in md
