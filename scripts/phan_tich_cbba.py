"""Phân tích MÔ TẢ kết quả đo mẫu con cbba (kế hoạch V3, mục «Phân tích đăng ký trước»). Chỉ đọc kết quả đã có, không gọi mô hình.

  python scripts/phan_tich_cbba.py --goi inbox/kaggle_cbba/lexo_do_ban_an_cbba --ket-qua <thư mục có C0.jsonl, L.jsonl> [--tap test]

Đầu vào: gói đo (ban_an_do.json, cau_hinh.json) và thư mục kết quả của scripts/do_ban_an.py (C0.jsonl, L.jsonl, ...). A3 / A5 (truy hồi thẳng,
hiển thị top 3 / top 5) tính lại từ ứng viên đã xếp hạng trong gói, với chế độ ứng viên của cau_hinh.json (hoặc của file chốt nếu có --chot).
Đầu ra: <ket-qua>/phan_tich.md (cũng in ra màn hình):
  1. tìm đủ / khớp đúng / bao phủ / chính xác của từng cấu hình, khoảng tin cậy Wilson 95%;
  2. so sánh cặp L với C0, A5, A3 trên «tìm đủ» và «khớp đúng»: số vụ khác nhau, thắng / thua, p McNemar chính xác, khoảng tin cậy 95% của hiệu
     (bootstrap theo vụ, hạt 2026, 2.000 lần lấy mẫu lại);
  3. «tìm đủ» theo nhóm: cấp, số Điều đáp án, tần suất Điều hiếm nhất trong tập học, Điều chưa gặp ở tập học, độ dài sự việc gốc, năm;
  4. trung bình vĩ mô theo Điều (mỗi Điều một phiếu): Điều có >= 5 vụ test và mọi Điều;
  5. vận hành: lỗi, vụ có thể bị cắt, khối think, giây mỗi vụ.
Vụ lỗi (không đọc được câu trả lời) tính là không tìm đủ, như scripts/do_ban_an.py. Cấu hình thiếu vụ được ghi rõ «CHƯA ĐỦ»; so sánh cặp chỉ trên vụ chung.
Không có phép kiểm nào ở đây dùng để chọn mô hình: chỉ báo cáo.
"""
from __future__ import annotations

import argparse
import json
import math
import random
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ban_an import chon_dieu as cd  # noqa: E402

SEED = 2026
SO_LAN_LAY_MAU = 2000
MUC_VI_MO = 5                                  # trung bình vĩ mô: Điều có từ bấy nhiêu vụ test
CAU_HINH_MAC_DINH = ("A3", "A5", "C0", "L")
SO_SANH = (("L", "C0"), ("L", "A5"), ("L", "A3"))
NHOM_TAN_SUAT = (("0 (chưa gặp)", 0, 0), ("1–9", 1, 9), ("10–29", 10, 29), ("≥30", 30, 10 ** 9))


# --------------------------------------------------------------------------------------------------------------------
# Thống kê
# --------------------------------------------------------------------------------------------------------------------


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return 0.0, 0.0
    p = k / n
    mau = 1 + z * z / n
    tam = (p + z * z / (2 * n)) / mau
    nua = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / mau
    return max(0.0, tam - nua), min(1.0, tam + nua)


def mcnemar_p(thang: int, thua: int) -> float:
    """p chính xác hai phía của kiểm cặp McNemar (giả thuyết 0: thắng / thua cân bằng)."""
    n = thang + thua
    if n == 0:
        return 1.0
    k = max(thang, thua)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n)


def khoang_hieu(hieu: Sequence[int], seed: int = SEED, so_lan: int = SO_LAN_LAY_MAU) -> tuple[float, float, float]:
    """(hiệu trung bình, cận dưới, cận trên 95%) của hiệu cặp theo vụ, bootstrap phân vị."""
    n = len(hieu)
    if n == 0:
        return 0.0, 0.0, 0.0
    rng = random.Random(seed)
    tb = sorted(sum(rng.choices(hieu, k=n)) / n for _ in range(so_lan))
    return sum(hieu) / n, tb[int(0.025 * so_lan)], tb[min(so_lan - 1, int(0.975 * so_lan))]


