"""Bản án hình sự từ dataset Hugging Face tmquan/anle-toaan-gov-vn -> tập đo / tập huấn luyện «sự việc -> Điều BLHS».

Nhãn ở đây là Điều mà TÒA ÁN đã áp dụng (đọc từ phần Quyết định hoặc đoạn chép bản án sơ thẩm), không phải nhãn do Claude soạn.
Các bước (mỗi bước một hàm, để kiểm thử riêng):
  1. la_hinh_su(): chỉ giữ văn bản hình sự;
  2. tach() của src/ban_an/tach.py -> danh_gia(): giữ văn bản có nhãn DÙNG ĐƯỢC
     (đủ bốn phần, biết nhãn cuối nằm ở đâu, có ít nhất một Điều tội phạm, phần nhãn không nhắc BLHS 1999);
  3. che_dap_an(): che tội danh (của nhãn, của mọi tội trong BLHS lấy từ luat.sqlite, và tên tội viết hoa sau chữ «tội»),
     dẫn chiếu Điều luật (chịu chữ bị vỡ khi trích PDF) và dữ liệu cá nhân dễ thấy trong phần sự việc (đầu vào của mô hình);
     bỏ hẳn các câu nêu kết quả xét xử / đề nghị mức án còn sót (bộ tách không nhận ra đoạn chép bản án sơ thẩm);
     tên tội còn nằm trong lời kể («hành vi lừa đảo chiếm đoạt tài sản») KHÔNG che, chỉ đếm (ten_toi_trong_loi_ke);
  4. gom_vu() + chia_tap(): các bản án cùng một vụ (cùng bản án sơ thẩm, hoặc sự việc gần trùng) luôn nằm cùng một tập;
     chia theo Điều hiếm nhất của nhóm, cố định bằng băm (seed) nên thêm văn bản mới không xáo lại các nhóm cũ;
  5. trung_voi(): kiểm trùng đầu vào với tập huấn luyện cũ (train/tinh_huong.json).

Cấp xét xử lấy từ số bản án do bộ tách đọc (HS-ST / HS-PT / ...), KHÔNG dùng trường cấp xét xử của dataset: trường đó sai ở
phần lớn văn bản gắn nhãn sơ thẩm (tác giả dataset lấy nhầm số bản án sơ thẩm được trích trong bản án phúc thẩm).
Chỉ dùng thư viện chuẩn; đọc parquet cần pyarrow (nạp trễ).
"""
from __future__ import annotations

import hashlib
import math
import re
import sqlite3
import unicodedata
from pathlib import Path

from src.ban_an.tach import _RE_BO_LUAT, _mem, khoa, tach, tim_dau_hieu_ro_ri, tim_pii

DATASET = "tmquan/anle-toaan-gov-vn"
DIEU_TOI_PHAM_DAU, DIEU_TOI_PHAM_CUOI = 108, 425      # Phần thứ hai BLHS 2015 (các tội phạm): Điều 108 -> Điều 425
CHE = "[đã che]"
DAU_VAO_TOI_THIEU = 200          # ký tự: sau khi che và bỏ câu phán quyết, sự việc ngắn hơn thì không đủ để làm mẫu

# --------------------------------------------------------------------------------------------------------------------
# 1. Đọc dataset, lọc hình sự
# --------------------------------------------------------------------------------------------------------------------


def doc_parquet(path: str | Path) -> list[dict]:
    import pyarrow.parquet as pq  # noqa: PLC0415
    return pq.read_table(str(path)).to_pylist()


def tim_parquet(thu_muc: str | Path) -> Path | None:
    """File documents-*.parquet đầu tiên trong thư mục (tìm cả thư mục con: snapshot_download giữ nguyên cây data/ của dataset)."""
    ds = sorted(Path(thu_muc).rglob("documents-*.parquet")) if Path(thu_muc).exists() else []
    return ds[0] if ds else None


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for khoi in iter(lambda: f.read(1 << 20), b""):
            h.update(khoi)
    return h.hexdigest()


