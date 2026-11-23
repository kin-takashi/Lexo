"""Chấm «tìm đủ» cho các câu loai = nhieu_dieu: một tình huống có nhiều hành vi, mỗi hành vi một Điều, phải tìm ĐỦ cả tập Điều.

Vì sao cần số đo riêng: Hit@k của scripts/danh_gia.py chỉ hỏi «có Điều nào trong danh sách chấp nhận nằm trong top k không», trúng một Điều là đủ.
Với tình huống nhiều hành vi, trúng một Điều rồi bỏ sót Điều còn lại là kết quả SAI đối với người dùng (họ tưởng đã thấy hết).

Dữ liệu vào là «các hành vi được tách ra», mỗi hành vi kèm danh sách Điều xếp hạng:
    hanh_vi = [["173", "172", "171"], ["178", "134", "318"]]        # hai hành vi, mỗi hành vi một danh sách Điều xếp hạng giảm dần
Mỗi hành vi chỉ hiển thị m Điều đầu (m = 3 là mặc định của công cụ). Tập «hiển thị» là hợp các Điều đó. Các số đo:

  bao_phu     phần Điều đáp án nằm trong tập hiển thị (recall mức Điều).
  tim_du      1 nếu MỌI Điều đáp án nằm trong tập hiển thị, ngược lại 0 (đây là số đo chính).
  chinh_xac   phần tập hiển thị là Điều đáp án (precision mức Điều); tập hiển thị càng gọn càng dễ đọc.
  hanh_vi_co_dap_an  phần hành vi mà m Điều đầu có chứa ít nhất một Điều đáp án (hành vi tách thừa thì không có).
  dung_so_hanh_vi    1 nếu số hành vi tách ra bằng số Điều đáp án (quy ước: mỗi hành vi bị xử riêng một Điều; tình tiết tăng nặng không tách).
  so_hien_thi        số Điều hiển thị.

So sánh công bằng: không tách (cả câu là một truy vấn) hiển thị cùng số Điều với bản có tách, xem so_ngan_sach().
"""
from __future__ import annotations

from collections.abc import Sequence


def so_dieu(d: str) -> str:
    """'dieu 173' hoặc 'Điều 173' hoặc '173' -> '173' (chữ thường cho hậu tố như 217a)."""
    return d.strip().lower().replace("điều", "").replace("dieu", "").strip()


def hien_thi(hanh_vi: Sequence[Sequence[str]], m: int = 3) -> list[str]:
    """Tập Điều được hiển thị (hợp m Điều đầu của mỗi hành vi), giữ thứ tự xuất hiện, không lặp."""
    if m < 1:
        raise ValueError("m phải >= 1")
    ra: list[str] = []
    for ds in hanh_vi:
        for d in list(dict.fromkeys(so_dieu(x) for x in ds))[:m]:
            if d not in ra:
                ra.append(d)
    return ra


def cham(dap_an: Sequence[str], hanh_vi: Sequence[Sequence[str]], m: int = 3) -> dict:
    """Chấm MỘT tình huống. dap_an: các số Điều cần tìm đủ (không lặp, ít nhất 1)."""
    vang = list(dict.fromkeys(so_dieu(d) for d in dap_an))
    if not vang:
        raise ValueError("dap_an rỗng")
    hien = hien_thi(hanh_vi, m)
    trung = [d for d in vang if d in hien]
    co = sum(1 for ds in hanh_vi if set(hien_thi([ds], m)) & set(vang))
    return {
        "bao_phu": len(trung) / len(vang),
        "tim_du": float(len(trung) == len(vang)),
        "chinh_xac": len(trung) / len(hien) if hien else 0.0,
        "hanh_vi_co_dap_an": co / len(hanh_vi) if hanh_vi else 0.0,
        "dung_so_hanh_vi": float(len(hanh_vi) == len(vang)),
        "so_hien_thi": len(hien),
        "thieu": [d for d in vang if d not in hien],
    }


def so_ngan_sach(dap_an: Sequence[str], xep_hang: Sequence[str], k: int) -> dict:
    """Mốc «không tách»: cả tình huống là một truy vấn, hiển thị k Điều đầu của danh sách xếp hạng (k thường = số Điều bản có tách hiển thị)."""
    return cham(dap_an, [list(xep_hang)], m=max(1, k))


def tong_hop(ket_qua: Sequence[dict]) -> dict:
    """Trung bình các số đo trên nhiều tình huống (mỗi tình huống nặng như nhau)."""
    if not ket_qua:
        raise ValueError("không có kết quả nào để tổng hợp")
    n = len(ket_qua)
    return {t: sum(r[t] for r in ket_qua) / n
            for t in ("bao_phu", "tim_du", "chinh_xac", "hanh_vi_co_dap_an", "dung_so_hanh_vi", "so_hien_thi")}