# --------------------------------------------------------------------------------------------------------------------
# Nạp
# --------------------------------------------------------------------------------------------------------------------


def doc_jsonl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []


def hang_truy_hoi(mau: Sequence[dict], che_do: str, k: int) -> list[dict]:
    """Kết quả cấu hình A_k tính từ ứng viên đã xếp hạng, cùng dạng một dòng của C0.jsonl / L.jsonl."""
    return [{"id": x["id"], "dieu": x["dieu"], "hien_thi": x["xep_hang"][che_do][:k], "loi": None,
             "cham": cd.cham_chon(x["dieu"], x["xep_hang"][che_do][:k])} for x in mau]


def nap_cau_hinh(ten: str, mau: Sequence[dict], che_do: str, ket_qua: Path) -> list[dict]:
    if ten in ("A3", "A5"):
        return hang_truy_hoi(mau, che_do, int(ten[1:]))
    ids = {x["id"] for x in mau}
    return [r for r in doc_jsonl(ket_qua / f"{ten}.jsonl") if r["id"] in ids]


# --------------------------------------------------------------------------------------------------------------------
# Bảng
# --------------------------------------------------------------------------------------------------------------------


def phan_tram(k: int, n: int) -> str:
    lo, hi = wilson(k, n)
    return f"{k}/{n} ({k / n:.1%}; {lo:.1%}–{hi:.1%})" if n else "–"


