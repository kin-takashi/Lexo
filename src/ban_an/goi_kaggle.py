"""Dựng hai gói dữ liệu cho Kaggle từ bộ bản án (inbox/anle_hf) và tập tổng hợp sạch (train/sach), xem scripts/dong_goi_kaggle.py.

  gói HỌC  (lexo_hoc_chon_dieu): SFT «chọn Điều từ ứng viên»; 70 vụ bản án + 368 mẫu tổng hợp (train), 20 vụ dev + 51 mẫu (val).
           KHÔNG chứa chữ của vụ test nào; chỉ có băm của chúng (kiem_giao.json) để notebook học tự kiểm.
  gói ĐO   (lexo_do_ban_an): mã nguồn + chỉ mục + 189 vụ (90 train + 99 test) kèm ứng viên đã xếp hạng, cho scripts/do_ban_an.py.

Mỗi gói có SHA256SUMS; file zip dựng xác định (thứ tự cố định, mốc thời gian cố định) nên chạy lại cùng dữ liệu ra cùng mã băm.
"""
from __future__ import annotations

import hashlib
import json
import zipfile
from collections.abc import Callable, Iterable, Sequence
from pathlib import Path

from src.ban_an import chon_dieu as cd
from src.ban_an.anle_hf import trung_voi

NGUON_BAN_AN, NGUON_TONG_HOP = "ban_an", "tong_hop"
TEN_GOI_HOC, TEN_GOI_DO = "lexo_hoc_chon_dieu", "lexo_do_ban_an"
DAU_GOI_HOC, DAU_GOI_DO = "LEXO_HOC_CHON_DIEU.md", "LEXO_DO_BAN_AN.md"      # file đánh dấu: notebook tìm gói theo tên file này
MOC_ZIP = (2026, 1, 1, 0, 0, 0)


class GoiError(ValueError):
    pass


# --------------------------------------------------------------------------------------------------------------------
# 1. Mẫu
# --------------------------------------------------------------------------------------------------------------------


def mau_ban_an(ban_an: dict, so_dev: int = 20, seed: int = 2026) -> list[dict]:
    """Các vụ của ban_an_hinh_su.json thành mẫu chung: tap 'hoc' | 'dev' (chia 90 vụ train theo nhóm vụ) | 'test'."""
    goc = ban_an.get("mau") or []
    if not goc:
        raise GoiError("bộ bản án rỗng")
    train = [b for b in goc if b.get("tap") == "train"]
    if not train or not any(b.get("tap") == "test" for b in goc):
        raise GoiError("bộ bản án phải có cả tập train và test (chạy scripts/xu_ly_anle_hf.py)")
    chia = cd.chia_dev(train, {b["ma"]: b["nhom_vu"] for b in train}, so_dev, seed)
    dieu_train = {d for b in train for d in b["dieu"]}
    ra = []
    for b in goc:
        if b.get("tap") not in ("train", "test"):
            raise GoiError(f"{b.get('ma')}: tap = {b.get('tap')!r}")
        sv, da_cat = cd.cat_su_viec(b["dau_vao"])
        ra.append({"id": b["ma"], "nguon": NGUON_BAN_AN, "tap": chia[b["ma"]] if b["tap"] == "train" else "test",
                   "su_viec": sv, "da_cat": da_cat, "so_tu_goc": len(b["dau_vao"].split()), "dieu": cd.sap_xep(b["dieu"]),
                   "nhom_vu": b["nhom_vu"], "ngay": b.get("ngay"), "ngay_tra_cuu": cd.ngay_tra_cuu(b.get("ngay")),
                   "ten_toi_trong_loi_ke": int(b.get("ten_toi_trong_loi_ke") or 0),
                   "dieu_chua_gap": b["tap"] == "test" and any(d not in dieu_train for d in b["dieu"]),
                   "hash_dau_vao": b["hash_dau_vao"], "dau_vao_goc": b["dau_vao"]})
    return ra


def doc_jsonl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()]


