"""Chọn tập học SẠCH và các tập con lồng nhau (50, 100, 200, đủ) từ train/tinh_huong.json.

Sạch: bỏ mẫu mà tập Điều đáp án trùng đúng tập Điều đáp án của một câu nhiều Điều trong bộ đo (mọi tập: dev, kiem_tra, ...).
Chỉ so danh sách Điều đáp án; không đọc, không đưa nội dung câu hỏi của bộ đo vào đâu cả.

Tập con lồng nhau: xếp hạng cả tập sạch một lần (phân tầng theo số hành vi, hạt cố định), rồi lấy k mẫu đầu. Mọi tập nhỏ nằm trọn trong tập lớn
hơn, nên đường cong "số mẫu → kết quả" so sánh được với nhau.
"""
from __future__ import annotations

import random
from collections import defaultdict

TANG_TOI_DA = 4           # 4 hành vi trở lên gộp một tầng


def to_hop_dieu(x: dict) -> set[frozenset[str]]:
    """Các tập Điều mà một mẫu có thể bị coi là trùng: (a) mọi Điều chấp nhận của mọi hành vi, (b) Điều đầu tiên của mỗi hành vi."""
    return {frozenset(d for h in x["hanh_vi"] for d in h["dieu"]), frozenset(h["dieu"][0] for h in x["hanh_vi"])}


def to_hop_bo_do(cau_do: list[dict]) -> set[frozenset[str]]:
    """Tập Điều đáp án của các câu nhiều Điều trong bộ đo (loai = nhieu_dieu)."""
    return {frozenset(c["dieu"]) for c in cau_do if c.get("loai") == "nhieu_dieu"}


def mau_trung(mau: list[dict], cau_do: list[dict]) -> list[str]:
    """Id các mẫu học có tập Điều trùng đúng một câu nhiều Điều của bộ đo."""
    gold = to_hop_bo_do(cau_do)
    return sorted(x["id"] for x in mau if to_hop_dieu(x) & gold)


def xep_hang(mau: list[dict], hat: int = 42) -> list[str]:
    """Id theo thứ tự ưu tiên: k mẫu đầu xấp xỉ giữ đúng tỷ lệ các tầng (số hành vi). Xác định hoàn toàn theo (mau, hat), không phụ thuộc thứ tự đầu vào."""
    nhom: dict[int, list[str]] = defaultdict(list)
    for x in sorted(mau, key=lambda m: m["id"]):
        nhom[min(len(x["hanh_vi"]), TANG_TOI_DA)].append(x["id"])
    khoa: list[tuple[float, str]] = []
    for tang in sorted(nhom):
        ids = nhom[tang]
        rng = random.Random(f"{hat}:{tang}")
        rng.shuffle(ids)
        n = len(ids)
        khoa += [((i + rng.random()) / n, id_) for i, id_ in enumerate(ids)]
    khoa.sort()
    return [id_ for _, id_ in khoa]
