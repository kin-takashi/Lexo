"""Tách một bản án / quyết định hình sự (đã trích ra chữ) thành BỐN PHẦN, và rút nhãn thô từ phần Quyết định.

Bố cục bản án theo Điều 260 BLTTHS 2015: phần mở đầu -> NỘI DUNG VỤ ÁN -> NHẬN ĐỊNH CỦA TÒA ÁN -> QUYẾT ĐỊNH (rồi Nơi nhận / chữ ký).
Quyết định về thủ tục (kháng cáo quá hạn, đình chỉ xét xử phúc thẩm...) dùng NHẬN THẤY -> XÉT THẤY -> QUYẾT ĐỊNH; cũng tách được
nhưng đánh dấu kieu = "quyet_dinh_thu_tuc" vì KHÔNG phải mẫu có sự kiện + tội danh để dùng cho Chức năng 2.

Ba điều rút ra từ 10 bản án thật đầu tiên (xem tests/test_tach_ban_an.py) và đã được xử lý ở đây:
  * văn bản trích ra có ký tự ngắt trang (\\f) dính đầu dòng tiêu đề, số trang đứng một mình, NBSP, và (bản quét OCR) tiêu đề sai dấu:
    "NỌI DUNG VỤ ÁN", "NHẠẬN THÁY" -> so khớp tiêu đề trên dạng BỎ DẤU + gần đúng (difflib), không so khớp nguyên văn;
  * bản án PHÚC THẨM / GIÁM ĐỐC THẨM chép lại nguyên văn phần quyết định của bản án sơ thẩm ngay trong NỘI DUNG VỤ ÁN
    ("Tại Bản án hình sự sơ thẩm số ... quyết định: ... Xử phạt ..."): đó là CHỖ LỘ ĐÁP ÁN, nên tách riêng thành so_tham_trich;
    su_viec chỉ gồm phần đứng TRƯỚC đoạn đó;
  * su_viec vẫn có thể còn dấu hiệu rò rỉ ("truy tố về tội “...”", "Điều 134 BLHS"): tim_dau_hieu_ro_ri() đếm chúng để bước
    gỡ tội danh sau này biết phải xử lý bao nhiêu.

Chỉ dùng thư viện chuẩn (đọc PDF cần pdfplumber, nạp trễ). Không làm thay đổi file gốc.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

# --------------------------------------------------------------------------------------------------------------------
# Chuẩn hóa văn bản
# --------------------------------------------------------------------------------------------------------------------
_SO_TRANG = re.compile(r"^[-–—\s]*\d{1,3}[-–—\s]*$")     # dòng chỉ có số trang


def chuan_hoa(text: str) -> str:
    """NFC, ngắt trang (\\f) -> xuống dòng, NBSP/zero-width -> bỏ, gộp khoảng trắng, bỏ dòng chỉ có số trang, gộp dòng trống."""
    t = unicodedata.normalize("NFC", text)
    t = t.replace("\r\n", "\n").replace("\r", "\n").replace("\f", "\n")
    t = t.replace(" ", " ").replace("​", "").replace("﻿", "").replace("\t", " ")
    out: list[str] = []
    for dong in t.split("\n"):
        d = re.sub(r" {2,}", " ", dong).strip()
        if d and _SO_TRANG.match(d):
            continue
        if not d and (not out or not out[-1]):
            continue
        out.append(d)
    while out and not out[-1]:
        out.pop()
    return "\n".join(out)


def bo_dau(s: str) -> str:
    s = s.replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


def khoa(s: str) -> str:
    """Dạng so khớp: bỏ dấu, IN HOA, mọi ký tự không phải chữ/số thành một dấu cách."""
    return re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9]+", " ", bo_dau(s).upper())).strip()


# --------------------------------------------------------------------------------------------------------------------
# Nhận diện tiêu đề (gần đúng, chịu lỗi OCR)
# --------------------------------------------------------------------------------------------------------------------
_TIEU_DE = {                      # tên -> (khóa chuẩn, ngưỡng giống nhau)
    "noi_dung": ("NOI DUNG VU AN", 0.84),
    "nhan_thay": ("NHAN THAY", 0.80),
    "nhan_dinh": ("NHAN DINH CUA TOA AN", 0.84),
    "xet_thay": ("XET THAY", 0.80),
    "quyet_dinh": ("QUYET DINH", 0.88),
}


def la_tieu_de(k: str, ten: str) -> bool:
    mau, nguong = _TIEU_DE[ten]
    if not k or abs(len(k) - len(mau)) > 4:
        return False
    return k == mau or SequenceMatcher(None, k, mau).ratio() >= nguong


_CUOI = re.compile(r"^NOI NHAN\b|\bTM HOI DONG\b|^TM\b|^T M\b|^CAC THAM PHAN\b|\bCHU TOA PHIEN\b|^TM UY BAN\b|^THAM PHAN CHU TOA\b")


def _tim_tieu_de(keys: list[str]) -> dict[str, int]:
    """Chỉ số dòng của: noi_dung, nhan_dinh, quyet_dinh, cuoi (khóa thiếu = không thấy) + 'goc' = tên tiêu đề đã khớp."""
    res: dict[str, int] = {}
    ten_goc: dict[str, str] = {}
    for i, k in enumerate(keys):
        for ten in ("noi_dung", "nhan_thay"):
            if la_tieu_de(k, ten):
                res["noi_dung"] = i
                ten_goc["noi_dung"] = ten
                break
        if "noi_dung" in res:
            break
    start = res.get("noi_dung", -1) + 1
    for i in range(start, len(keys)):
        hit = next((t for t in ("nhan_dinh", "xet_thay") if la_tieu_de(keys[i], t)), None)
        if hit:
            res["nhan_dinh"] = i
            ten_goc["nhan_dinh"] = hit
            break
    start = res.get("nhan_dinh", res.get("noi_dung", -1)) + 1
    for i in range(start, len(keys)):
        if la_tieu_de(keys[i], "quyet_dinh"):
            res["quyet_dinh"] = i
            break
    if "quyet_dinh" in res:
        for i in range(res["quyet_dinh"] + 2, len(keys)):
            if _CUOI.search(keys[i]):
                res["cuoi"] = i
                break
    res_goc = {k: v for k, v in ten_goc.items()}
    res["_goc"] = res_goc   # type: ignore[assignment]
    return res


# --------------------------------------------------------------------------------------------------------------------
# Thông tin ở phần đầu
# --------------------------------------------------------------------------------------------------------------------
_RE_SO = re.compile(r"(?i:(bản án|quyết định)\s+)?(?i:số)\s*:?\s*(\d{1,4})\s*/\s*(\d{4})\s*/\s*([A-ZĐ]{2,}(?:\s*[-–]\s*[A-ZĐ]{2,})*)")
_RE_NGAY_1 = re.compile(r"(?i:ngày)\s*:?\s*(\d{1,2})\s*[/\-–—]\s*(\d{1,2})\s*[/\-–—]\s*(\d{4})")
_RE_NGAY_2 = re.compile(r"(?i:ngày)\s+(\d{1,2})\s+(?i:tháng)\s+(\d{1,2})\s+(?i:năm)\s+(\d{4})")
_RE_SO_THAM_THAM_CHIEU = re.compile(r"(?i:sơ\s*th[aảâầẩ]m)\s+(?i:số)\s*(\d{1,4}/\d{4}/[A-ZĐ]{2,}(?:-[A-ZĐ]{2,})?)")


def _cap_tu_hau_to(hau_to: str) -> str:
    h = bo_dau(hau_to).upper().replace(" ", "").replace("–", "-")
    if "GDT" in h:
        return "giam_doc_tham"
    if h.endswith("TT") or "-TT" in h:
        return "tai_tham"
    if "PT" in h:
        return "phuc_tham"
    if "ST" in h:
        return "so_tham"
    return "khong_ro"


def trich_thong_tin(dau: str, toan_van: str = "") -> dict:
    meta: dict = {"so": None, "nam": None, "hau_to": None, "loai": None, "cap": "khong_ro", "ngay": None, "toa_an": None,
                  "so_tham_tham_chieu": None}
    m = _RE_SO.search(dau)
    if m:
        meta["loai"] = (m.group(1) or "").lower() or None
        meta["so"] = m.group(2)
        meta["nam"] = int(m.group(3))
        meta["hau_to"] = re.sub(r"\s*[-–]\s*", "-", m.group(4))
        meta["cap"] = _cap_tu_hau_to(meta["hau_to"])
    ung_vien = []
    for rx in (_RE_NGAY_1, _RE_NGAY_2):
        for m in rx.finditer(dau):
            d, mo, y = (int(x) for x in m.groups())
            if 1 <= d <= 31 and 1 <= mo <= 12:
                ung_vien.append((m.start(), f"{y:04d}-{mo:02d}-{d:02d}"))
    if ung_vien:                       # ngày ra bản án đứng sớm nhất ở phần đầu (các ngày tạm giữ, bắt... đứng sau)
        meta["ngay"] = min(ung_vien)[1]
    dong = dau.split("\n")
    for i, d in enumerate(dong[:12]):
        if khoa(d).startswith("TOA AN"):
            ten = re.split(r"(?i)(?:C[ỘỌ]NG H[ÒO]A|Độc lập)", d)[0].strip()
            if i + 1 < len(dong) and khoa(dong[i + 1]).startswith("TAI "):
                ten = (ten + " " + re.split(r"(?i)(?:C[ỘỌ]NG H[ÒO]A|Độc lập)", dong[i + 1])[0].strip()).strip()
            meta["toa_an"] = ten
            break
    m = _RE_SO_THAM_THAM_CHIEU.search((toan_van or dau).replace("-\n", "-"))
    if m:
        meta["so_tham_tham_chieu"] = m.group(1)
    return meta


# --------------------------------------------------------------------------------------------------------------------
# NỘI DUNG VỤ ÁN: tách sự việc / đoạn chép bản án sơ thẩm / diễn biến kháng cáo
# --------------------------------------------------------------------------------------------------------------------
_RE_TRICH_SO_THAM = re.compile(r"\bTAI (?:CAC )?(?:BAN AN|QUYET DINH)\b[A-Z0-9 ]{0,40}?\bSO THAM SO\b")
_RE_BAT_DAU_KHANG_CAO = re.compile(r"^(?:NGAY \d|SAU KHI XET XU|KHONG DONG Y|DO KHONG DONG Y|TAI PHIEN TOA)")
_RE_KHANG_CAO = re.compile(r"(?<!QUYEN )KHANG CAO|(?<!QUYEN )KHANG NGHI")


def cat_noi_dung(dong_nd: list[str]) -> dict:
    """dong_nd[0] là dòng tiêu đề. Trả su_viec / so_tham_trich / dien_bien (chuỗi) và canh_bao (list)."""
    body = dong_nd[1:]
    keys = [khoa(d) for d in body]
    canh_bao: list[str] = []
    j = None
    for i, k in enumerate(keys):
        win = k + " " + (keys[i + 1] if i + 1 < len(keys) else "")
        m = _RE_TRICH_SO_THAM.search(win)
        if m and m.start() < len(k):
            j = i
            break
    if j is None:
        return {"su_viec": "\n".join(body).strip(), "so_tham_trich": "", "dien_bien": "", "canh_bao": canh_bao}
    e = None
    for i in range(j + 1, len(keys)):
        if _RE_BAT_DAU_KHANG_CAO.match(re.sub(r"^(?:\d+\s)?", "", keys[i])):
            win = " ".join(keys[i:i + 3])
            if _RE_KHANG_CAO.search(win):
                e = i
                break
    if e is None:
        canh_bao.append("không thấy mốc kết thúc đoạn chép bản án sơ thẩm (dòng 'Ngày ..., ... kháng cáo'); coi phần còn lại là so_tham_trich")
        e = len(body)
    return {"su_viec": "\n".join(body[:j]).strip(), "so_tham_trich": "\n".join(body[j:e]).strip(),
            "dien_bien": "\n".join(body[e:]).strip(), "canh_bao": canh_bao}


# --------------------------------------------------------------------------------------------------------------------
# Phần QUYẾT ĐỊNH: dẫn chiếu pháp luật, tội danh, hình phạt (thô)
# --------------------------------------------------------------------------------------------------------------------
def _mem(cum: str) -> str:
    """Regex cho một cụm từ chịu được chữ bị vỡ bởi khoảng trắng thừa khi trích PDF ('B ộ luật', 'T ố tụng hình s ự')."""
    return r"\s+".join(r"\s?".join(re.escape(c) for c in tu) for tu in cum.split())


_RE_BO_LUAT = (r"(?:" + _mem("Bộ luật") + r"\s+(?:" + _mem("Tố tụng") + r"\s+)?(?:" + _mem("hình") + "|" + _mem("dân") + r")\s+"
               + _mem("sự") + r"|BL(?:TT)?[HD]S)")
_RE_AP_DUNG = re.compile(r"(?:Áp dụng|Căn cứ)\s*:?\s*(?P<ds>.{3,400}?)\s*(?:của\s+)?(?P<bl>" + _RE_BO_LUAT + r")", re.S | re.I)
_RE_TOI = re.compile(r"tội\s*:?\s*[“\"]\s*([^”\"]{3,90}?)\s*[”\"]", re.I)
_RE_XU_PHAT = re.compile(r"Xử phạt[^.]{3,260}")
_TOKEN = re.compile(
    r"(?P<diem>(?:các\s+)?điểm\s+(?P<dl>[a-zđ]\b(?:\s*(?:,|và|\.)\s*[a-zđ]\b)*))"
    r"|(?P<khoan>(?:các\s+)?khoản\s+(?P<kl>\d+(?:\s*(?:,|và)\s*\d+)*))"
    r"|(?P<dieu>(?:các\s+)?điều\s+(?P<el>\d+(?:[a-zđ](?!\w))?(?:\s*(?:,|và)\s*\d+(?:[a-zđ](?!\w))?)*))", re.I)   # «Điều 217a», «Điều 51, 52»


def _loai_bo_luat(s: str) -> str:
    k = khoa(s).replace(" ", "")      # bỏ khoảng trắng: PDF hay vỡ chữ thành «T ố tụng», «B ộ luật»
    if "TOTUNG" in k or "BLTT" in k:
        return "tttt_hinh_su" if ("HINH" in k or "BLTTHS" in k) else "tttt_dan_su"
    if "DAN" in k or "BLDS" in k:
        return "dan_su"
    return "hinh_su"


def rut_dieu(ds: str) -> list[dict]:
    """'điểm b khoản 2 Điều 318, Điều 38; điểm s khoản 1, khoản 2 Điều 51' -> [{dieu,chu,khoan,diem}, ...].
    dieu là số nguyên; chu là chữ cái đi kèm của Điều có chữ ('Điều 217a' -> dieu 217, chu 'a'), None nếu không có.
    Quy ước: nhóm điểm đứng ngay trước một khoản thuộc về khoản đó; danh sách 'Điều 51, 52' gắn khoản/điểm đang chờ vào Điều đầu tiên."""
    out: list[dict] = []
    nhom: list[tuple[str, list[str]]] = []          # (khoản, [điểm])
    diem_cho: list[str] = []
    for m in _TOKEN.finditer(ds):
        if m.group("diem"):
            diem_cho = [x.lower() for x in re.findall(r"[a-zđ]\b", m.group("dl"), re.I)]
        elif m.group("khoan"):
            for idx, k in enumerate(re.findall(r"\d+", m.group("kl"))):
                nhom.append((k, diem_cho if idx == 0 else []))
            diem_cho = []
        else:
            for idx, (d, chu) in enumerate(re.findall(r"(\d+)([a-zđ](?!\w))?", m.group("el"), re.I)):
                chu = chu.lower() or None
                if idx == 0 and nhom:
                    for k, dm in nhom:
                        for p in (dm or [None]):
                            out.append({"dieu": int(d), "chu": chu, "khoan": int(k), "diem": p})
                elif idx == 0 and diem_cho:
                    for p in diem_cho:
                        out.append({"dieu": int(d), "chu": chu, "khoan": None, "diem": p})
                else:
                    out.append({"dieu": int(d), "chu": chu, "khoan": None, "diem": None})
            nhom, diem_cho = [], []
    return out


def rut_nhan_quyet_dinh(quyet_dinh: str) -> dict:
    """Nhãn THÔ từ phần Quyết định: các dẫn chiếu theo từng bộ luật, tội danh trong ngoặc kép, các câu 'Xử phạt ...'."""
    q = re.sub(r"\s+", " ", quyet_dinh)
    dan_chieu: list[dict] = []
    for m in _RE_AP_DUNG.finditer(q):
        ds = m.group("ds").strip(" ,;:")
        loai = _loai_bo_luat(m.group("bl"))
        dan_chieu.append({"bo_luat": loai, "goc": ds, "dieu": rut_dieu(ds)})
    toi: list[str] = []
    for m in _RE_TOI.finditer(q):
        t = m.group(1).strip()
        if t not in toi:
            toi.append(t)
    return {"dan_chieu": dan_chieu, "toi_danh": toi, "xu_phat": [m.group(0).strip() for m in _RE_XU_PHAT.finditer(q)]}


_KQ = {
    "huy": re.compile(r"\bHUY (?:TOAN BO |MOT PHAN |PHAN )?(?:BAN AN|QUYET DINH)"),
    "giu_nguyen": re.compile(r"\bGIU NGUYEN\b"),
    "sua": re.compile(r"\bSUA (?:TOAN BO |MOT PHAN |PHAN )?(?:BAN AN|QUYET DINH|HINH PHAT|MOT PHAN|PHAN)"),
    "chap_nhan_khang_cao": re.compile(r"(?<!KHONG )\bCHAP NHAN (?:MOT PHAN )?(?:YEU CAU |QUYET DINH )?KHANG (?:CAO|NGHI)"),
    "khong_chap_nhan_khang_cao": re.compile(r"\bKHONG CHAP NHAN (?:YEU CAU )?KHANG (?:CAO|NGHI)|\bBAC KHANG CAO"),
    "dinh_chi": re.compile(r"\bDINH CHI\b"),
}


def ket_qua_cap_tren(quyet_dinh: str) -> list[str]:
    """Dấu hiệu cách bản án cấp trên xử bản án sơ thẩm: huy / giu_nguyen / sua / chap_nhan_khang_cao / khong_chap_nhan_khang_cao / dinh_chi."""
    k = khoa(quyet_dinh)
    return [ten for ten, rx in _KQ.items() if rx.search(k)]


def nguon_nhan_de_xuat(cap: str, kq: list[str]) -> str:
    """Nhãn tội danh/hình phạt CUỐI CÙNG nằm ở đâu (ĐỀ XUẤT, người duyệt quyết):
    quyet_dinh (bản án sơ thẩm) | so_tham_trich (cấp trên giữ nguyên) | quyet_dinh_cap_tren (cấp trên sửa) |
    ket_hop (nhiều bị cáo: có người sửa, có người giữ nguyên) | khong_co_nhan_cuoi (hủy / đình chỉ: chưa có kết luận cuối)."""
    if cap == "so_tham":
        return "quyet_dinh"
    giu = "giu_nguyen" in kq or "khong_chap_nhan_khang_cao" in kq
    if "sua" in kq:
        return "ket_hop" if giu else "quyet_dinh_cap_tren"
    if giu:
        return "so_tham_trich"
    if "huy" in kq or "dinh_chi" in kq:
        return "khong_co_nhan_cuoi"
    return "khong_ro"


# --------------------------------------------------------------------------------------------------------------------
# Dấu hiệu rò rỉ trong su_viec, và dấu hiệu thông tin cá nhân còn sót
# --------------------------------------------------------------------------------------------------------------------
_RO_RI = {
    "toi_danh_ngoac_kep": re.compile(r"tội\s*:?\s*[“\"][^”\"]{3,90}[”\"]", re.I),
    "dieu_luat": re.compile(r"(?:điểm\s+[a-zđ]\b|khoản\s+\d+|Điều\s+\d+)[^.;]{0,60}?(?:Điều\s+\d+)[^.;]{0,40}?" + _RE_BO_LUAT
                            + r"|Điều\s+\d+\s+" + _RE_BO_LUAT, re.I),
    "truy_to": re.compile(r"truy tố", re.I),
    "xu_phat_tuyen_bo": re.compile(r"Xử phạt|Tuyên bố|tuyên phạt|bị kết án", re.I),
    "ap_dung": re.compile(r"Áp dụng"),
}


def tim_dau_hieu_ro_ri(van_ban: str) -> dict[str, int]:
    t = re.sub(r"\s+", " ", van_ban)
    return {ten: len(rx.findall(t)) for ten, rx in _RO_RI.items() if rx.search(t)}


_PII = {
    "day_so_dai_9_13_chu_so": re.compile(r"\b\d{9,13}(?:[xX]{1,4})?\b"),
    "so_bi_che_xxx": re.compile(r"\b\d{5,}[xX]{2,}\b"),
    "sinh_ngay_day_du": re.compile(r"sinh\s+(?:ngày\s+)?(?:\d{1,2}[/ -]\d{1,2}[/ -]\d{4}|\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4})", re.I),
    "sinh_nam": re.compile(r"sinh\s+năm\s+\d{4}", re.I),
    "noi_thuong_tru_cu_tru": re.compile(r"nơi\s+(?:đăng ký\s+)?(?:thường trú|cư trú|ở hiện tại)|Địa chỉ", re.I),
    "ten_cha_me_vo_chong": re.compile(r"con (?:ông|bà)|Họ tên (?:cha|mẹ)|có (?:chồng|vợ)", re.I),
    "dien_thoai": re.compile(r"\b0\d{9}\b"),
}


def tim_pii(van_ban: str) -> dict[str, int]:
    """Đếm dấu hiệu thông tin cá nhân CÒN SÓT trong văn bản đã công bố (chỉ đếm, không sửa)."""
    return {ten: len(rx.findall(van_ban)) for ten, rx in _PII.items() if rx.search(van_ban)}


# --------------------------------------------------------------------------------------------------------------------
# Hàm chính
# --------------------------------------------------------------------------------------------------------------------
_TOI_THIEU = {"noi_dung": 100, "nhan_dinh": 100, "quyet_dinh": 60}


def tach(van_ban: str) -> dict:
    """Tách văn bản thành bốn phần. Không ném lỗi khi thiếu tiêu đề: ghi canh_bao và dat=False."""
    t = chuan_hoa(van_ban)
    dong = t.split("\n")
    keys = [khoa(d) for d in dong]
    td = _tim_tieu_de(keys)
    goc = td.pop("_goc")           # type: ignore[arg-type]
    canh_bao: list[str] = []

    moc = sorted((v, k) for k, v in td.items())      # (chỉ số dòng, tên phần)
    phan = {"dau": "", "noi_dung": "", "nhan_dinh": "", "quyet_dinh": "", "cuoi": ""}
    dau_to = moc[0][0] if moc else len(dong)
    phan["dau"] = "\n".join(dong[:dau_to]).strip()
    for n, (vi_tri, ten) in enumerate(moc):
        ket = moc[n + 1][0] if n + 1 < len(moc) else len(dong)
        phan[ten] = "\n".join(dong[vi_tri:ket]).strip()

    for ten, nhan in (("noi_dung", "NỘI DUNG VỤ ÁN / NHẬN THẤY"), ("nhan_dinh", "NHẬN ĐỊNH CỦA TÒA ÁN / XÉT THẤY"), ("quyet_dinh", "QUYẾT ĐỊNH")):
        if ten not in td:
            canh_bao.append(f"không thấy tiêu đề {nhan}")
        elif len(phan[ten]) < _TOI_THIEU[ten]:
            canh_bao.append(f"phần {ten} quá ngắn ({len(phan[ten])} ký tự)")
    if "quyet_dinh" in td and "cuoi" not in td:
        canh_bao.append("không thấy mốc 'Nơi nhận' / chữ ký sau phần Quyết định")

    meta = trich_thong_tin(phan["dau"], t)
    thu_tuc = goc.get("noi_dung") == "nhan_thay" or (meta["hau_to"] or "").endswith("QĐ")
    kieu = "quyet_dinh_thu_tuc" if thu_tuc else ("ban_an" if "noi_dung" in td else "khong_ro")

    nd: dict = {"su_viec": "", "so_tham_trich": "", "dien_bien": ""}
    if phan["noi_dung"]:
        nd = cat_noi_dung(phan["noi_dung"].split("\n"))
        canh_bao += nd.pop("canh_bao")
        if kieu == "ban_an" and meta["cap"] in ("phuc_tham", "giam_doc_tham", "tai_tham") and not nd["so_tham_trich"]:
            canh_bao.append("bản án cấp trên nhưng không thấy đoạn chép bản án sơ thẩm trong NỘI DUNG (su_viec có thể còn lộ kết quả)")

    rong = {"dan_chieu": [], "toi_danh": [], "xu_phat": []}
    nhan = rut_nhan_quyet_dinh(phan["quyet_dinh"]) if phan["quyet_dinh"] else rong
    nhan_st = rut_nhan_quyet_dinh(nd["so_tham_trich"]) if nd["so_tham_trich"] else rong
    kq = ket_qua_cap_tren(phan["quyet_dinh"]) if kieu == "ban_an" else []
    dat = all(k in td for k in ("noi_dung", "nhan_dinh", "quyet_dinh")) and not any(c.startswith("phần ") for c in canh_bao)
    return {
        "kieu": kieu,
        "dat": bool(dat),
        "meta": meta,
        "tieu_de": {k: v for k, v in sorted(td.items())},      # chỉ số dòng trong văn bản đã chuẩn hóa
        "tieu_de_goc": goc,
        "phan": phan,
        "noi_dung": nd,
        "nhan_quyet_dinh": nhan,
        "nhan_so_tham_trich": nhan_st,
        "ket_qua_cap_tren": kq,
        "nguon_nhan_de_xuat": nguon_nhan_de_xuat(meta["cap"], kq) if kieu == "ban_an" else "khong_dung_lam_mau",
        "ro_ri_trong_su_viec": tim_dau_hieu_ro_ri(nd["su_viec"]),
        "pii": tim_pii(t),
        "canh_bao": canh_bao,
    }


# --------------------------------------------------------------------------------------------------------------------
# Đọc file
# --------------------------------------------------------------------------------------------------------------------
def doc_file(path: str | Path) -> tuple[str, list[str]]:
    """.txt -> chữ UTF-8; .pdf -> pdfplumber (nạp trễ). Trả (văn bản, cảnh báo). PDF quét ảnh trả văn bản gần rỗng + cảnh báo cần OCR."""
    p = Path(path)
    if p.suffix.lower() == ".pdf":
        import pdfplumber  # noqa: PLC0415
        trang: list[str] = []
        with pdfplumber.open(p) as pdf:
            for pg in pdf.pages:
                trang.append(pg.extract_text() or "")
        van = "\f".join(trang)
        canh = []
        if len(van.strip()) < 200 * max(1, len(trang)):
            canh.append(f"PDF có ít chữ ({len(van.strip())} ký tự / {len(trang)} trang): nhiều khả năng là bản quét ảnh, cần OCR")
        return van, canh
    return p.read_text(encoding="utf-8", errors="replace"), []