COT_VAN_BAN = ("content", "text", "noi_dung", "full_text", "markdown")
COT_MA = ("doc_name", "id", "doc_id", "document_id", "web_url", "url", "source_url")
CAP_DATASET = {"First-instance": "so_tham", "Appellate": "phuc_tham", "Cassation": "giam_doc_tham", "Retrial": "tai_tham"}
COT_LOAI_AN = ("case_type", "loai_an", "linh_vuc", "category", "case_category")


def _cot(row: dict, ung_vien: tuple[str, ...]) -> str | None:
    for c in ung_vien:
        if c in row and row[c] not in (None, ""):
            return c
    return None


def van_ban(row: dict) -> str:
    c = _cot(row, COT_VAN_BAN)
    return str(row[c]) if c else ""


def ma_van_ban(row: dict, stt: int) -> str:
    c = _cot(row, COT_MA)
    return str(row[c]) if c else f"hang_{stt:05d}"


_HAU_TO_HS = re.compile(r"\b\d{1,4}\s*/\s*\d{4}\s*/\s*(?:HS|HSST|HSPT|HS-ST|HS-PT|HS-GĐT|HS-GDT|HS-TT)\b", re.I)


def la_hinh_su(row: dict) -> bool:
    """Trường loại án của dataset nếu có; không có thì xem số bản án trong 1.500 ký tự đầu có hậu tố HS không."""
    c = _cot(row, COT_LOAI_AN)
    if c:
        return khoa(str(row[c])).startswith("HINH SU") or khoa(str(row[c])) in ("CRIMINAL", "HS")
    return bool(_HAU_TO_HS.search(van_ban(row)[:1500]))


# --------------------------------------------------------------------------------------------------------------------
# 2. Nhãn dùng được
# --------------------------------------------------------------------------------------------------------------------
_NGUON_DUNG_DUOC = ("quyet_dinh", "so_tham_trich", "quyet_dinh_cap_tren", "ket_hop")
_BLHS_1999 = re.compile(r"\b(?:BO LUAT HINH SU|BLHS)(?: NUOC CHXHCN VIET NAM| NUOC CONG HOA XA HOI CHU NGHIA VIET NAM)?(?: NAM)? 1999\b"
                        r"|\b15 1999 QH10\b")


def dieu_toi_pham(dan_chieu: list[dict]) -> list[str]:
    """Các Điều thuộc Phần các tội phạm (108-425) trong dẫn chiếu BLHS, dạng chuỗi '173', '217a'; giữ thứ tự xuất hiện."""
    ra: list[str] = []
    for d in dan_chieu:
        if d["bo_luat"] != "hinh_su":
            continue
        for x in d["dieu"]:
            if DIEU_TOI_PHAM_DAU <= x["dieu"] <= DIEU_TOI_PHAM_CUOI:
                s = f"{x['dieu']}{x.get('chu') or ''}"
                if s not in ra:
                    ra.append(s)
    return ra


def phan_nhan(kq: dict) -> tuple[list[dict], list[str], str]:
    """(dẫn chiếu, tội danh, văn bản phần nhãn) theo nguồn nhãn đề xuất của bộ tách."""
    nguon = kq["nguon_nhan_de_xuat"]
    qd, st = kq["nhan_quyet_dinh"], kq["nhan_so_tham_trich"]
    if nguon in ("quyet_dinh", "quyet_dinh_cap_tren"):
        return qd["dan_chieu"], qd["toi_danh"], kq["phan"]["quyet_dinh"]
    if nguon == "so_tham_trich":
        return st["dan_chieu"], st["toi_danh"], kq["noi_dung"]["so_tham_trich"]
    if nguon == "ket_hop":          # nhiều bị cáo: có người được sửa (quyết định cấp trên), có người giữ nguyên (bản sơ thẩm)
        toi = qd["toi_danh"] + [t for t in st["toi_danh"] if t not in qd["toi_danh"]]
        return qd["dan_chieu"] + st["dan_chieu"], toi, kq["phan"]["quyet_dinh"] + "\n" + kq["noi_dung"]["so_tham_trich"]
    return [], [], ""


