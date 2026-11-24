"""Tập huấn luyện cho bước "tách hành vi": MỘT file nguồn train/tinh_huong.json, tách hẳn khỏi bộ đo eval/bo_cau_hoi.json.

Mỗi mẫu có: id, tinh_huong (đoạn văn đời thường), hanh_vi (danh sách các hành vi / hậu quả có thể bị xử riêng), loai, nguon, trang_thai.
Mỗi phần tử của hanh_vi gồm:
  mo_ta  một câu ngắn, tự đủ nghĩa, nêu các tình tiết quan trọng (số lượng, hậu quả, đối tượng, cách thức); KHÔNG nêu số Điều.
         Đây là đích mà mô hình nhỏ phải học viết ra, đồng thời là câu truy vấn đem đi tìm Điều.
  dieu   các Điều CHẤP NHẬN cho hành vi đó (trúng một trong số đó là đúng, như loai = don của bộ đo). Mô hình tách KHÔNG nhìn thấy
         trường này khi huấn luyện; nó chỉ dùng để chấm cả đường ống (tách -> tìm -> gộp) và để kiểm phủ.

  loai   don    đúng 1 hành vi.      nhieu  từ 2 hành vi trở lên (mỗi hành vi là một việc có thể bị xử riêng, không tính
                                       tình tiết tăng nặng nằm trong cùng một Điều).
  nguon  claude | nguoi_dung | ban_an      trang_thai  nhap | da_duyet

Quy tắc chống rò rỉ: không được trùng cụm dài (K_TRUNG âm tiết liền nhau) với bất kỳ câu nào của bộ đo, để bộ đo còn nguyên giá trị.
Sửa nhãn, thêm mẫu: chỉ sửa train/tinh_huong.json rồi chạy `python scripts/kiem_tra_train.py`.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from .bo_cau_hoi import _CAM, _SO_DIEU, NGUON, TRANG_THAI

MAC_DINH = Path(__file__).resolve().parents[2] / "train" / "tinh_huong.json"
LOAI = ("don", "nhieu")
K_TRUNG = 9                      # cụm ≥ 9 âm tiết liền nhau trùng với một câu của bộ đo là rò rỉ (ngắn hơn là cụm pháp lý chung, vd. «đã bị phạt hành chính mà còn tái phạm»)
DO_DAI_TOI_THIEU = 25            # ký tự của tinh_huong
HE_THONG = ("Bạn đọc một tình huống đời thường và tách thành từng hành vi hoặc hậu quả có thể bị xử riêng theo pháp luật hình sự. "
            "Mỗi hành vi viết thành MỘT câu ngắn, tự đủ nghĩa, nêu các tình tiết quan trọng (số lượng, hậu quả, đối tượng, cách thức). "
            "Không nêu số Điều. Chỉ tách những việc có thể bị xử riêng; chi tiết không liên quan thì bỏ. "
            'Trả về đúng một JSON: {"hanh_vi": ["...", "..."]}, theo thứ tự xảy ra.')


class TapTrainError(ValueError):
    pass


def doc_tho(duong_dan: str | Path = MAC_DINH) -> dict:
    p = Path(duong_dan)
    if not p.exists():
        raise TapTrainError(f"không thấy {p}")
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        raise TapTrainError(f"{p.name} không phải JSON hợp lệ: {e}") from e
    if not isinstance(d, dict) or not isinstance(d.get("mau"), list):
        raise TapTrainError(f'{p.name}: thiếu danh sách "mau"')
    return d


def doc_train(duong_dan: str | Path = MAC_DINH) -> list[dict]:
    return doc_tho(duong_dan)["mau"]


def _tu(s: str) -> list[str]:
    return re.findall(r"\w+", s.lower())


def tap_cum(texts, k: int = K_TRUNG) -> set[tuple[str, ...]]:
    """Mọi cụm k âm tiết liền nhau của các văn bản (dùng để dò rò rỉ)."""
    out: set[tuple[str, ...]] = set()
    for t in texts:
        w = _tu(str(t))
        out.update(tuple(w[i:i + k]) for i in range(len(w) - k + 1))
    return out


def cum_trung(van_ban: str, cum_do: set[tuple[str, ...]], k: int = K_TRUNG) -> list[str]:
    w = _tu(van_ban)
    return sorted({" ".join(w[i:i + k]) for i in range(len(w) - k + 1) if tuple(w[i:i + k]) in cum_do})


def kiem_tra_hop_le(mau: list[dict], cau_do: list[str] | None = None) -> list[str]:
    """Danh sách lỗi (rỗng = hợp lệ). cau_do: các câu của bộ đo để dò rò rỉ."""
    loi: list[str] = []
    thay_id: set[str] = set()
    thay_van: dict[str, str] = {}
    cum_do = tap_cum(cau_do or [])
    dau_vao_do = {" ".join(c.lower().split()) for c in (cau_do or [])}
    for i, x in enumerate(mau, 1):
        id_ = x.get("id")
        ten = id_ if isinstance(id_, str) and id_.strip() else f"#{i}"
        if not (isinstance(id_, str) and id_.strip()):
            loi.append(f"{ten}: thiếu id")
        elif id_ in thay_id:
            loi.append(f"{ten}: id trùng")
        else:
            thay_id.add(id_)
        van = x.get("tinh_huong")
        if not (isinstance(van, str) and len(van.strip()) >= DO_DAI_TOI_THIEU):
            loi.append(f"{ten}: tinh_huong rỗng hoặc quá ngắn (< {DO_DAI_TOI_THIEU} ký tự)")
            van = ""
        else:
            k = " ".join(van.lower().split())
            if k in thay_van:
                loi.append(f"{ten}: tinh_huong trùng với {thay_van[k]}")
            thay_van.setdefault(k, ten)
            if _CAM.search(van):
                loi.append(f"{ten}: tinh_huong nhắc số Điều / khoản / bộ luật")
            if k in dau_vao_do:
                loi.append(f"{ten}: tinh_huong trùng nguyên văn một câu của bộ đo")
            elif cum_do and (t := cum_trung(van, cum_do)):
                loi.append(f"{ten}: tinh_huong trùng cụm {K_TRUNG} âm tiết với bộ đo: «{t[0]}»")
        hv = x.get("hanh_vi")
        if not (isinstance(hv, list) and hv):
            loi.append(f"{ten}: hanh_vi phải là danh sách không rỗng")
            hv = []
        mo_ta_thay: set[str] = set()
        for j, h in enumerate(hv, 1):
            tj = f"{ten}.hanh_vi[{j}]"
            if not isinstance(h, dict):
                loi.append(f"{tj}: phải là đối tượng {{mo_ta, dieu}}")
                continue
            m = h.get("mo_ta")
            if not (isinstance(m, str) and m.strip()):
                loi.append(f"{tj}: mo_ta rỗng")
            else:
                if _CAM.search(m):
                    loi.append(f"{tj}: mo_ta nhắc số Điều / khoản / bộ luật")
                km = " ".join(m.lower().split())
                if km in mo_ta_thay:
                    loi.append(f"{tj}: mo_ta lặp trong cùng tình huống")
                mo_ta_thay.add(km)
                if km in dau_vao_do:
                    loi.append(f"{tj}: mo_ta trùng nguyên văn một câu của bộ đo")
                elif cum_do and (t := cum_trung(m, cum_do)):
                    loi.append(f"{tj}: mo_ta trùng cụm {K_TRUNG} âm tiết với bộ đo: «{t[0]}»")
            d = h.get("dieu")
            if not (isinstance(d, list) and d and all(isinstance(s, str) and _SO_DIEU.fullmatch(s) for s in d)):
                loi.append(f"{tj}: dieu phải là danh sách số Điều dạng chuỗi, ví dụ [\"173\"]")
            elif len(set(d)) != len(d):
                loi.append(f"{tj}: dieu có số lặp")
        for truong, hop_le in (("loai", LOAI), ("nguon", NGUON), ("trang_thai", TRANG_THAI)):
            if x.get(truong) not in hop_le:
                loi.append(f"{ten}: {truong} = {x.get(truong)!r}, phải là một trong {', '.join(hop_le)}")
        if x.get("loai") == "don" and len(hv) != 1:
            loi.append(f"{ten}: loai don phải có đúng 1 hanh_vi (đang {len(hv)})")
        if x.get("loai") == "nhieu" and len(hv) < 2:
            loi.append(f"{ten}: loai nhieu cần ít nhất 2 hanh_vi (đang {len(hv)})")
    return loi


def dieu_da_phu(mau: list[dict]) -> Counter:
    """Đếm số lần mỗi Điều xuất hiện làm đáp án ("dieu") của một hành vi."""
    c: Counter = Counter()
    for x in mau:
        for h in x.get("hanh_vi", []):
            if isinstance(h, dict):
                for d in h.get("dieu", []) or []:
                    c[d] += 1
    return c


def thong_ke(mau: list[dict]) -> dict:
    so_hv = Counter(len(x.get("hanh_vi", [])) for x in mau)
    return {"so_mau": len(mau), "loai": Counter(x.get("loai") for x in mau), "nguon": Counter(x.get("nguon") for x in mau),
            "trang_thai": Counter(x.get("trang_thai") for x in mau), "so_hanh_vi": dict(sorted(so_hv.items())),
            "tong_hanh_vi": sum(k * v for k, v in so_hv.items())}


def tap_cua(id_: str, ti_le_val: float = 0.1) -> str:
    """'val' hoặc 'train', cố định theo id (băm), không phụ thuộc thứ tự hay số mẫu."""
    return "val" if int(hashlib.sha1(id_.encode("utf-8")).hexdigest(), 16) % 1000 < round(ti_le_val * 1000) else "train"


def dong_sft(x: dict) -> dict:
    """Một dòng SFT (định dạng messages). Đích CHỈ gồm mo_ta, không có số Điều: mô hình tách không được biết luật cụ thể nào."""
    dich = json.dumps({"hanh_vi": [h["mo_ta"] for h in x["hanh_vi"]]}, ensure_ascii=False)
    return {"id": x["id"], "messages": [{"role": "system", "content": HE_THONG},
                                          {"role": "user", "content": x["tinh_huong"]},
                                          {"role": "assistant", "content": dich}]}
