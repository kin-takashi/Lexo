"""So một cách tách hành vi (của mô hình) với cách tách «chuẩn» do Claude làm MÙ (không thấy đáp án Điều), nhiều lần.

Vì sao cần: các số «tìm đủ» hiện nay đo khoảng cách tới đáp án Điều do Claude soạn, còn chất lượng khâu TÁCH thì chưa có chuẩn riêng.
Hàng «tách lý tưởng» là hành vi viết tay SAU khi đã biết đáp án (số hành vi = số Điều theo cách soạn) nên không phải chuẩn khách quan.

Cách đo (không cần mô hình ngôn ngữ làm giám khảo):
  - đồng số hành vi: số hành vi của mô hình = số hành vi của bản chuẩn (1 hoặc 0 mỗi tình huống).
  - ghép hành vi: ghép 1-1 tối ưu giữa hành vi hai bên theo độ tương đồng chữ (hoặc vector); `ghep` = tổng độ tương đồng của phép ghép / max(số hành vi hai bên),
    không cần ngưỡng, phạt cả tách thừa lẫn tách thiếu. `f1` = F1 tính trên các cặp ghép có độ tương đồng >= ngưỡng (phụ; ngưỡng chưa hiệu chỉnh).
  - TRẦN: cùng các số đo nhưng giữa hai bản chuẩn khác nhau (Claude với Claude). Mô hình không thể kỳ vọng vượt mức này vì cùng một tình huống
    có nhiều cách tách hợp lệ. «Gần chuẩn» = số đo của mô hình xấp xỉ trần.
  - Khoảng tin cậy bootstrap theo cặp từng tình huống cho hiệu (mô hình - trần).

Tiền tố tên tội («Hiếp dâm: ...») được bỏ trước khi so (hai bên có thể viết hoặc không viết).
"""
from __future__ import annotations

import random
import re
import unicodedata
from collections.abc import Callable, Mapping, Sequence

from src.index.tach_hanh_vi import bo_tien_to

TuongDong = Callable[[str, str], float]
KHOA = ("bang_so", "lech", "p", "r", "f1", "ghep")
TOI_DA_DP = 12                 # ghép tối ưu chính xác bằng quy hoạch động khi bên nhỏ có <= 12 hành vi; quá thì ghép tham lam
_TU = re.compile(r"\w+", re.U)
_DUNG = frozenset("và của để trong cho là có một các những được bị khi với rồi đã sau nhưng hoặc thì mà nên do bằng từ ra vào lên".split())


def am_tiet(s: str) -> list[str]:
    """Âm tiết chữ thường (bỏ tiền tố tên tội, bỏ từ nối thông dụng)."""
    ts = _TU.findall(unicodedata.normalize("NFC", bo_tien_to(s)).lower())
    return [t for t in ts if t not in _DUNG]


def tuong_dong_chu(a: str, b: str) -> float:
    """Dice trên tập âm tiết và cặp âm tiết liền nhau; 0..1; không cần mô hình, chạy offline."""
    ta, tb = am_tiet(a), am_tiet(b)
    ga, gb = set(ta) | set(zip(ta, ta[1:])), set(tb) | set(zip(tb, tb[1:]))
    if not ga or not gb:
        return 0.0
    return 2 * len(ga & gb) / (len(ga) + len(gb))


def tuong_dong_vec(embed: Callable[[list[str]], list[list[float]]], lo: int = 32) -> TuongDong:
    """Độ tương đồng cosine giữa hai đoạn qua một hàm nhúng (ví dụ bge-m3). Hàm trả về có thuộc tính .nap(danh_sach_chu) để nhúng trước theo lô."""
    cache: dict[str, list[float]] = {}

    def chuan_hoa(v: list[float]) -> list[float]:
        n = sum(x * x for x in v) ** 0.5 or 1.0
        return [x / n for x in v]

    def nap(chu: Sequence[str]) -> None:
        can = [k for k in dict.fromkeys(bo_tien_to(c) for c in chu) if k not in cache]
        for i in range(0, len(can), lo):
            for k, v in zip(can[i:i + lo], embed(can[i:i + lo])):
                cache[k] = chuan_hoa(v)

    def td(a: str, b: str) -> float:
        nap([a, b])
        return max(0.0, sum(x * y for x, y in zip(cache[bo_tien_to(a)], cache[bo_tien_to(b)])))

    td.nap = nap  # type: ignore[attr-defined]
    return td


def _ghep_tham(s: Sequence[Sequence[float]]) -> tuple[float, list[tuple[int, int]]]:
    cap_ung = sorted(((s[i][j], i, j) for i in range(len(s)) for j in range(len(s[0]))), key=lambda t: (-t[0], t[1], t[2]))
    dung_h, dung_c, cap, tong = set(), set(), [], 0.0
    for v, i, j in cap_ung:
        if i not in dung_h and j not in dung_c:
            dung_h.add(i), dung_c.add(j), cap.append((i, j))
            tong += v
    return tong, sorted(cap)