def danh_gia(kq: dict) -> dict:
    """{dung_duoc, ly_do, dieu, toi_danh, nhac_blhs_1999}. ly_do là lý do LOẠI đầu tiên (None nếu dùng được)."""
    dan_chieu, toi, van_nhan = phan_nhan(kq)
    dieu = dieu_toi_pham(dan_chieu)
    nhac_1999 = bool(_BLHS_1999.search(khoa(van_nhan)))
    if kq["kieu"] != "ban_an":
        ly_do = f"kieu_{kq['kieu']}"
    elif not kq["dat"]:
        ly_do = "thieu_phan"
    elif kq["nguon_nhan_de_xuat"] not in _NGUON_DUNG_DUOC:
        ly_do = f"nguon_nhan_{kq['nguon_nhan_de_xuat']}"
    elif not dieu:
        ly_do = "khong_co_dieu_toi_pham"
    elif nhac_1999:
        ly_do = "nhac_blhs_1999"
    elif not kq["noi_dung"]["su_viec"].strip():
        ly_do = "su_viec_rong"
    else:
        ly_do = None
    return {"dung_duoc": ly_do is None, "ly_do": ly_do, "dieu": dieu, "toi_danh": toi, "nhac_blhs_1999": nhac_1999}


def ten_toi_tu_luat(luat_sqlite: str | Path, so_hieu: str = "100/2015/QH13") -> list[str]:
    """Tên các tội (Điều 108-425, mọi phiên bản) lấy từ tiêu đề Điều trong db/luat.sqlite, bỏ chữ «Tội» đầu: 'trộm cắp tài sản'.
    Mở chỉ đọc."""
    conn = sqlite3.connect(f"file:{Path(luat_sqlite).as_posix()}?mode=ro", uri=True)
    try:
        rows = conn.execute(
            "SELECT DISTINCT p.ky_hieu, p.tieu_de FROM don_vi_luat d JOIN phien_ban_noi_dung p ON p.don_vi_id = d.id "
            "JOIN van_ban v ON v.id = d.van_ban_id WHERE v.so_hieu = ? AND d.loai = 'dieu' AND p.tieu_de IS NOT NULL", (so_hieu,)).fetchall()
    finally:
        conn.close()
    ra: list[str] = []
    for ky_hieu, tieu_de in rows:
        so = re.match(r"\d+", ky_hieu)
        m = re.match(r"\s*Tội\s+(.+?)\s*$", tieu_de or "")
        if so and m and DIEU_TOI_PHAM_DAU <= int(so.group()) <= DIEU_TOI_PHAM_CUOI and m.group(1) not in ra:
            ra.append(m.group(1))
    return ra


# --------------------------------------------------------------------------------------------------------------------
# 3. Che đáp án và dữ liệu cá nhân trong phần sự việc
# --------------------------------------------------------------------------------------------------------------------
# PDF/OCR hay vỡ chữ: «Đi ều 174», «kho ản», «iểm» (mất chữ đ), «Điều 1 41» (vỡ số) -> mỗi từ khóa chịu khoảng trắng thừa
_DIEM = r"đ?\s?i\s?[ểềêeế]\s?m"
_KHOAN = r"kho\s?[ảa]\s?n"
_DIEU = r"đ\s?i\s?[ềêe]\s?u"
_SO = r"\d(?:\s?\d){0,2}"
_DAN_CHIEU_TOKEN = (r"(?:(?:các\s+)?(?:" + _DIEM + r"\s+[a-zđ]?(?:\s*(?:,|và)\s*[a-zđ])*|" + _KHOAN + r"\s+" + _SO + r"(?:\s*(?:,|và)\s*" + _SO + r")*"
                    r"|" + _DIEU + r"\s+" + _SO + r"[a-zđ]?(?:\s*(?:,|và)\s*" + _SO + r"[a-zđ]?)*)(?!\w))")
_RE_DAN_CHIEU_BLHS = re.compile(                    # «điểm a khoản 2 Điều 134, Điều 38 (của) Bộ luật Hình sự (năm 2015...)»
    _DAN_CHIEU_TOKEN + r"(?:[\s,;]+(?:và\s+)?" + _DAN_CHIEU_TOKEN + r")*\s*(?:c\s?ủa\s+)?" + _RE_BO_LUAT
    + r"(?:\s+(?:năm\s+)?2015)?(?:\s*\((?:được\s+)?sửa đổi[^)]{0,60}\))?", re.I)