def bang_tong(cau_hinh: dict[str, list[dict]], n_mau: int) -> list[str]:
    d = ["| cấu hình | số vụ | tìm đủ (95% CI) | khớp đúng (95% CI) | bao phủ | chính xác | Điều hiển thị TB | lỗi | có thể bị cắt | think | giây/vụ |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for ten, rows in cau_hinh.items():
        n = len(rows)
        if not n:
            d.append(f"| {ten} | 0 | – | – | – | – | – | – | – | – | – |")
            continue
        tb = lambda t: sum(r["cham"][t] for r in rows) / n                                     # noqa: E731
        ghi_chu = "" if n == n_mau else f" **CHƯA ĐỦ ({n}/{n_mau})**"
        d.append(f"| {ten}{ghi_chu} | {n} | {phan_tram(int(sum(r['cham']['tim_du'] for r in rows)), n)} | "
                 f"{phan_tram(int(sum(r['cham']['khop_dung'] for r in rows)), n)} | {tb('bao_phu'):.1%} | {tb('chinh_xac'):.1%} | {tb('so_hien_thi'):.1f} | "
                 f"{sum(1 for r in rows if r.get('loi'))} | {sum(1 for r in rows if r.get('co_the_bi_cat'))} | {sum(1 for r in rows if r.get('co_think'))} | "
                 f"{sum(r.get('giay') or 0 for r in rows) / n:.1f} |")
    return d


def bang_cap(cau_hinh: dict[str, list[dict]], a: str, b: str) -> list[str]:
    ta = {r["id"]: r["cham"] for r in cau_hinh.get(a, [])}
    tb = {r["id"]: r["cham"] for r in cau_hinh.get(b, [])}
    chung = sorted(ta.keys() & tb.keys())
    d = []
    for chi_so, nhan in (("tim_du", "tìm đủ"), ("khop_dung", "khớp đúng")):
        thang = sum(1 for i in chung if ta[i][chi_so] > tb[i][chi_so])
        thua = sum(1 for i in chung if ta[i][chi_so] < tb[i][chi_so])
        tb_hieu, lo, hi = khoang_hieu([int(ta[i][chi_so]) - int(tb[i][chi_so]) for i in chung])
        d.append(f"| {a} so với {b} | {nhan} | {len(chung)} | {thang + thua} | {thang} / {thua} | {tb_hieu:+.1%} ({lo:+.1%}…{hi:+.1%}) | {mcnemar_p(thang, thua):.4f} |")
    return d


def bang_nhom(cau_hinh: dict[str, list[dict]], mau: Sequence[dict], ten_nhom: str, khoa: Callable[[dict], str], thu_tu: Sequence[str]) -> list[str]:
    ten = list(cau_hinh)
    theo_id = {x["id"]: x for x in mau}
    d = [f"| {ten_nhom} | số vụ | " + " | ".join(f"tìm đủ {t}" for t in ten) + " |", "|---|---|" + "---|" * len(ten)]
    for g in thu_tu:
        ids = {x["id"] for x in mau if khoa(x) == g}
        if not ids:
            continue
        o = []
        for t in ten:
            rs = [r for r in cau_hinh[t] if r["id"] in ids]
            o.append(f"{int(sum(r['cham']['tim_du'] for r in rs))}/{len(rs)} ({sum(r['cham']['tim_du'] for r in rs) / len(rs):.0%})" if rs else "–")
        d.append(f"| {g} | {len(ids)} | " + " | ".join(o) + " |")
    return d if len(d) > 2 else []


def vi_mo_theo_dieu(rows: Sequence[dict], toi_thieu: int = 1) -> tuple[float, int]:
    """(trung bình theo Điều của «Điều d có được hiển thị khi d là đáp án», số Điều tính) trên các Điều có >= toi_thieu vụ."""
    co: dict[str, list[int]] = {}
    for r in rows:
        hien = set(r["hien_thi"])
        for d in r["dieu"]:
            co.setdefault(d, []).append(int(d in hien))
    xet = {d: v for d, v in co.items() if len(v) >= toi_thieu}
    if not xet:
        return 0.0, 0
    return sum(sum(v) / len(v) for v in xet.values()) / len(xet), len(xet)


def so_dieu_hon_kem(a: Sequence[dict], b: Sequence[dict], toi_thieu: int = MUC_VI_MO) -> tuple[int, int, int]:
    """(số Điều mà a có tỉ lệ được hiển thị cao hơn b, thấp hơn b, bằng nhau) trên các Điều có >= toi_thieu vụ chung."""
    chung = {r["id"] for r in a} & {r["id"] for r in b}

    def ty_le(rows):
        co: dict[str, list[int]] = {}
        for r in rows:
            if r["id"] in chung:
                for d in r["dieu"]:
                    co.setdefault(d, []).append(int(d in set(r["hien_thi"])))
        return {d: sum(v) / len(v) for d, v in co.items() if len(v) >= toi_thieu}

    ta, tb = ty_le(a), ty_le(b)
    ds = ta.keys() & tb.keys()
    return sum(ta[d] > tb[d] for d in ds), sum(ta[d] < tb[d] for d in ds), sum(ta[d] == tb[d] for d in ds)


def nhom_tan_suat(x: dict) -> str:
    t = x.get("tan_suat_dieu_hoc")
    if t is None:
        return "?"
    return next(ten for ten, lo, hi in NHOM_TAN_SUAT if lo <= t <= hi)


def nhom_do_dai(x: dict) -> str:
    n = x.get("so_tu_goc")
    return "?" if n is None else "≤500" if n <= 500 else "501–1000" if n <= 1000 else ">1000"


def bao_cao(mau: Sequence[dict], cau_hinh: dict[str, list[dict]], tieu_de: str) -> str:
    n = len(mau)
    d = [f"# Phân tích mô tả — {tieu_de}", "", f"{n} vụ trong gói đo. Vụ lỗi tính là không tìm đủ. Khoảng tin cậy chỉ để mô tả độ bất định, không dùng để chọn mô hình.", "",
         "## 1. Tổng quan", ""] + bang_tong(cau_hinh, n)
    d += ["", "## 2. So sánh cặp (các vụ chung)", "", "| so sánh | chỉ số | vụ chung | vụ khác nhau | thắng / thua | hiệu (95% CI) | p McNemar |", "|---|---|---|---|---|---|---|"]
    for a, b in SO_SANH:
        if a in cau_hinh and b in cau_hinh:
            d += bang_cap(cau_hinh, a, b)
    d += ["", "## 3. Tìm đủ theo nhóm", ""]
    nhom = [("cấp xét xử", lambda x: x.get("cap") or "?", ("so_tham", "phuc_tham", "giam_doc_tham", "tai_tham", "khong_ro")),
            ("số Điều đáp án", lambda x: "1" if len(x["dieu"]) == 1 else "≥2", ("1", "≥2")),
            ("tần suất Điều hiếm nhất trong tập học", nhom_tan_suat, [g[0] for g in NHOM_TAN_SUAT]),
            ("Điều chưa gặp ở tập học", lambda x: "có" if x.get("dieu_chua_gap") else "không", ("có", "không")),
            ("độ dài sự việc gốc (từ)", nhom_do_dai, ("≤500", "501–1000", ">1000", "?")),
            ("năm bản án", lambda x: str(x.get("nam") or "?"), tuple(str(y) for y in range(2018, 2031)) + ("?",))]
    for ten, khoa, thu_tu in nhom:
        b = bang_nhom(cau_hinh, mau, ten, khoa, thu_tu)
        if b:
            d += b + [""]
    d += ["## 4. Trung bình vĩ mô theo Điều (mỗi Điều một phiếu)", "", f"| cấu hình | Điều có >= {MUC_VI_MO} vụ | trung bình | mọi Điều | trung bình |", "|---|---|---|---|---|"]
    for ten, rows in cau_hinh.items():
        v5, n5 = vi_mo_theo_dieu(rows, MUC_VI_MO)
        v1, n1 = vi_mo_theo_dieu(rows, 1)
        d.append(f"| {ten} | {n5} | {v5:.1%} | {n1} | {v1:.1%} |")
    for a, b in SO_SANH[:1]:
        if a in cau_hinh and b in cau_hinh:
            hon, kem, bang = so_dieu_hon_kem(cau_hinh[a], cau_hinh[b])
            d += ["", f"{a} so với {b} theo từng Điều (>= {MUC_VI_MO} vụ): {a} cao hơn ở {hon} Điều, thấp hơn ở {kem}, bằng ở {bang}."]
    return "\n".join(d) + "\n"


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--goi", type=Path, required=True, help="thư mục gói đo (ban_an_do.json, cau_hinh.json)")
    ap.add_argument("--ket-qua", type=Path, required=True, help="thư mục kết quả của do_ban_an.py (C0.jsonl, L.jsonl, ...)")
    ap.add_argument("--tap", default="test", choices=("test", "dev"))
    ap.add_argument("--cau-hinh", default=",".join(CAU_HINH_MAC_DINH), help="cách nhau dấu phẩy; A3, A5, C0, L, HOP, LOC, LOC0")
    ap.add_argument("--chot", type=Path, default=None, help="cau_hinh_chot.json (lấy chế độ ứng viên cho A3 / A5)")
    ap.add_argument("--ra", type=Path, default=None)
    a = ap.parse_args()
    try:
        du_lieu = json.loads((a.goi / "ban_an_do.json").read_text(encoding="utf-8"))
        ch = json.loads((a.goi / "cau_hinh.json").read_text(encoding="utf-8"))
        che_do = json.loads(a.chot.read_text(encoding="utf-8"))["che_do_uv"] if a.chot else ch["ung_vien"]["che_do"]
    except (OSError, ValueError, KeyError) as e:
        sys.exit(f"LỖI: không đọc được gói đo / file chốt: {e}")
    mau = [x for x in du_lieu["mau"] if x["tap"] == a.tap]
    if not mau:
        sys.exit(f"LỖI: gói không có vụ nào thuộc tập {a.tap}")
    cau_hinh = {}
    for t in (c.strip() for c in a.cau_hinh.split(",") if c.strip()):
        rows = nap_cau_hinh(t, mau, che_do, a.ket_qua)
        if rows or t in ("A3", "A5"):
            cau_hinh[t] = rows
        else:
            print(f"BỎ QUA {t}: không có {a.ket_qua / (t + '.jsonl')}")
    if not cau_hinh:
        sys.exit("LỖI: không có cấu hình nào để phân tích")
    txt = bao_cao(mau, cau_hinh, f"tập {a.tap}, ứng viên {che_do}")
    ra = a.ra or a.ket_qua / "phan_tich.md"
    ra.write_text(txt, encoding="utf-8", newline="\n")
    print(txt)
    print(f"Đã ghi {ra}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
