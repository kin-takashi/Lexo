"""Các script dòng lệnh của Bước 2 chạy đầu-cuối trên bộ luật thử nghiệm (subprocess, CSDL và raw/ tạm)."""
import os
import subprocess
import sys
from pathlib import Path

from src.ingest.amending_law import stage_amending_law
from src.ingest.base_law import stage_base_law

from test_apply_rebuild import BASE_LINES
from test_extract_commands import ALI2, AMEND, LUAT, SCOPE2
from test_ingest_lookup import approved_review, build_docx

ROOT = Path(__file__).resolve().parent.parent


def run(script, *args, raw, expect=0):
    env = {**os.environ, "LEXO_RAW_DIR": str(raw), "PYTHONIOENCODING": "utf-8"}
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / script), *map(str, args)], capture_output=True, text=True,
                       encoding="utf-8", env=env, cwd=ROOT, timeout=120)
    assert p.returncode == expect, f"{script} {args} -> {p.returncode}\n{p.stdout}\n{p.stderr}"
    return p.stdout + p.stderr


def test_quy_trinh_dong_lenh_dau_cuoi(tmp_path):
    raw, db = tmp_path / "raw", tmp_path / "db" / "luat.sqlite"
    st = stage_base_law(build_docx(tmp_path / "BLTN.docx", BASE_LINES), raw, ten_viet_tat="BLTN")
    approved_review(st)
    stage_amending_law(build_docx(tmp_path / "LSD.docx", AMEND, so_hieu=LUAT), raw, aliases=ALI2, pham_vi_so_hieu=SCOPE2)
    run("ingest_base_law.py", st.directory.name, "--db", db, raw=raw)

    out = run("extract_commands.py", "11-2029-QH99", "--dich", "99/2098/QH99", "--nap", "--db", db, raw=raw)
    assert "4/4 mục lệnh" in out and "100.0%" in out and "4 lệnh" in out and "đã nạp 4 lệnh chờ duyệt" in out
    assert (raw / "11-2029-QH99" / "commands.json").exists()
    out = run("extract_commands.py", "11-2029-QH99", "--dich", "99/2098/QH99", "--nap", "--db", db, raw=raw, expect=2)      # nạp lại không --thay
    assert "LỖI nạp" in out and "--thay" in out

    assert "chờ duyệt 4, đã duyệt 0" in run("apply_commands.py", "tong-quan", "99/2098/QH99", "--db", db, raw=raw)
    out = run("lookup.py", "Điều 2 BLTN", "--ngay", "2030-01-01", "--db", db, raw=raw)
    assert "CHƯA được duyệt" in out and "giảm nhẹ" in out and "miễn trách nhiệm" not in out            # chưa duyệt thì chưa áp
    prev = tmp_path / "preview.sqlite"
    out = run("apply_commands.py", "xem-truoc", "99/2098/QH99", "--luu", prev, "--db", db, raw=raw)
    assert "4 chạy được, 0 lỗi" in out and prev.exists()
    assert "miễn trách nhiệm" in run("lookup.py", "Điều 2 BLTN", "--ngay", "2030-01-01", "--db", prev, raw=raw)

    out = run("apply_commands.py", "bao-cao", "99/2098/QH99", LUAT, "--db", db, raw=raw)
    assert (raw / "11-2029-QH99" / "lenh_cho_duyet.md").read_text(encoding="utf-8").count("## #") == 4
    run("apply_commands.py", "duyet", "99/2098/QH99", LUAT, "--db", db, raw=raw, expect=2)                    # thiếu --nguoi (argparse)
    run("apply_commands.py", "duyet", "99/2098/QH99", LUAT, "--nguoi", "Người kiểm thử", "--db", db, raw=raw)
    assert "Đã dựng lại" in run("apply_commands.py", "ap-dung", "99/2098/QH99", "--db", db, raw=raw)

    out = run("lookup.py", "Điều 2 BLTN", "--ngay", "2030-01-01", "--db", db, raw=raw)
    assert "miễn trách nhiệm hình sự" in out and f"Luật số {LUAT} (Điều 1 khoản 1), hiệu lực từ 01/01/2030" in out
    assert "giảm nhẹ" in run("lookup.py", "Điều 2 BLTN", "--ngay", "2029-12-31", "--db", db, raw=raw)           # xem bản cũ
    out = run("lookup.py", "Điều 4 BLTN", "--ngay", "2030-01-01", "--db", db, raw=raw, expect=1)
    assert "đã hết hiệu lực từ 01/01/2030" in out and LUAT in out
    out = run("lookup.py", "Điều 4 BLTN", "--db", db, raw=raw)                   # hôm nay (2026) luật sửa đổi chưa có hiệu lực (2030)
    assert "lừa đảo" in out and "sẽ có sửa đổi hiệu lực từ 01/01/2030" in out
    out = run("lookup.py", "Điều 3 BLTN", "--lich-su", "--db", db, raw=raw)
    assert "Lịch sử Điều 3" in out and "01/01/2030" in out and "Điều 1 khoản 4" in out
    out = run("lookup.py", "Điều 3 BLTN", "--so-sanh", "2029-12-31", "2030-01-01", "--db", db, raw=raw)
    assert "-1. Người nào trộm cắp tài sản thì bị phạt tù từ 01 năm đến 03 năm." in out.replace("  ", "")
    assert "hiệu lực thi hành từ ngày 01 tháng 01 năm 2030" in run("lookup.py", "Điều 3 BLTN", "--chuyen-tiep", "--db", db, raw=raw)