_RE_TOI_NGOAC = re.compile(r"(tội\s*:?\s*)[“\"]\s*[^”\"]{3,90}?\s*[”\"]", re.I)
_RE_SINH_NGAY = re.compile(r"(sinh\s+(?:ngày\s+)?)(?:\d{1,2}[/ -]\d{1,2}[/ -]\d{4}|\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+\d{4})", re.I)
_RE_SO_DAI = re.compile(r"\b\d{9,13}(?:[xX]{1,4})?\b(?!\s*(?:đồng|đ\b|VNĐ|VND|USD))")


def _re_ten_toi(ten: str) -> re.Pattern:
    """«tội Trộm cắp tài sản» không có ngoặc kép, chịu khoảng trắng thừa và hoa/thường."""
    return re.compile(r"(tội\s*(?:danh\s*)?:?\s*)" + _mem(ten) + r"(?!\w)", re.I)


# Tòa án viết hoa chữ đầu tên tội: «phạm tội Tàng trữ trái phép chất ma túy». Chữ thường («phạm tội lần đầu») không bị che.
_RE_TOI_VIET_HOA = re.compile(r"(tội[ \t]*(?:danh[ \t]*)?:?[ \t]*)([^\W\d_][^.,;:()\[\]\n“”\"]{2,90})")


def _che_toi_viet_hoa(t: str) -> tuple[str, int]:
    n = 0

    def thay(m: re.Match) -> str:
        nonlocal n
        if not m.group(2)[0].isupper():
            return m.group(0)
        n += 1
        return m.group(1) + CHE

    return _RE_TOI_VIET_HOA.sub(thay, t), n


def _re_dieu_so(dieu: str) -> re.Pattern:
    """«(điểm a khoản 2) Điều 134», chịu chữ / số bị vỡ («Đi ều 1 34»); không khớp «Điều 1340»."""
    so = r"\s?".join(re.escape(c) for c in dieu)
    return re.compile(r"(?:" + _DIEM + r"\s+[a-zđ]\s+)?(?:" + _KHOAN + r"\s+\d+\s+)?" + _DIEU + r"\s+" + so + r"(?![0-9a-zđ])", re.I)


_SAU_AP_DUNG = r"\s*:?\s*(?:vào\s+)?(?:\[đã che\]|(?:các\s+)?(?:" + _DIEM + r"|" + _KHOAN + r"|" + _DIEU + r")\s)"
_RE_CAU_PHAN_QUYET = re.compile(     # câu nêu KẾT QUẢ xét xử / đề nghị của kiểm sát viên: không phải sự việc, và lộ nhãn
    r"Áp\s?dụng" + _SAU_AP_DUNG + r"|Căn\s?cứ" + _SAU_AP_DUNG
    + r"|(?<!định\s)Xử\s?phạt(?!\s+vi\s?phạm)|tuyên\s?phạt|Tuy[êe]n\s?b?\s?ố\s*:?\s*(?:các\s+)?b?\s?ị\s?cáo"
    + r"|đề\s?nghị[^.]{0,120}?(?:xử\s?phạt|áp\s?dụng|tuyên\s?bố|mức\s?(?:án|hình\s?phạt)|từ\s+\d+\s+năm)", re.I)
_RE_TACH_CAU = re.compile(r"(?<=[.!?])\s+")


def bo_cau_phan_quyet(van: str) -> tuple[str, int]:
    """Bỏ các câu nêu quyết định / đề nghị mức án (đoạn chép bản án sơ thẩm mà bộ tách không nhận ra, lời đề nghị của VKS).
    Trả (văn bản còn lại, số câu đã bỏ). Dòng bị ngắt giữa câu được nối lại trước khi tách câu."""
    so_bo = 0
    dong_ra = []
    van = re.sub(r"(?<![.!?:])\n(?!\n)", " ", van)       # nối dòng bị ngắt giữa câu (văn bản trích từ PDF)
    for dong in van.split("\n"):
        giu = []
        for cau in _RE_TACH_CAU.split(dong):
            if _RE_CAU_PHAN_QUYET.search(cau):
                so_bo += 1
            else:
                giu.append(cau)
        if giu or not dong.strip():
            dong_ra.append(" ".join(giu))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(dong_ra)).strip(), so_bo


