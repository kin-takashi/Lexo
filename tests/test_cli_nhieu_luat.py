"""scripts/lookup.py khi kho có nhiều bộ luật nối tiếp cùng tên viết tắt (BLHS 1999 → BLHS 2015): không nêu năm thì dùng bộ luật đang có
hiệu lực tại ngày xem."""
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from test_agent_nhieu_luat import dung_kho

ROOT = Path(__file__).resolve().parent.parent


def run(db, *args, expect=0):
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / "lookup.py"), *args, "--db", str(db)], capture_output=True, text=True,
                       encoding="utf-8", env=env, cwd=ROOT, timeout=120)
    assert p.returncode == expect, f"{args} -> {p.returncode}\n{p.stdout}\n{p.stderr}"
    return p.stdout, p.stderr


@pytest.fixture
def db(tmp_path):
    k = dung_kho(tmp_path, co_chi_muc=False, ten="cli")
    path = tmp_path / "cli.sqlite"
    dest = sqlite3.connect(path)
    k.c.backup(dest)
    dest.close()
    k.c.close()
    return path


def test_khong_nem_nam_chon_bo_luat_theo_ngay_xem(db):
    out, err = run(db, "Điều 2 BLHS", "--ngay", "2010-05-05")
    assert "[15/1999/QH10" in out and "miễn án phạt" in out and "37/2009/QH12" in out
    assert "áp dụng 15/1999/QH10" in err and "100/2015/QH13" in err          # nói rõ đã chọn bộ nào, trong những bộ nào
    out, err = run(db, "Điều 2 BLHS", "--ngay", "2018-01-01")
    assert "[100/2015/QH13" in out and "miễn trách nhiệm hình sự" in out and "áp dụng 100/2015/QH13" in err


def test_khong_nem_nam_va_khong_ngay_dung_bo_luat_hom_nay(db):
    out, _ = run(db, "Điều 2 BLHS")
    assert "[100/2015/QH13" in out


def test_ngay_khong_thuoc_bo_luat_nao_thi_van_doi_nam(db):
    _, err = run(db, "Điều 2 BLHS", "--ngay", "1990-01-01", expect=1)
    assert "hãy thêm năm" in err and "15/1999/QH10" in err and "100/2015/QH13" in err


def test_neu_nam_thi_dung_dung_bo_do_ke_ca_khi_ngay_o_ngoai(db):
    out, err = run(db, "Điều 2 BLHS 2015", "--ngay", "2010-05-05", expect=1)
    assert "[100/2015/QH13" in out and "Có 2 bộ luật" not in err
