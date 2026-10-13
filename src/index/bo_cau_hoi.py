"""Bộ câu hỏi đánh giá thống nhất: MỘT file nguồn eval/bo_cau_hoi.json, chia thành các tập bằng trường `tap`.

Mỗi câu có: id, cau_hoi, dieu (danh sách số Điều), loai, tap, nguon, trang_thai.

  tap     dev       chẩn đoán và chọn tham số (được xem kết quả, được chỉnh).
          xac_nhan  xác nhận độc lập cấu hình đã chọn trên dev: chạy với tham số ĐÃ CHỐT, không quét, không chỉnh.
          kiem_tra  đóng băng: xác nhận cuối, không quét, không chỉnh theo kết quả.
          phu       phủ nốt: mỗi Điều về tội phạm chưa có câu nào ở ba tập trên có một câu, để đo độ phủ toàn bộ luật.
                    Chỉ đo với tham số đã chốt, không quét, không chỉnh theo kết quả.
  loai    don         `dieu` là các Điều CHẤP NHẬN: tìm được bất kỳ Điều nào trong danh sách là trúng.
          nhieu_dieu  `dieu` là các Điều CẦN TÌM ĐỦ (mỗi Điều ứng với một hành vi khác nhau của cùng tình huống).
                      Các script chấm Hit@k hiện bỏ qua loại này (doc_bo(..., loai="don")), tránh chấm sai.
  nguon   claude | nguoi_dung | ban_an: ai soạn câu. Câu do cùng một mô hình soạn với dữ liệu huấn luyện sau này sẽ cho điểm
          cao hơn thực tế, nên báo cáo riêng theo nguồn.
  trang_thai   nhap | da_duyet

Sửa nhãn, thêm câu: chỉ sửa eval/bo_cau_hoi.json rồi chạy `python scripts/kiem_tra_bo_cau_hoi.py`.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

MAC_DINH = Path(__file__).resolve().parents[2] / "eval" / "bo_cau_hoi.json"
TAP = ("dev", "xac_nhan", "kiem_tra", "phu")
TAP_DONG_BANG = frozenset({"xac_nhan", "kiem_tra", "phu"})          # chỉ xác nhận với tham số đã chốt: cấm quét / chỉnh
LOAI = ("don", "nhieu_dieu")
NGUON = ("claude", "nguoi_dung", "ban_an")
TRANG_THAI = ("nhap", "da_duyet")
FILE_CU = {"cau_hoi_dev.json": "dev", "cau_hoi_dev2.json": "xac_nhan", "cau_hoi_thu.json": "kiem_tra"}
_SO_DIEU = re.compile(r"\d+[a-z]?")
_CAM = re.compile(r"\b(điều|khoản|điểm)\s+\d|bộ luật|\bblhs\b|luật hình sự", re.I)


class BoCauHoiError(ValueError):
    pass


def doc_tho(duong_dan: str | Path) -> dict:
    """Đọc file JSON của bộ câu hỏi; báo lỗi rõ ràng (kể cả khi người dùng còn gọi tên file cũ đã gom)."""
    p = Path(duong_dan)
    if not p.exists():
        if p.name in FILE_CU:
            raise BoCauHoiError(f"{p.name} đã được gom vào eval/bo_cau_hoi.json. Dùng: --bo-cau-hoi eval/bo_cau_hoi.json --tap {FILE_CU[p.name]}")
        raise BoCauHoiError(f"không thấy {p}")
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except ValueError as e:
        raise BoCauHoiError(f"{p.name} không phải JSON hợp lệ: {e}") from e
    if not isinstance(d, dict) or not isinstance(d.get("cau_hoi"), list):
        raise BoCauHoiError(f'{p.name}: thiếu danh sách "cau_hoi"')
    return d


def doc_bo(duong_dan: str | Path = MAC_DINH, tap: str | None = None, loai: str | None = "don") -> list[dict]:
    """Các câu của một tập (tap=None hoặc "tat_ca": mọi tập). loai="don" (mặc định) bỏ các câu cần tìm đủ nhiều Điều; loai=None: lấy cả hai."""
    cau = doc_tho(duong_dan)["cau_hoi"]
    if tap not in (None, "tat_ca"):
        if tap not in TAP:
            raise BoCauHoiError(f"tập không hợp lệ: {tap!r}; chọn một trong {', '.join(TAP)} hoặc tat_ca")
        co = Counter(x.get("tap") for x in cau)
        cau = [x for x in cau if x.get("tap") == tap]
        if not cau:
            raise BoCauHoiError(f"không có câu nào thuộc tập {tap!r}; các tập hiện có: {dict(co)}")
    if loai is not None:
        cau = [x for x in cau if x.get("loai", "don") == loai]
        if not cau:
            raise BoCauHoiError(f"không có câu nào loại {loai!r} trong tập đã chọn")
    return cau


def kiem_tra_hop_le(cau: list[dict]) -> list[str]:
    """Danh sách lỗi (rỗng = hợp lệ). Kiểm tra từng câu và quan hệ giữa các tập."""
    loi: list[str] = []
    thay_id: set[str] = set()
    thay_cau: dict[str, str] = {}
    dieu_theo_tap: dict[str, dict[str, str]] = {}                # tap -> {số Điều: id}, chỉ với loai = don
    for i, x in enumerate(cau, 1):
        id_ = x.get("id")
        ten = id_ if isinstance(id_, str) and id_.strip() else f"#{i}"
        if not (isinstance(id_, str) and id_.strip()):
            loi.append(f"{ten}: thiếu id")
        elif id_ in thay_id:
            loi.append(f"{ten}: id trùng")
        else:
            thay_id.add(id_)
        q = x.get("cau_hoi")
        if not (isinstance(q, str) and q.strip()):
            loi.append(f"{ten}: câu hỏi rỗng")
        else:
            k = " ".join(q.lower().split())
            if k in thay_cau:
                loi.append(f"{ten}: câu hỏi trùng với {thay_cau[k]}")
            thay_cau.setdefault(k, ten)
            if _CAM.search(q):
                loi.append(f"{ten}: câu hỏi nhắc số Điều / khoản / bộ luật (người dân không hỏi vậy)")
        dieu = x.get("dieu")
        if not (isinstance(dieu, list) and dieu and all(isinstance(d, str) and _SO_DIEU.fullmatch(d) for d in dieu)):
            loi.append(f"{ten}: dieu phải là danh sách số Điều dạng chuỗi, ví dụ [\"173\"] hoặc [\"217a\"]")
            dieu = []
        elif len(set(dieu)) != len(dieu):
            loi.append(f"{ten}: dieu có số lặp")
        for truong, hop_le in (("tap", TAP), ("nguon", NGUON), ("trang_thai", TRANG_THAI), ("loai", LOAI)):
            if x.get(truong) not in hop_le:
                loi.append(f"{ten}: {truong} = {x.get(truong)!r}, phải là một trong {', '.join(hop_le)}")
        if x.get("loai") == "nhieu_dieu" and len(dieu) < 2:
            loi.append(f"{ten}: loai nhieu_dieu cần ít nhất 2 Điều")
        if x.get("loai") == "don" and x.get("tap") in TAP:
            m = dieu_theo_tap.setdefault(x["tap"], {})
            for d in dieu:
                m.setdefault(d, ten)
    taps = sorted(dieu_theo_tap)
    for a in range(len(taps)):                                     # câu "don": cùng một Điều không được đứng ở hai tập
        for b in range(a + 1, len(taps)):
            for d in sorted(set(dieu_theo_tap[taps[a]]) & set(dieu_theo_tap[taps[b]]), key=lambda s: (len(s), s)):
                loi.append(f"Điều {d} là đáp án ở cả tập {taps[a]} ({dieu_theo_tap[taps[a]][d]}) và {taps[b]} ({dieu_theo_tap[taps[b]][d]})")
    return loi


def thong_ke(cau: list[dict]) -> dict[str, Counter]:
    return {t: Counter(x.get(t) for x in cau) for t in ("tap", "loai", "nguon", "trang_thai")}


def _ten_dieu(tieu_de: dict[str, str], d: str) -> str:
    t = tieu_de.get(f"dieu {d}")
    return re.sub(r"^Điều\s+\S+\.\s*", "", t).strip() if t else "?"


def bang_xem_duyet(cau: list[dict], tieu_de: dict[str, str]) -> str:
    """Bảng markdown để duyệt nhãn: id, câu hỏi, Điều, tiêu đề Điều; chia theo tập. `tieu_de`: {"dieu 173": "Điều 173. Tội trộm cắp tài sản"}."""
    dong = ["# Duyệt bộ câu hỏi", "",
            "Với mỗi câu: đọc câu hỏi, xem Điều ghi bên phải có ĐÚNG là điều luật người hỏi cần không. Báo lại id sai hoặc thiếu, "
            "ví dụ: `sai e05 (thêm 176)`, hoặc `ok hết`. Câu hỏi nên là lời người dân, không lặp từ trong tên Điều.", ""]
    for tap in TAP:
        xs = [x for x in cau if x.get("tap") == tap]
        if not xs:
            continue
        dong += [f"## Tập {tap} ({len(xs)} câu)", "", "| id | câu hỏi | Điều | tiêu đề Điều |", "|---|---|---|---|"]
        for x in xs:
            q = str(x.get("cau_hoi", "")).replace("|", "\\|")
            ti = "; ".join(_ten_dieu(tieu_de, d) for d in x.get("dieu", [])).replace("|", "\\|")
            dong.append(f"| {x.get('id')} | {q} | {', '.join(x.get('dieu', []))} | {ti} |")
        dong.append("")
    return "\n".join(dong) + "\n"