def ghep_toi_uu(s: Sequence[Sequence[float]]) -> tuple[float, list[tuple[int, int]]]:
    """Ghép 1-1 giữa hàng và cột sao cho tổng độ tương đồng lớn nhất (độ tương đồng >= 0, nên bên nhỏ được ghép hết). Trả (tổng, [(hàng, cột)])."""
    n = len(s)
    m = len(s[0]) if n else 0
    if n == 0 or m == 0:
        return 0.0, []
    if n > m:
        tong, cap = ghep_toi_uu([list(c) for c in zip(*s)])
        return tong, sorted((i, j) for j, i in cap)
    if n > TOI_DA_DP:
        return _ghep_tham(s)
    tot: dict[int, tuple[float, tuple[tuple[int, int], ...]]] = {0: (0.0, ())}
    for i in range(n):
        moi: dict[int, tuple[float, tuple[tuple[int, int], ...]]] = {}
        for mask, (v, cap) in tot.items():
            for j in range(m):
                if mask >> j & 1:
                    continue
                nm, nv = mask | 1 << j, v + s[i][j]
                if nm not in moi or nv > moi[nm][0] + 1e-12:
                    moi[nm] = (nv, cap + ((i, j),))
        tot = moi
    v, cap = max(tot.values(), key=lambda t: t[0])
    return v, list(cap)


def so_sanh(mo_hinh: Sequence[str], chuan: Sequence[str], td: TuongDong, tau: float) -> dict[str, float]:
    """So MỘT tình huống: hành vi của mô hình với hành vi của một bản chuẩn."""
    if not mo_hinh or not chuan:
        raise ValueError("cần ít nhất một hành vi ở cả hai bên")
    s = [[td(a, b) for b in chuan] for a in mo_hinh]
    tong, cap = ghep_toi_uu(s)
    tp = sum(1 for i, j in cap if s[i][j] >= tau)
    p, r = tp / len(mo_hinh), tp / len(chuan)
    return {"bang_so": float(len(mo_hinh) == len(chuan)), "lech": float(len(mo_hinh) - len(chuan)), "p": p, "r": r,
            "f1": (2 * p * r / (p + r)) if tp else 0.0, "ghep": tong / max(len(mo_hinh), len(chuan))}


def trung_binh(ds: Sequence[Mapping[str, float]]) -> dict[str, float]:
    if not ds:
        raise ValueError("không có số đo nào để lấy trung bình")
    return {k: sum(d[k] for d in ds) / len(ds) for k in ds[0]}


def so_voi_cac_chuan(mo_hinh: Mapping[str, Sequence[str]], chuan: Sequence[Mapping[str, Sequence[str]]], ids: Sequence[str],
                     td: TuongDong, tau: float) -> dict[str, dict[str, float]]:
    """Từng id: trung bình số đo khi so mô hình với TỪNG bản chuẩn."""
    return {i: trung_binh([so_sanh(mo_hinh[i], c[i], td, tau) for c in chuan]) for i in ids}


def tran_chuan(chuan: Sequence[Mapping[str, Sequence[str]]], ids: Sequence[str], td: TuongDong, tau: float) -> dict[str, dict[str, float]]:
    """Từng id: trung bình số đo khi so MỖI bản chuẩn với MỌI bản chuẩn khác (cặp có thứ tự). Cần >= 2 bản chuẩn."""
    if len(chuan) < 2:
        raise ValueError("cần ít nhất 2 bản chuẩn để tính trần")
    return {i: trung_binh([so_sanh(a[i], b[i], td, tau) for x, a in enumerate(chuan) for y, b in enumerate(chuan) if x != y]) for i in ids}


def tong_hop(theo_id: Mapping[str, Mapping[str, float]]) -> dict[str, float]:
    """Trung bình qua các tình huống (mỗi tình huống nặng như nhau)."""
    return trung_binh(list(theo_id.values()))


def boot_hieu(a: Sequence[float], b: Sequence[float], *, hat: int = 42, so_lan: int = 2000, do_tin: float = 0.95) -> tuple[float, float, float]:
    """Hiệu trung bình a - b theo cặp từng tình huống; khoảng tin cậy bootstrap (percentile), xác định theo `hat`. Trả (hiệu, thấp, cao)."""
    if len(a) != len(b) or not a:
        raise ValueError("hai dãy phải cùng độ dài và không rỗng")
    d = [x - y for x, y in zip(a, b)]
    rng = random.Random(hat)
    n = len(d)
    mau = sorted(sum(d[rng.randrange(n)] for _ in range(n)) / n for _ in range(so_lan))
    lech = (1 - do_tin) / 2
    return sum(d) / n, mau[int(lech * so_lan)], mau[min(so_lan - 1, int((1 - lech) * so_lan))]


def doc_tach(d: object) -> dict[str, list[str]]:
    """Đọc file tách: {id: [hành vi, ...]} (đầu ra của scripts/tach_hanh_vi.py) hoặc {id: {"hanh_vi": [...]}} (đầu ra dán từ phiên Claude mù)."""
    if not isinstance(d, dict) or not d:
        raise ValueError("file tách phải là JSON {id: [hành vi...]} hoặc {id: {\"hanh_vi\": [...]}}")
    ra: dict[str, list[str]] = {}
    for k, v in d.items():
        if isinstance(v, dict):
            v = v.get("hanh_vi")
        if not (isinstance(v, list) and v and all(isinstance(s, str) and s.strip() for s in v)):
            raise ValueError(f"{k}: cần danh sách hành vi không rỗng, mỗi hành vi là chuỗi không rỗng")
        ra[str(k)] = [s.strip() for s in v]
    return ra
