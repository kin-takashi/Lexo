"""scripts/doi_chieu_vbhn.py chạy đầu-cuối (subprocess, CSDL và raw/ tạm) trên bộ luật thử nghiệm và 'văn bản hợp nhất' giả lập."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from src.ingest.base_law import stage_base_law

from test_apply_rebuild import BASE_LINES
from test_ingest_lookup import approved_review, build_docx

ROOT = Path(__file__).resolve().parent.parent
DICH = "99/2098/QH99"
THAN = BASE_LINES[3:BASE_LINES.index("________________")]          # từ "Chương I" đến hết Điều 5 (thân văn bản hợp nhất giả lập)


def run(script, *args, raw, expect=0):
    env = {**os.environ, "LEXO_RAW_DIR": str(raw), "PYTHONIOENCODING": "utf-8"}
    p = subprocess.run([sys.executable, str(ROOT / "scripts" / script), *map(str, args)], capture_output=True, text=True,
                       encoding="utf-8", env=env, cwd=ROOT, timeout=120)
    assert p.returncode == expect, f"{script} {args} -> {p.returncode}\n{p.stdout}\n{p.stderr}"
    return p.stdout + p.stderr


def ghi_vbhn(raw, slug, lines):
    d = raw / slug
    d.mkdir(parents=True, exist_ok=True)
    (d / "vbhn.json").write_text(json.dumps({"lines": lines, "marks": {}, "footnotes": {}, "preamble": [], "pages": [[1, 1]] * len(lines),
                                             "sources": []}, ensure_ascii=False), encoding="utf-8")


def thay(lines, cu, moi):
    assert any(cu in x for x in lines)
    return [x.replace(cu, moi) for x in lines]


def dung(tmp_path):
    raw, db = tmp_path / "raw", tmp_path / "db" / "luat.sqlite"
    st = stage_base_law(build_docx(tmp_path / "BLTN.docx", BASE_LINES), raw, ten_viet_tat="BLTN")
    approved_review(st)
    run("ingest_base_law.py", st.directory.name, "--db", db, raw=raw)
    return raw, db, st.directory.name


def test_doi_chieu_va_hieu_dinh_dau_cuoi(tmp_path):
    raw, db, slug = dung(tmp_path)
    ghi_vbhn(raw, "135-VBHN-VPQH", thay(THAN, "quy định về tội phạm", "quy định về các tội phạm"))      # văn bản hợp nhất chính: thêm chữ 'các'
    ghi_vbhn(raw, "11-VBHN-VPQH", thay(THAN, "quy định về tội phạm", "quy định về các tội phạm"))        # bản tham chiếu đồng thuận
    common = ["--dich", DICH, "--db", db]

    out = run("doi_chieu_vbhn.py", "so-sanh", *common, "--ngay", "2026-01-01", "--bao-cao", tmp_path / "bc.md", raw=raw)
    assert "sai khác nội dung: 1 chỗ ở 1 Điều" in out and "khac_noi_dung" in out and "giống hệt từng chữ" in out
    assert "dieu 1" in (tmp_path / "bc.md").read_text(encoding="utf-8")

    out = run("doi_chieu_vbhn.py", "de-xuat", *common, raw=raw)
    assert "Đề xuất hiệu đính: 1 (mới 1, đã có 0); theo loại: loi_go 1" in out
    assert "đã có 1" in run("doi_chieu_vbhn.py", "de-xuat", *common, raw=raw)                       # chạy lại không nhân đôi
    hdj = json.loads((raw / slug / "hieu_dinh.json").read_text(encoding="utf-8"))
    assert [r["trang_thai_duyet"] for r in hdj["quy_tac"]] == ["cho_duyet"]
    out = run("doi_chieu_vbhn.py", "danh-sach", *common, raw=raw)
    assert "[cho_duyet]" in out and "“về tội” → “về các tội”" in out and "11/VBHN-VPQH" in out

    # chưa duyệt: tra cứu báo nhưng không áp
    out = run("lookup.py", "Điều 1 BLTN", "--ngay", "2026-01-01", "--db", db, raw=raw)
    assert "quy định về tội phạm" in out and "1 đề xuất hiệu đính kỹ thuật chưa được duyệt" in out and "CHƯA duyệt" in out
    run("doi_chieu_vbhn.py", "duyet", *common, raw=raw, expect=2)                                  # thiếu --nguoi (argparse)

    out = run("doi_chieu_vbhn.py", "duyet", "--nguoi", "Người kiểm thử", "--ap-dung", *common, raw=raw)
    assert "Đã duyệt 1 đề xuất (người duyệt: Người kiểm thử)" in out and "Hiệu đính: 1/1 quy tắc đã áp." in out
    out = run("doi_chieu_vbhn.py", "so-sanh", *common, "--ngay", "2026-01-01", raw=raw)
    assert "sai khác nội dung: 0 chỗ" in out and "(100.00%)" in out

    out = run("lookup.py", "Điều 1 BLTN", "--ngay", "2026-01-01", "--db", db, raw=raw)
    assert "quy định về các tội phạm" in out and "hiệu đính kỹ thuật" in out and "duyệt: Người kiểm thử" in out
    out = run("lookup.py", "Điều 1 BLTN", "--ngay", "2026-01-01", "--nguyen-van", "--db", db, raw=raw)
    assert "quy định về tội phạm" in out and "NGUYÊN VĂN" in out and "hiệu đính kỹ thuật:" not in out
    assert "quy định về tội phạm" in run("lookup.py", "Điều 1 BLTN", "--ngay", "2016-07-01", "--nguyen-van", "--db", db, raw=raw)

    # init_db --reset rồi nạp lại từ file: quyết định không mất
    run("init_db.py", "--reset", "--db", db, raw=raw)
    run("ingest_base_law.py", slug, "--db", db, raw=raw)
    assert "quy định về tội phạm" in run("lookup.py", "Điều 1 BLTN", "--ngay", "2026-01-01", "--db", db, raw=raw)
    assert "thêm 1" in run("doi_chieu_vbhn.py", "nap", *common, raw=raw)
    out = run("apply_commands.py", "ap-dung", DICH, "--db", db, raw=raw)
    assert "Hiệu đính kỹ thuật: 1/1 quy tắc đã duyệt đã áp." in out
    assert "quy định về các tội phạm" in run("lookup.py", "Điều 1 BLTN", "--ngay", "2026-01-01", "--db", db, raw=raw)


def test_khong_co_bang_chung_thi_khong_de_xuat(tmp_path):
    raw, db, _ = dung(tmp_path)
    ghi_vbhn(raw, "135-VBHN-VPQH", thay(THAN, "quy định về tội phạm", "quy định về các tội phạm"))      # chỉ MỘT văn bản hợp nhất, không bản nào đồng thuận
    out = run("doi_chieu_vbhn.py", "de-xuat", "--dich", DICH, "--db", db, raw=raw)
    assert "Đề xuất hiệu đính: 0" in out and "thieu_bang_chung" in out and "dieu 1 [noi_dung]" in out
    # có xác minh nguồn do người ghi thì được đề xuất, kèm nguồn trong bằng chứng
    (raw / "99-2098-QH99" / "xac_minh_nguon.json").write_text(
        json.dumps({"muc": [{"khoa": "dieu 1", "nguon": "Công báo thử nghiệm, tr. 1"}]}, ensure_ascii=False), encoding="utf-8")
    assert "Đề xuất hiệu đính: 1" in run("doi_chieu_vbhn.py", "de-xuat", "--dich", DICH, "--db", db, raw=raw)
    assert "đã kiểm nguồn: Công báo thử nghiệm, tr. 1" in run("doi_chieu_vbhn.py", "danh-sach", "--dich", DICH, "--db", db, raw=raw)


def test_loi_thuong_gap(tmp_path):
    raw, db, _ = dung(tmp_path)
    out = run("doi_chieu_vbhn.py", "so-sanh", "--dich", DICH, "--db", db, raw=raw, expect=2)           # chưa trich: không có vbhn.json
    assert "Chưa có" in out and "trich" in out
    assert "Không có văn bản 1/2000/XX" in run("doi_chieu_vbhn.py", "danh-sach", "--dich", "1/2000/XX", "--db", db, raw=raw, expect=2)
    assert "Chưa có CSDL" in run("doi_chieu_vbhn.py", "danh-sach", "--db", tmp_path / "khong_co.sqlite", raw=raw, expect=2)
    assert "Chưa có đề xuất nào" in run("doi_chieu_vbhn.py", "danh-sach", "--dich", DICH, "--db", db, raw=raw)
    assert "Không có" in run("doi_chieu_vbhn.py", "nap", "--dich", DICH, "--db", db, raw=raw, expect=2)
    shutil.rmtree(raw, ignore_errors=True)
    assert "Không có PDF nào" in run("doi_chieu_vbhn.py", "trich", "khong-co-thu-muc", raw=raw, expect=2)


def test_con_lenh_chua_duyet_thi_de_xuat_bi_tu_choi_tru_khi_xem_truoc(tmp_path):
    from src.ingest.amending_law import stage_amending_law

    from test_extract_commands import ALI2, AMEND, LUAT, SCOPE2

    raw, db, _ = dung(tmp_path)
    stage_amending_law(build_docx(tmp_path / "LSD.docx", AMEND, so_hieu=LUAT), raw, aliases=ALI2, pham_vi_so_hieu=SCOPE2)
    run("extract_commands.py", "11-2029-QH99", "--dich", DICH, "--nap", "--db", db, raw=raw)
    ghi_vbhn(raw, "135-VBHN-VPQH", thay(THAN, "quy định về tội phạm", "quy định về các tội phạm"))
    ghi_vbhn(raw, "11-VBHN-VPQH", thay(THAN, "quy định về tội phạm", "quy định về các tội phạm"))
    common = ["--dich", DICH, "--db", db]

    out = run("doi_chieu_vbhn.py", "de-xuat", *common, raw=raw, expect=2)                              # bản hệ thống chưa gồm luật sửa đổi -> kết quả sẽ sai
    assert "LỖI: còn 4 lệnh sửa đổi CHƯA được duyệt" in out and "--xem-truoc" in out
    assert not (raw / "99-2098-QH99" / "hieu_dinh.json").exists()
    assert "Lưu ý: còn 4 lệnh sửa đổi CHƯA được duyệt" in run("doi_chieu_vbhn.py", "so-sanh", *common, "--ngay", "2026-01-01", raw=raw)
    assert "BẢN CHẠY THỬ" in run("doi_chieu_vbhn.py", "so-sanh", *common, "--ngay", "2026-01-01", "--xem-truoc", raw=raw)
    out = run("doi_chieu_vbhn.py", "de-xuat", *common, "--xem-truoc", raw=raw)
    assert "Đề xuất hiệu đính:" in out and (raw / "99-2098-QH99" / "hieu_dinh.json").exists()
    out = run("doi_chieu_vbhn.py", "danh-sach", *common, raw=raw)
    assert "[cho_duyet]" in out and "“về tội” → “về các tội”" in out                                   # đề xuất vẫn chờ duyệt, ghi vào CSDL thật