def che_dap_an(su_viec: str, dieu: list[str], toi_danh: list[str], ten_toi_blhs: tuple[str, ...] | list[str] = ()) -> tuple[str, dict[str, int]]:
    """Trả (văn bản đã che, số chỗ đã che theo loại). Thay các cụm lộ nhãn; bỏ hẳn những câu nêu kết quả xét xử.
    ten_toi_blhs: tên MỌI tội của BLHS (ten_toi_tu_luat), để che cả tên tội không nằm trong ngoặc kép, không chỉ tội của nhãn."""
    t = unicodedata.normalize("NFC", su_viec)
    dem: dict[str, int] = {}

    def thay(rx: re.Pattern, mau: str, ten: str) -> None:
        nonlocal t
        t, n = rx.subn(mau, t)
        if n:
            dem[ten] = dem.get(ten, 0) + n

    thay(_RE_DAN_CHIEU_BLHS, CHE, "dan_chieu_blhs")
    thay(_RE_TOI_NGOAC, r"\1" + CHE, "toi_danh_ngoac_kep")
    for ten in sorted(set(toi_danh), key=len, reverse=True):
        thay(_re_ten_toi(ten), r"\1" + CHE, "toi_danh_tran")
    for ten in sorted(set(ten_toi_blhs) - set(toi_danh), key=len, reverse=True):
        thay(_re_ten_toi(ten), r"\1" + CHE, "ten_toi_blhs")
    t, n = _che_toi_viet_hoa(t)
    if n:
        dem["toi_danh_viet_hoa"] = n
    for d in dieu:
        thay(_re_dieu_so(d), CHE, "dieu_le")
    thay(_RE_SINH_NGAY, r"\1" + CHE, "ngay_sinh")
    thay(_RE_SO_DAI, CHE, "day_so_dai")
    t, n = bo_cau_phan_quyet(t)
    if n:
        dem["cau_phan_quyet"] = n
    return t, dem


LO_NHAN = ("toi_danh_ngoac_kep", "dieu_luat", "dieu_cua_nhan", "ten_toi_cua_nhan", "ten_toi_blhs", "toi_danh_viet_hoa", "cau_phan_quyet")   # còn một trong số này = còn lộ
# nhãn. «truy tố» đứng một mình (tên tội và Điều đã che), «Áp dụng phương pháp ...» chỉ được đếm để báo cáo.
_RE_DIEU_BLHS_VO = re.compile(_DIEU + r"\s+" + _SO + r"[a-zđ]?[^.;]{0,40}?" + _RE_BO_LUAT, re.I)     # «Đi ều 1 41 ... BLHS»


def con_lo(van: str, dieu: list[str], toi_danh: list[str], ten_toi_blhs: tuple[str, ...] | list[str] = ()) -> dict[str, int]:
    """Dấu hiệu lộ nhãn CÒN LẠI sau khi che: bộ dò của tach.py + số Điều của nhãn + tên tội của nhãn đứng sau chữ «tội»."""
    ra = dict(tim_dau_hieu_ro_ri(van))
    n = len(_RE_DIEU_BLHS_VO.findall(van))
    if n > ra.get("dieu_luat", 0):
        ra["dieu_luat"] = n
    n = len(_RE_CAU_PHAN_QUYET.findall(van))
    if n:
        ra["cau_phan_quyet"] = n
    n = sum(len(_re_dieu_so(d).findall(van)) for d in dieu)
    if n:
        ra["dieu_cua_nhan"] = n
    n = sum(len(_re_ten_toi(x).findall(van)) for x in set(toi_danh))
    if n:
        ra["ten_toi_cua_nhan"] = n
    n = sum(len(_re_ten_toi(x).findall(van)) for x in set(ten_toi_blhs) - set(toi_danh))
    if n:
        ra["ten_toi_blhs"] = n
    n = _che_toi_viet_hoa(van)[1]
    if n:
        ra["toi_danh_viet_hoa"] = n
    return ra


# --------------------------------------------------------------------------------------------------------------------
# Xử lý một văn bản
# --------------------------------------------------------------------------------------------------------------------


