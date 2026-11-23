"""Sinh 3 notebook Kaggle bản V3 (mẫu con cbba) từ 3 notebook V2 đã sinh ở kaggle/, KHÔNG sửa scripts/tao_notebook_kaggle.py.

  python scripts/tao_notebook_cbba.py                 # EPOCH = 1
  python scripts/tao_notebook_cbba.py --epoch 2

Đọc kaggle/lexo_hoc_chon_dieu.ipynb, lexo_gop_gguf.ipynb, lexo_do_ban_an.ipynb (chạy scripts/tao_notebook_kaggle.py trước nếu thiếu / cũ) và ghi
kaggle/lexo_hoc_cbba.ipynb, lexo_gop_gguf_cbba.ipynb, lexo_do_ban_an_cbba.ipynb. Mỗi chỗ thay có số lần xuất hiện dự kiến; khác đi (V2 đổi
mà script này chưa theo kịp) thì dừng, không ghi file nào.

Khác V2: tên mô hình (`...-chon-dieu-cbba-v1`), `EPOCH` (V2 đặt 3 cho ~440 mẫu; với mẫu con cbba ngân sách 9 giờ T4 chỉ đủ khoảng một lượt,
nên V3 ghi trước EPOCH trong kế hoạch và không đổi theo điểm), bỏ Vòng 1 (gói cbba không có tập train90) và bỏ B0 / B1 khỏi lượt test.
Mọi siêu tham số khác, thư viện ghim, cổng G0–G4 và quy tắc cấm giữ nguyên như V2.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
KAGGLE = ROOT / "kaggle"
TEN_CU, TEN_MOI = "chon-dieu-v1", "chon-dieu-cbba-v1"

# (cũ, mới, số lần xuất hiện dự kiến trong cả notebook)
THAY_HOC = [
    ("MICRO_BS, GRAD_ACC, EPOCH = 1, 8, 3", "MICRO_BS, GRAD_ACC, EPOCH = 1, 8, @EPOCH@", 1),
    ('TEN = "lexo-qwen3-8b-chon-dieu-v1"', 'TEN = "lexo-qwen3-8b-chon-dieu-cbba-v1"', 1),
    ('DU_LIEU = "train"         # "train": vụ bản án học + 368 tổng hợp | "train_tong_hop": chỉ 368 tổng hợp (Vòng 3, C1)',
     'DU_LIEU = "train"         # gói cbba chỉ có "train" (mẫu con cbba); không có mẫu tổng hợp', 1),
    ("chỉ Dataset private từ `lexo_hoc_chon_dieu.zip`", "chỉ Dataset private từ `lexo_hoc_chon_dieu_cbba.zip`", 1),
    ("không dòng nào trùng mã hay băm sự việc của 99 vụ test", "không dòng nào trùng mã hay băm sự việc của các vụ test", 1),
]
THAY_GOP = [
    ('TEN = "lexo-qwen3-8b-chon-dieu-v1"', 'TEN = "lexo-qwen3-8b-chon-dieu-cbba-v1"', 1),
]
THAY_DO = [
    ("CHAY_VONG_1 = True        # Vòng 1: A, B0, B1, C0 trên 90 vụ train (hoc + dev)",
     "CHAY_VONG_1 = False       # V3: gói cbba không có tập train90 nên không có Vòng 1 (đừng bật)", 1),
    ('MO_HINH_LORA = "qwen3-8b-lexo-chon-dieu-v1"', 'MO_HINH_LORA = "qwen3-8b-lexo-chon-dieu-cbba-v1"', 1),
    ('MAU_GGUF_LORA = "*chon-dieu-v1*q4_k_m*.gguf"', 'MAU_GGUF_LORA = "*chon-dieu-cbba-v1*q4_k_m*.gguf"', 1),
    ("tên file chứa `chon-dieu-v1` và `q4_k_m`", "tên file chứa `chon-dieu-cbba-v1` và `q4_k_m`", 1),
    ("`lexo_do_ban_an.zip` | luôn", "`lexo_do_ban_an_cbba.zip` | luôn", 1),
    ("**Tập test (99 vụ) chỉ chạy một lần", "**Tập test chỉ chạy một lần", 1),
    ("## 8. Lượt test (99 vụ): một lần duy nhất", "## 8. Lượt test: một lần duy nhất", 1),
    ("đã chốt ở chat gốc dựa trên 90 vụ train, dev và val loss.", "đã chốt ở chat gốc dựa trên val loss, K chọn trên học + dev và cổng kỹ thuật G3 / G4.", 1),
    ('    "cau_hinh": ["A", "B0", "B1", "C0", "L"],   # mọi cấu hình trong cùng một lượt',
     '    "cau_hinh": ["A", "C0", "L"],               # V3: truy hồi, mô hình gốc, LoRA cbba; B0 / B1 (tách hành vi) quá chậm với cỡ test này', 1),
    ('    "tot_nhat_cu": "B1",                        # cấu hình cũ tốt nhất trên 90 vụ train: A3, A5, B0 hoặc B1\n', "", 1),
]

LUU_Y = {
    "hoc": """# V3 — học trên mẫu con cbba