def mau_tong_hop(tinh_huong: dict, ids_train: Sequence[str], ids_val: Sequence[str]) -> tuple[list[dict], list[str]]:
    """Mẫu tổng hợp (train/tinh_huong.json) theo đúng danh sách id của tập sạch n368 (train) và val sạch.
    Đáp án = hợp các Điều tội phạm của mọi hành vi (3/729 hành vi có hai Điều chấp nhận: lấy cả hai). Trả (mẫu, cảnh báo)."""
    theo_id = {x["id"]: x for x in tinh_huong["mau"]}
    ra, canh_bao = [], []
    for tap, ids in (("tong_hop_hoc", ids_train), ("tong_hop_val", ids_val)):
        for i in ids:
            if i not in theo_id:
                raise GoiError(f"id {i} của tập sạch không có trong tinh_huong.json")
            x = theo_id[i]
            vang = cd.sap_xep(d for h in x["hanh_vi"] for d in h["dieu"] if cd.la_dieu_toi_pham(d))
            bo = [d for h in x["hanh_vi"] for d in h["dieu"] if not cd.la_dieu_toi_pham(d)]
            if bo:
                canh_bao.append(f"{i}: bỏ Điều ngoài 108–425: {', '.join(bo)}")
            if not vang:
                canh_bao.append(f"{i}: không còn Điều tội phạm nào, bỏ mẫu")
                continue
            ra.append({"id": i, "nguon": NGUON_TONG_HOP, "tap": tap, "su_viec": x["tinh_huong"].strip(), "da_cat": False,
                       "so_tu_goc": len(x["tinh_huong"].split()), "dieu": vang, "ngay_tra_cuu": None})
    return ra, canh_bao


# --------------------------------------------------------------------------------------------------------------------
# 2. Ứng viên
# --------------------------------------------------------------------------------------------------------------------


def khoa_cache(ten_mo_hinh: str, ngay: str | None, chu: str) -> str:
    return cd.bam_chu(f"{cd.PHIEN_BAN_TIN_NHAN}|{cd.DOAN_TU}|{ten_mo_hinh}|{ngay}|{chu}")


def gan_xep_hang(mau: Sequence[dict], xep: Callable[[str, str | None], dict[str, list[str]]], cache: dict,
                 ten_mo_hinh: str, bao: Callable[[int, int], None] | None = None) -> None:
    """Gắn mau[i]['xep_hang'] = {che_do: [...]}; dùng / ghi vào cache {khóa: kết quả} (để chạy lại tiếp từ chỗ dừng)."""
    for i, x in enumerate(mau, 1):
        k = khoa_cache(ten_mo_hinh, x["ngay_tra_cuu"], x["su_viec"])
        if k not in cache:
            cache[k] = xep(x["su_viec"], x["ngay_tra_cuu"])
        x["xep_hang"] = cache[k]
        if bao:
            bao(i, len(mau))


# --------------------------------------------------------------------------------------------------------------------
# 3. SFT
# --------------------------------------------------------------------------------------------------------------------


def dong_sft(x: dict, che_do: str, k: int, tieu_de: dict[str, str]) -> dict:
    """Một dòng SFT. Ứng viên = top K của chế độ đã chọn, CHÈN đáp án còn thiếu (chỉ dùng cho tập học và val)."""
    uv, chen = cd.dung_ung_vien(x["xep_hang"][che_do], k, x["dieu"])
    tn = cd.dung_tin_nhan(x["su_viec"], uv, tieu_de) + [{"role": "assistant", "content": cd.dich_chon(x["dieu"])}]
    return {"id": x["id"], "nguon": x["nguon"], "messages": tn, "so_ung_vien": len(uv), "chen": chen, "da_cat": x["da_cat"],
            "so_tu_su_viec": len(x["su_viec"].split())}


# --------------------------------------------------------------------------------------------------------------------
# 4. Kiểm giao (G0)
# --------------------------------------------------------------------------------------------------------------------