def xu_ly(row: dict, stt: int = 0, ten_toi_blhs: tuple[str, ...] | list[str] = ()) -> dict:
    """Một hàng dataset -> bản ghi (có dung_duoc / ly_do). Không ném lỗi."""
    van = van_ban(row)
    cap_ds = next((row[c] for c in ("instance_level", "cap_xet_xu", "level") if row.get(c)), None)
    kq = tach(van)
    dg = danh_gia(kq)
    m = kq["meta"]
    ban_ghi = {
        "ma": ma_van_ban(row, stt),
        "so_ban_an": f"{m['so']}/{m['nam']}/{m['hau_to']}" if m["so"] else None,
        "cap": m["cap"],
        "cap_dataset": cap_ds,               # chỉ để đối chiếu; KHÔNG dùng (xem docstring đầu file)
        "cap_dataset_khop": CAP_DATASET.get(str(cap_ds)) == m["cap"] if cap_ds else None,
        "ngay": m["ngay"],
        "toa_an": m["toa_an"],
        "so_tham_tham_chieu": m["so_tham_tham_chieu"],
        "nguon_nhan": kq["nguon_nhan_de_xuat"],
        "ket_qua_cap_tren": kq["ket_qua_cap_tren"],
        **dg,
        "canh_bao": kq["canh_bao"],
        "hash_toan_van": hash_van(van),
    }
    if dg["dung_duoc"]:
        da_che, dem = che_dap_an(kq["noi_dung"]["su_viec"], dg["dieu"], dg["toi_danh"], ten_toi_blhs)
        ban_ghi.update({
            "dau_vao": da_che,
            "da_che": dem,
            "ro_ri_truoc_che": kq["ro_ri_trong_su_viec"],
            "ro_ri_sau_che": con_lo(da_che, dg["dieu"], dg["toi_danh"], ten_toi_blhs),
            "pii_sau_che": tim_pii(da_che),
            "hash_dau_vao": hash_van(da_che),
        })
        ban_ghi["lo_nhan_con_lai"] = {k: v for k, v in ban_ghi["ro_ri_sau_che"].items() if k in LO_NHAN}
        # tên tội của nhãn còn nằm trong LỜI KỂ («06 hành vi lừa đảo chiếm đoạt tài sản»): không che vì là mô tả sự việc,
        # nhưng đếm để báo cáo như một gợi ý mềm
        ban_ghi["ten_toi_trong_loi_ke"] = sum(len(re.findall(r"(?<!\w)" + _mem(x) + r"(?!\w)", da_che, re.I)) for x in set(dg["toi_danh"]))
        if len(da_che) < DAU_VAO_TOI_THIEU:
            ban_ghi["dung_duoc"], ban_ghi["ly_do"] = False, "dau_vao_qua_ngan"
    return ban_ghi


# --------------------------------------------------------------------------------------------------------------------
# 4. Gom vụ, chia tập
# --------------------------------------------------------------------------------------------------------------------


def chuan_van(s: str) -> str:
    return " ".join(unicodedata.normalize("NFC", s).lower().split())


def hash_van(s: str) -> str:
    """Cùng cách băm với src/dulieu/nhap.py (NFC, chữ thường, gọn khoảng trắng)."""
    return hashlib.sha256(chuan_van(s).encode("utf-8")).hexdigest()


def _shingle(s: str, n: int = 5) -> set[str]:
    tu = re.findall(r"\w+", chuan_van(s))
    return {" ".join(tu[i:i + n]) for i in range(max(1, len(tu) - n + 1))} if tu else set()


def do_chua(a: set, b: set) -> float:
    """Tỉ lệ 5-gram của văn bản NGẮN HƠN nằm trong văn bản kia: bắt được cả đoạn ngắn chép từ một bản án dài."""
    return len(a & b) / min(len(a), len(b)) if a and b else 0.0


