"""Dựng gói NGUỒN cho notebook Kaggle lexo_dong_goi_cbba.ipynb (chạy trên laptop, trong E:\\Lexo).

  python scripts/dong_goi_nguon_cbba.py            # ghi inbox/kaggle_cbba_nguon/lexo_cbba_nguon.zip
  python scripts/dong_goi_nguon_cbba.py --khong-zip   # chỉ dựng thư mục, tự tải lên

Chép: src/, scripts/, config.yaml, requirements*.txt (nếu có), db/chi_muc.sqlite, inbox/cbba_blhs/nhan/{train,test}.jsonl,
inbox/anle_hf/ban_an_hinh_su.json (nếu có), kaggle/*cbba*, kaggle/*V3*; bỏ __pycache__, .git, mọi môi trường ảo (env, venv, .venv, thư mục có pyvenv.cfg), file có tên chứa [ ] < > : \" | ? *; ghi SHA256SUMS.
Tải lên Kaggle thành Dataset PRIVATE tên lexo_cbba_nguon (Kaggle tự giải nén zip). Chứa vụ test: không để Public.
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEN_BO = {"__pycache__", ".git", ".venv", "venv", "env", ".env", "site-packages", ".pytest_cache", ".mypy_cache", ".idea", ".vscode", "node_modules"}
KY_TU_CAM = set('[]<>:"|?*\\')       # Kaggle từ chối tên file chứa các ký tự này
DA_BO: list[str] = []


def bo(thu_muc: str, ten: list[str]) -> set[str]:
    """Bỏ môi trường ảo (thư mục có pyvenv.cfg hoặc tên quen thuộc), bộ nhớ đệm, và file có tên Kaggle không nhận."""
    ra = set()
    for t in ten:
        p = Path(thu_muc) / t
        if t in TEN_BO or t.endswith(".pyc") or (p.is_dir() and (p / "pyvenv.cfg").exists()) or (set(t) & KY_TU_CAM):
            ra.add(t)
            if p.is_dir() or set(t) & KY_TU_CAM:
                DA_BO.append(str(p))
    return ra
CAN_CO = ["scripts/dong_goi_cbba_kaggle.py", "scripts/do_ban_an.py", "src/ban_an/cbba_kaggle.py", "src/ban_an/chon_dieu.py",
          "src/ban_an/goi_kaggle.py", "config.yaml", "db/chi_muc.sqlite", "inbox/cbba_blhs/nhan/train.jsonl", "inbox/cbba_blhs/nhan/test.jsonl"]


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 24), b""):
            h.update(b)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ra", type=Path, default=ROOT / "inbox" / "kaggle_cbba_nguon")
    ap.add_argument("--khong-zip", action="store_true")
    a = ap.parse_args()
    thieu = [x for x in CAN_CO if not (ROOT / x).exists()]
    if thieu:
        sys.exit(f"LỖI: thiếu {thieu} (chạy xu_ly_cbba_blhs.py và dựng chỉ mục trước)")
    ra = a.ra if a.ra.is_absolute() else ROOT / a.ra
    goi = ra / "lexo_cbba_nguon"
    if goi.exists():
        shutil.rmtree(goi)
    goi.mkdir(parents=True)
    for d in ("src", "scripts"):
        shutil.copytree(ROOT / d, goi / d, ignore=bo)
    for f in ["config.yaml", *[p.name for p in ROOT.glob("requirements*.txt")]]:
        if (ROOT / f).exists():
            shutil.copy2(ROOT / f, goi / f)
    for rel in ("db/chi_muc.sqlite", "inbox/cbba_blhs/nhan/train.jsonl", "inbox/cbba_blhs/nhan/test.jsonl", "inbox/anle_hf/ban_an_hinh_su.json"):
        if (ROOT / rel).exists():
            (goi / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / rel, goi / rel)
        else:
            print(f"CẢNH BÁO: không thấy {rel} (bỏ qua)")
    if (ROOT / "kaggle").exists():
        (goi / "kaggle").mkdir()
        for p in sorted((ROOT / "kaggle").glob("*")):
            if p.is_file() and p.suffix in (".ipynb", ".md") and ("cbba" in p.name or "V3" in p.name):
                shutil.copy2(p, goi / "kaggle" / p.name)
    if DA_BO:
        print(f"Đã bỏ {len(DA_BO)} thư mục/tệp (môi trường ảo, bộ nhớ đệm, tên không hợp lệ):")
        for x in DA_BO[:15]:
            print("  -", x)
    tep = sorted(p for p in goi.rglob("*") if p.is_file())
    xau = [p for p in tep if set(p.name) & KY_TU_CAM]
    if xau:
        sys.exit(f"LỖI: còn file có tên Kaggle không nhận: {xau[:5]}")
    to = sorted(tep, key=lambda p: p.stat().st_size, reverse=True)[:8]
    print("File lớn nhất:", ", ".join(f"{p.relative_to(goi).as_posix()} ({p.stat().st_size / 2**20:.0f} MiB)" for p in to))
    (goi / "SHA256SUMS").write_text("".join(f"{sha256(p)}  {p.relative_to(goi).as_posix()}\n" for p in tep), encoding="utf-8", newline="\n")
    tong = sum(p.stat().st_size for p in tep)
    print(f"Đã dựng {goi}: {len(tep)} file, {tong / 2**20:.0f} MiB")
    if a.khong_zip:
        return 0
    z = ra / "lexo_cbba_nguon.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as f:
        for p in sorted(goi.rglob("*")):
            if p.is_file():
                f.write(p, p.relative_to(ra).as_posix())
    print(f"Đã ghi {z} ({z.stat().st_size / 2**20:.0f} MiB, sha256 {sha256(z)})")
    print("Tiếp: Kaggle → Datasets → New Dataset → tải zip này lên, tên lexo_cbba_nguon, Private.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