def kiem_giao(test: Sequence[dict], hoc: Sequence[dict], nguong: float = 0.5) -> list[str]:
    """Lỗi rò rỉ giữa vụ test và mọi mẫu vào gói học (rỗng = sạch): trùng id, trùng nhóm vụ, trùng băm đầu vào,
    độ chứa 5-gram >= ngưỡng (so cả đầu vào gốc lẫn bản đã cắt của vụ test)."""
    loi = []
    id_hoc = {x["id"] for x in hoc}
    nhom_hoc = {x["nhom_vu"] for x in hoc if x.get("nhom_vu")}
    for t in test:
        if t["id"] in id_hoc:
            loi.append(f"{t['id']}: id vụ test nằm trong gói học")
        if t.get("nhom_vu") in nhom_hoc:
            loi.append(f"{t['id']}: nhóm vụ {t['nhom_vu']} có mặt ở cả test và gói học")
    van = {x["id"]: x.get("dau_vao_goc") or x["su_viec"] for x in hoc}
    ban_ghi = [{"ma": t["id"], "dau_vao": t["dau_vao_goc"], "hash_dau_vao": t["hash_dau_vao"]} for t in test]
    for c in trung_voi(ban_ghi, van, nguong):
        loi.append(f"{c['ma']}: trùng với {c['ma_cu']} (độ chứa 5-gram {c['do_chua']})")
    return loi


# --------------------------------------------------------------------------------------------------------------------
# 5. Ghi gói
# --------------------------------------------------------------------------------------------------------------------


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for khoi in iter(lambda: f.read(1 << 20), b""):
            h.update(khoi)
    return h.hexdigest()


def ghi_jsonl(p: Path, dong: Iterable[dict]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("".join(json.dumps(d, ensure_ascii=False) + "\n" for d in dong), encoding="utf-8", newline="\n")


def ghi_json(p: Path, obj) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def ghi_sha256sums(thu_muc: Path) -> Path:
    """SHA256SUMS (định dạng của sha256sum, đường dẫn tương đối, dấu /) cho mọi file trong thư mục, trừ chính nó."""
    dong = [f"{sha256_file(p)}  {p.relative_to(thu_muc).as_posix()}"
            for p in sorted(thu_muc.rglob("*")) if p.is_file() and p.name != "SHA256SUMS"]
    ra = thu_muc / "SHA256SUMS"
    ra.write_text("\n".join(dong) + "\n", encoding="utf-8", newline="\n")
    return ra


def kiem_sha256sums(thu_muc: Path) -> list[str]:
    """Như `sha256sum -c SHA256SUMS`: danh sách file sai / thiếu (rỗng = OK)."""
    sai = []
    for dong in (thu_muc / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        if not dong.strip():
            continue
        h, ten = dong.split("  ", 1)
        p = thu_muc / ten
        if not p.is_file():
            sai.append(f"thiếu {ten}")
        elif sha256_file(p) != h:
            sai.append(f"sai mã băm {ten}")
    return sai


def nen_zip(thu_muc: Path, dich: Path) -> str:
    """Nén thư mục thành zip xác định (thư mục gốc trong zip = tên thư mục). Trả sha256 của zip."""
    dich.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(dich, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for p in sorted(thu_muc.rglob("*")):
            if p.is_file():
                zi = zipfile.ZipInfo(f"{thu_muc.name}/{p.relative_to(thu_muc).as_posix()}", MOC_ZIP)
                zi.compress_type = zipfile.ZIP_DEFLATED
                zi.external_attr = 0o644 << 16
                z.writestr(zi, p.read_bytes())
    return sha256_file(dich)


def chep_ma_nguon(goc: Path, dich: Path, scripts: Sequence[str]) -> list[str]:
    """Chép src/**/*.py, src/**/*.sql, các script được nêu và config.yaml (bỏ __pycache__). Trả danh sách đường dẫn đã chép."""
    da = []
    for p in sorted((goc / "src").rglob("*")):
        if p.is_file() and p.suffix in (".py", ".sql") and "__pycache__" not in p.parts:
            da.append(p.relative_to(goc).as_posix())
    da += [f"scripts/{s}" for s in scripts] + ["config.yaml"]
    for r in da:
        q = dich / r
        q.parent.mkdir(parents=True, exist_ok=True)
        q.write_bytes((goc / r).read_bytes())
    return da