Bản V3 của `lexo_hoc_chon_dieu.ipynb` (sinh bởi `scripts/tao_notebook_cbba.py`). Khác V2 đúng ba điểm: gói học là `lexo_hoc_chon_dieu_cbba.zip`
(tập học theo trần mỗi Điều + dev), `TEN = "lexo-qwen3-8b-chon-dieu-cbba-v1"`, và `EPOCH = @EPOCH@` (ghi trong `kaggle/KE_HOACH_KAGGLE_V3.md`, không đổi theo điểm).
Với một epoch chỉ có một checkpoint (cuối epoch), nên «chọn theo val loss thấp nhất» chỉ còn điểm đó; val loss vẫn đo ở đầu, giữa và cuối epoch.
Mục «Vòng 3» bên dưới (C1, C2) không áp dụng cho V3. Chỉ gắn MỘT gói học vào notebook.""",
    "gop": """# V3 — gộp LoRA cbba thành GGUF

Bản V3 của `lexo_gop_gguf.ipynb`: chỉ khác `TEN` (`lexo-qwen3-8b-chon-dieu-cbba-v1`, trùng notebook học).""",
    "do": """# V3 — đo trên mẫu con cbba

Bản V3 của `lexo_do_ban_an.ipynb`. Khác V2: gói đo là `lexo_do_ban_an_cbba.zip` (vụ test + một phần dev), `MO_HINH_LORA` / `MAU_GGUF_LORA` theo
`chon-dieu-cbba-v1`, `CHAY_VONG_1 = False` (gói không có train90), và lượt test chỉ gồm A, C0, L (B0 / B1 tách hành vi quá chậm với cỡ test này).
Cỡ test `N` có thể phải cắt ngắn theo tốc độ Ollama đo ở G4 (quy tắc trong `kaggle/KE_HOACH_KAGGLE_V3.md`): đóng gói lại với `--so-test` nhỏ hơn
cho cùng danh sách test, không tự ý chạy một phần.""",
}


class ThayError(RuntimeError):
    pass


def _dong(s: str) -> list[str]:
    s = s.strip("\n")
    d = s.split("\n")
    return [x + "\n" for x in d[:-1]] + [d[-1]]


def ap_dung(nb: dict, thay: list[tuple[str, str, int]], luu_y: str, ten: str, **tham_so) -> dict:
    """Bản V3 của nb: thay chữ (kiểm số lần), thêm ô ghi chú ở đầu, đánh lại id ô."""
    tong: Counter = Counter()
    cells = []
    for c in nb["cells"]:
        s = "".join(c["source"])
        for i, (cu, moi, _) in enumerate(thay):
            k = s.count(cu)
            if k:
                s = s.replace(cu, moi.replace("@EPOCH@", str(tham_so["epoch"])))
                tong[i] += k
        c2 = dict(c)
        c2["source"] = _dong(s)
        cells.append(c2)
    sai = [f"{ten}: {thay[i][0][:60]!r} xuất hiện {tong[i]} lần, dự kiến {thay[i][2]}" for i in range(len(thay)) if tong[i] != thay[i][2]]
    if sai:
        raise ThayError("; ".join(sai))
    cells.insert(0, {"cell_type": "markdown", "metadata": {}, "source": _dong(luu_y.replace("@EPOCH@", str(tham_so["epoch"])))})
    for i, c in enumerate(cells):
        c["id"] = f"o{i:02d}"
    return dict(nb, cells=cells)


def sinh(kaggle: Path, epoch: int) -> dict[str, dict]:
    ra = {}
    for nguon, dich, thay, khoa in (("lexo_hoc_chon_dieu.ipynb", "lexo_hoc_cbba.ipynb", THAY_HOC, "hoc"),
                                    ("lexo_gop_gguf.ipynb", "lexo_gop_gguf_cbba.ipynb", THAY_GOP, "gop"),
                                    ("lexo_do_ban_an.ipynb", "lexo_do_ban_an_cbba.ipynb", THAY_DO, "do")):
        p = kaggle / nguon
        if not p.exists():
            raise ThayError(f"không thấy {p}: chạy scripts/tao_notebook_kaggle.py trước")
        ra[dich] = ap_dung(json.loads(p.read_text(encoding="utf-8")), thay, LUU_Y[khoa], nguon, epoch=epoch)
    return ra


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--epoch", type=int, default=1)
    ap.add_argument("--kaggle", type=Path, default=KAGGLE)
    a = ap.parse_args()
    if a.epoch < 1:
        sys.exit("LỖI: --epoch phải >= 1")
    try:
        nbs = sinh(a.kaggle, a.epoch)
    except ThayError as e:
        sys.exit(f"LỖI: {e}")
    for ten, nb in nbs.items():
        (a.kaggle / ten).write_text(json.dumps(nb, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        print("ghi", a.kaggle / ten)
    return 0


if __name__ == "__main__":
    sys.exit(main())