def gom_vu(ban_ghi: list[dict], nguong_gan_trung: float = 0.6) -> dict[str, str]:
    """ma -> khóa nhóm. Chung một nhóm khi: cùng số bản án sơ thẩm được tham chiếu / cùng số bản án, hoặc sự việc gần trùng
    (do_chua 5-gram >= ngưỡng). Số bản án trùng giữa hai tòa khác nhau chỉ làm nhóm to hơn (an toàn cho việc chia tập)."""
    cha = {b["ma"]: b["ma"] for b in ban_ghi}

    def goc(x: str) -> str:
        while cha[x] != x:
            cha[x] = cha[cha[x]]
            x = cha[x]
        return x

    def noi(a: str, b: str) -> None:
        ra, rb = goc(a), goc(b)
        if ra != rb:
            cha[max(ra, rb)] = min(ra, rb)

    theo_so: dict[str, str] = {}
    for b in ban_ghi:
        for so in {b.get("so_tham_tham_chieu"), b.get("so_ban_an") if b.get("cap") == "so_tham" else None} - {None}:
            k = re.sub(r"\s+", "", so).upper()
            if k in theo_so:
                noi(b["ma"], theo_so[k])
            else:
                theo_so[k] = b["ma"]
    sh = {b["ma"]: _shingle(b.get("dau_vao", "")) for b in ban_ghi}
    ds = list(sh)
    for i, a in enumerate(ds):
        for c in ds[i + 1:]:
            if do_chua(sh[a], sh[c]) >= nguong_gan_trung:
                noi(a, c)
    return {m: goc(m) for m in cha}


def _bam(seed: int, khoa_: str) -> str:
    return hashlib.sha256(f"{seed}:{khoa_}".encode()).hexdigest()


def chia_tap(ban_ghi: list[dict], nhom: dict[str, str], ti_le_test: float = 0.5, seed: int = 2026) -> dict[str, str]:
    """ma -> 'train' | 'test'. Mỗi nhóm vụ vào trọn một tập. Tầng = Điều hiếm nhất của nhóm (đếm theo số nhóm);
    trong mỗi tầng lấy round(số nhóm × tỉ lệ) nhóm (làm tròn xuống khi đúng nửa, tối thiểu 1) vào test theo thứ tự băm;
    Điều chỉ có một nhóm luôn nằm ở test (để đo được), nên tỉ lệ test thực tế hơi cao hơn tham số."""
    if not 0 < ti_le_test < 1:
        raise ValueError("ti_le_test phải nằm trong (0, 1)")
    dieu_nhom: dict[str, set[str]] = {}
    for b in ban_ghi:
        dieu_nhom.setdefault(nhom[b["ma"]], set()).update(b["dieu"])
    tan_so: dict[str, int] = {}
    for ds in dieu_nhom.values():
        for d in ds:
            tan_so[d] = tan_so.get(d, 0) + 1
    tang: dict[str, list[str]] = {}
    for g, ds in dieu_nhom.items():
        hiem = min(ds, key=lambda d: (tan_so[d], d)) if ds else ""
        tang.setdefault(hiem, []).append(g)
    tap_nhom: dict[str, str] = {}
    for gs in tang.values():
        gs = sorted(gs, key=lambda g: _bam(seed, g))
        k = 1 if len(gs) == 1 else max(1, math.floor(len(gs) * ti_le_test + 0.5 - 1e-9))
        for i, g in enumerate(gs):
            tap_nhom[g] = "test" if i < k else "train"
    return {b["ma"]: tap_nhom[nhom[b["ma"]]] for b in ban_ghi}


# --------------------------------------------------------------------------------------------------------------------
# 5. Kiểm trùng với tập huấn luyện cũ
# --------------------------------------------------------------------------------------------------------------------


def trung_voi(ban_ghi: list[dict], van_cu: dict[str, str], nguong: float = 0.5) -> list[dict]:
    """So đầu vào đã che với các văn bản cũ {mã: văn bản}: trùng băm, hoặc do_chua 5-gram >= ngưỡng. Trả danh sách cặp."""
    cu = {m: (hash_van(v), _shingle(v)) for m, v in van_cu.items()}
    ra = []
    for b in ban_ghi:
        sb = _shingle(b["dau_vao"])
        for m, (h, s) in cu.items():
            j = 1.0 if h == b["hash_dau_vao"] else do_chua(sb, s)
            if j >= nguong:
                ra.append({"ma": b["ma"], "ma_cu": m, "do_chua": round(j, 3)})
    return ra
