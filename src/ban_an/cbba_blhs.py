"""Bản án hình sự từ dataset Hugging Face tmquan/cbba-toaan-gov-vn -> lọc theo Bộ luật Hình sự (BLHS), chia train / test.

Dataset: bản án thật (sơ thẩm, phúc thẩm, giám đốc thẩm, tái thẩm) từ cổng congbobanan.toaan.gov.vn, CC-BY-4.0,
khoảng 1,5 triệu văn bản / 16 file documents-*.parquet (~4,6 GB). Cùng lược đồ với tmquan/anle-toaan-gov-vn (src/ban_an/anle_hf.py).
Module này CHỈ lọc + chia; không gán nhãn, không che đáp án (việc đó là của tach.py / anle_hf.che_dap_an trên tập đã chia).

Các bước (mỗi bước một hàm, để kiểm thử riêng):
  1. tai_shard(): tải từng file parquet (chỉ thư viện chuẩn);
  2. loc_shard(): đọc theo lô, giữ văn bản category == 'Criminal' CÓ trích dẫn Bộ luật Hình sự. «Có trích dẫn BLHS» = ít nhất một
     «Điều N … Bộ luật hình sự» (N = 1..426) ở lớp regex `citations_law` HOẶC lớp phân tích cấu trúc `citations` của dataset.
     Không tính Bộ luật Tố tụng hình sự, Luật Thi hành án hình sự. Tên luật bị PDF tách chữ («H ình sự») vẫn nhận;
  3. loai_bo(): bỏ «quyết định» (đình chỉ, trả hồ sơ…: không có phần xét xử), văn bản quá ngắn, văn bản trùng nguyên văn;
  4. gom_vu(): bản án cấp trên (phúc thẩm, giám đốc thẩm, tái thẩm) và bản án sơ thẩm của nó luôn cùng một nhóm (khóa: số + năm + NGÀY
     của bản án sơ thẩm do bản án cấp trên nêu; chỉ nối khi khớp 1-3 văn bản, nhiều hơn là mơ hồ nên không nối).
     KHÔNG nối bản án sơ thẩm với bản án sơ thẩm khác: số bản án sơ thẩm nêu trong một bản án sơ thẩm là tiền án của bị cáo, số thụ lý
     của chính tòa đó hoặc trùng số ngẫu nhiên giữa các tòa, không phải cùng một vụ (khảo sát 5 mẫu: 0/5 cùng vụ);
  5. chia_tap(): mỗi nhóm vào trọn một tập, chọn bằng băm sha256(seed:khóa nhóm) nên cố định và thêm văn bản không xáo lại nhóm cũ.
     Tỉ lệ test thực tế lệch tham số một chút (băm theo nhóm, không ép đúng từng văn bản).

Cấp xét xử: dataset lấy từ MÃ SỐ bản án trên cổng; ta đối chiếu với dòng «Thành phần Hội đồng xét xử sơ thẩm / phúc thẩm…» ở đầu văn bản.
Hai nguồn lệch nhau thì tin văn bản (mau_thuan_cap = True); cả hai nguồn đều được giữ lại trong bản ghi.
Văn bản là chữ trích từ PDF: còn dữ liệu cá nhân và có chỗ vỡ chữ; đây là dữ liệu thô, chưa che gì.
Chỉ dùng thư viện chuẩn; đọc parquet cần pyarrow (nạp trễ).
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
import shutil
import time
import unicodedata
import urllib.request
from collections import Counter
from pathlib import Path

DATASET = "tmquan/cbba-toaan-gov-vn"
SO_SHARD = 16
DIEU_TOI_PHAM_DAU, DIEU_TOI_PHAM_CUOI = 108, 425     # Phần thứ hai BLHS 2015 (các tội phạm), cùng quy ước với anle_hf
DIEU_TOI_DA = 426                                     # BLHS 2015 có 426 Điều; số lớn hơn là nhiễu của regex
SO_KY_TU_TOI_THIEU = 3000                              # ngắn hơn: không phải bản án đầy đủ (xem tom_tat.json -> thong_ke_loc)
PHIEN_BAN_LOC = "v1"                                   # đổi khi đổi logic loc_shard: file lọc trung gian cũ sẽ không bị dùng lại
CAP_CONG_THONG_TIN = {"First-instance": "so_tham", "Appellate": "phuc_tham", "Cassation": "giam_doc_tham", "Retrial": "tai_tham"}
COT_DOC = ("doc_name", "official_document_id", "official_document_id_normalized", "code", "category", "instance_level", "court",
           "court_level", "issued_date", "year", "citations_law", "citations", "web_url", "pdf_url", "markdown")

LUU_Y = (
    "Văn bản là chữ trích từ PDF: còn dữ liệu cá nhân (tên, địa chỉ, số giấy tờ) và có chỗ vỡ chữ; chưa che gì.",
    "cap lấy từ dòng «Hội đồng xét xử … thẩm» trong văn bản, khác mã số trên cổng ở mau_thuan_cap = true; cap_cong_thong_tin giữ giá trị của cổng.",
    "Chỉ nối bản án cấp trên với bản án sơ thẩm khi khớp (số, năm, ngày). Bản án phúc thẩm không nối được vẫn có thể có sơ thẩm của nó "
    "ở tập kia (xem gom_vu.khong_noi_duoc); muốn chắc chắn không rò rỉ thì chạy với --cap so_tham.",
    "Hai bản án sơ thẩm khác nhau về cùng bị cáo (tiền án, tổng hợp hình phạt) không được nối: có thể nằm ở hai tập khác nhau.",
    "Văn bản dài từ 3.000 ký tự có thể còn lẫn một số quyết định (đình chỉ, trả hồ sơ…): mã QĐ trên cổng cũng gắn cho nhiều bản án thật nên không dùng để loại.",
    "BLHS 1999 và 2015 đều được tính là «Bộ luật hình sự»; đánh số Điều khác nhau. Dùng nhac_blhs_1999, nhac_blhs_2015, ngay để chọn phiên bản luật.",
)

# --------------------------------------------------------------------------------------------------------------------
# 1. Tải
# --------------------------------------------------------------------------------------------------------------------


def ten_shard(i: int, n: int = SO_SHARD) -> str:
    return f"documents-{i:05d}-of-{n:05d}.parquet"


def url_shard(i: int, n: int = SO_SHARD) -> str:
    return f"https://huggingface.co/datasets/{DATASET}/resolve/main/{ten_shard(i, n)}"


def shard_doc_duoc(path: str | Path) -> bool:
    """File parquet đọc được phần chân (file tải dở thì không)."""
    import pyarrow.parquet as pq  # noqa: PLC0415
    try:
        return pq.ParquetFile(str(path)).metadata.num_rows > 0
    except Exception:  # noqa: BLE001 - mọi lỗi đọc đều nghĩa là file hỏng / dở
        return False


def tai_shard(i: int, thu_muc: str | Path, n: int = SO_SHARD, lan_thu: int = 3, im: bool = False) -> Path:
    """Tải documents-0000i-of-000nn.parquet về thu_muc nếu chưa có file đọc được. Ghi ra .part rồi đổi tên."""
    thu_muc = Path(thu_muc)
    thu_muc.mkdir(parents=True, exist_ok=True)
    dich = thu_muc / ten_shard(i, n)
    if dich.exists() and shard_doc_duoc(dich):
        return dich
    tam = dich.with_name(dich.name + ".part")
    loi = None
    for lan in range(1, lan_thu + 1):
        try:
            req = urllib.request.Request(url_shard(i, n), headers={"User-Agent": "lexo-cbba/1.0"})
            with urllib.request.urlopen(req, timeout=120) as r, tam.open("wb") as f:
                shutil.copyfileobj(r, f, 1 << 20)
            tam.replace(dich)
            if shard_doc_duoc(dich):
                return dich
            loi = RuntimeError(f"{dich.name}: tải xong nhưng không đọc được")
        except Exception as e:  # noqa: BLE001
            loi = e
        if not im:
            print(f"  [thử lại {lan}/{lan_thu}] {dich.name}: {loi}", flush=True)
        time.sleep(3 * lan)
    raise RuntimeError(f"không tải được {dich.name}: {loi}")


def phien_ban_dataset() -> dict:
    """{'sha': mã commit của dataset trên HF} để ghi vào tom_tat.json; không có mạng thì {'sha': None}."""
    try:
        with urllib.request.urlopen(f"https://huggingface.co/api/datasets/{DATASET}", timeout=30) as r:
            d = json.load(r)
        return {"sha": d.get("sha"), "lastModified": d.get("lastModified")}
    except Exception:  # noqa: BLE001
        return {"sha": None, "lastModified": None}


def sha256_ma(ma) -> str:
    """Dấu vân tay của một tập mã văn bản (không phụ thuộc thứ tự): so hai lần chạy / hai máy có chia giống nhau không."""
    return hashlib.sha256("\n".join(sorted(ma)).encode("utf-8")).hexdigest()


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for khoi in iter(lambda: f.read(1 << 20), b""):
            h.update(khoi)
    return h.hexdigest()


# --------------------------------------------------------------------------------------------------------------------
# 2. Nhận biết trích dẫn BLHS, cấp xét xử, loại văn bản
# --------------------------------------------------------------------------------------------------------------------


def _gon(s: str | None) -> str:
    """Bỏ mọi khoảng trắng + hạ chữ thường + NFC: 'H ình sự' -> 'hìnhsự' (PDF hay tách chữ)."""
    return re.sub(r"\s+", "", unicodedata.normalize("NFC", s or "")).lower()


def la_ten_blhs(loai: str | None = None, ten: str | None = None, dich: str | None = None) -> bool:
    """Bộ luật Hình sự, KHÔNG phải Bộ luật Tố tụng hình sự / Luật Thi hành án hình sự.
    Lớp regex `citations_law` cho (loại, tên): ('Bộ luật', 'hình sự'); lớp cấu trúc `citations` cho chuỗi đích 'Bộ luật hình sự'."""
    if dich is not None:
        return _gon(dich).startswith("bộluậthìnhsự")
    return _gon(loai) == "bộluật" and _gon(ten).startswith("hìnhsự")


def dan_chieu_blhs(row: dict) -> set[tuple[str, str, str]]:
    """{(điều, khoản, điểm)} được trích dẫn từ BLHS, gộp hai lớp trích dẫn của dataset. Chuỗi rỗng = không nêu."""
    ra: set[tuple[str, str, str]] = set()
    for x in row.get("citations_law") or []:
        if la_ten_blhs(x.get("law_type"), x.get("law_name")) and x.get("article"):
            ra.add((x["article"], x.get("clause") or "", x.get("point") or ""))
    for x in row.get("citations") or []:
        if x.get("target") and la_ten_blhs(dich=x["target"]) and x.get("dieu"):
            ra.add((x["dieu"], x.get("khoan") or "", x.get("diem") or ""))
    return {r for r in ra if r[0].isdigit() and 1 <= int(r[0]) <= DIEU_TOI_DA}


# Bản án phúc thẩm nêu bản án sơ thẩm: «Bản án hình sự sơ thẩm số 07/2017/HSST ngày 20/03/2017 của Tòa án nhân dân…»
_RE_SO_THAM = re.compile(
    r"số\s*:?\s*0*(\d{1,4})\s*/\s*(\d{4})\s*/\s*(?:HS\s*-?\s*ST|HSST)[^\n]{0,60}?"
    r"ngày\s*0*(\d{1,2})\s*(?:/|-|\.|tháng)\s*0*(\d{1,2})\s*(?:/|-|\.|năm)\s*(\d{4})", re.I)
_RE_SO_BAN_AN = re.compile(r"0*(\d{1,4})\s*/\s*(\d{4})\s*/")


def tham_chieu_so_tham(van_ban: str) -> list[tuple[int, int, str]]:
    """[(số, năm, 'YYYY-MM-DD')] của các bản án sơ thẩm được nêu (số + năm + ngày) trong 60.000 ký tự đầu, đã bỏ trùng và sắp xếp."""
    ra = set()
    for m in _RE_SO_THAM.finditer(van_ban[:60000]):
        so, nam, ng, th, nam_ng = (int(g) for g in m.groups())
        if 1 <= ng <= 31 and 1 <= th <= 12:
            ra.add((so, nam, f"{nam_ng:04d}-{th:02d}-{ng:02d}"))
    return sorted(ra)


def so_va_nam(so_chuan: str | None) -> tuple[int, int] | None:
    m = _RE_SO_BAN_AN.match(so_chuan or "")
    return (int(m.group(1)), int(m.group(2))) if m else None


_RE_HDXX = re.compile(r"Hội\s+đồng\s+xét\s+xử\s+(sơ|phúc|giám\s+đốc|tái)\s+thẩm", re.I)
_CAP_THEO_CHU = {"sơ": "so_tham", "phúc": "phuc_tham", "giám": "giam_doc_tham", "tái": "tai_tham"}


def cap_theo_van_ban(van_ban: str) -> str | None:
    """Cấp xét xử theo dòng «Thành phần Hội đồng xét xử … thẩm gồm có» đầu tiên trong 4.000 ký tự đầu; None nếu không thấy."""
    m = _RE_HDXX.search(van_ban[:4000])
    return _CAP_THEO_CHU[m.group(1).lower().split()[0]] if m else None


_RE_TIEU_DE_BAN_AN = re.compile(r"Bản\s+án\s+(?:hình\s+sự\s+)?(?:số|sơ|phúc)|BẢN\s+ÁN")
_RE_TIEU_DE_QUYET_DINH = re.compile(r"QUYẾT\s+ĐỊNH")


def loai_van_ban(van_ban: str) -> str:
    """'quyet_dinh' khi phần đầu có tiêu đề QUYẾT ĐỊNH mà không có tiêu đề Bản án (đình chỉ, trả hồ sơ…); còn lại 'ban_an'.
    Lưu ý: bản án nào cũng có chữ «QUYẾT ĐỊNH:» ở phần tuyên án, nên chỉ xét phần đầu và chỉ khi thiếu tiêu đề Bản án."""
    dau = van_ban[:2500]
    if not _RE_TIEU_DE_BAN_AN.search(dau[:1800]) and _RE_TIEU_DE_QUYET_DINH.search(dau):
        return "quyet_dinh"
    return "ban_an"


_RE_BLHS_1999 = re.compile(r"bộluậthìnhsự(?:nướccộnghoàxãhộichủnghĩaviệtnam|nướccộnghòaxãhộichủnghĩaviệtnam)?(?:năm)?1999|15/1999/qh10")
_RE_BLHS_2015 = re.compile(r"bộluậthìnhsự(?:nướccộnghoàxãhộichủnghĩaviệtnam|nướccộnghòaxãhộichủnghĩaviệtnam)?(?:năm)?2015|100/2015/qh13")


def nhac_phien_ban(van_ban: str) -> tuple[bool, bool]:
    """(nhắc BLHS 1999, nhắc BLHS 2015) theo cách văn bản tự gọi. Chỉ là gợi ý để chọn phiên bản luật; đa số văn bản chỉ viết «Bộ luật hình sự»."""
    g = _gon(van_ban)
    return bool(_RE_BLHS_1999.search(g)), bool(_RE_BLHS_2015.search(g))


def cap_cuoi(cap_cong: str | None, cap_van_ban: str | None) -> tuple[str, bool]:
    """(cấp dùng, mâu thuẫn). Văn bản nói gì thì tin điều đó; không thấy trong văn bản thì dùng cổng; không có gì: 'khong_ro'."""
    cong = CAP_CONG_THONG_TIN.get(cap_cong or "")
    return (cap_van_ban or cong or "khong_ro"), bool(cap_van_ban and cong and cap_van_ban != cong)


# --------------------------------------------------------------------------------------------------------------------
# 3. Lọc một shard
# --------------------------------------------------------------------------------------------------------------------
def _luoc_do():
    import pyarrow as pa  # noqa: PLC0415
    ds = pa.list_(pa.string())
    return pa.schema([
        ("ma", pa.string()), ("so_ban_an", pa.string()), ("so_chuan", pa.string()), ("ma_loai", pa.string()),
        ("cap", pa.string()), ("cap_cong_thong_tin", pa.string()), ("cap_theo_van_ban", pa.string()), ("mau_thuan_cap", pa.bool_()),
        ("loai_van_ban", pa.string()), ("toa_an", pa.string()), ("cap_toa", pa.string()), ("ngay", pa.string()), ("nam", pa.int32()),
        ("dieu_blhs", ds), ("dieu_khoan_diem_blhs", ds), ("co_dieu_toi_pham", pa.bool_()),
        ("nhac_blhs_1999", pa.bool_()), ("nhac_blhs_2015", pa.bool_()), ("tham_chieu_so_tham", ds),
        ("md5", pa.string()), ("so_ky_tu", pa.int32()), ("url_web", pa.string()), ("url_pdf", pa.string()), ("van_ban", pa.string())])


def ban_ghi_tu_hang(row: dict, dan_chieu: set[tuple[str, str, str]]) -> dict:
    """Một hàng của dataset (đã biết là hình sự và có trích dẫn BLHS) -> bản ghi gọn; chưa có cột `tap`/`nhom_vu`."""
    vb = unicodedata.normalize("NFC", row.get("markdown") or "")
    dieu = sorted({d for d, _, _ in dan_chieu}, key=int)
    cap_vb = cap_theo_van_ban(vb)
    cap, mau_thuan = cap_cuoi(row.get("instance_level"), cap_vb)
    n1999, n2015 = nhac_phien_ban(vb)
    nam = row.get("year")
    return {
        "ma": row["doc_name"],
        "so_ban_an": row.get("official_document_id"),
        "so_chuan": row.get("official_document_id_normalized"),
        "ma_loai": row.get("code"),
        "cap": cap,
        "cap_cong_thong_tin": CAP_CONG_THONG_TIN.get(row.get("instance_level") or ""),
        "cap_theo_van_ban": cap_vb,
        "mau_thuan_cap": mau_thuan,
        "loai_van_ban": loai_van_ban(vb),
        "toa_an": row.get("court"),
        "cap_toa": row.get("court_level"),
        "ngay": row.get("issued_date"),
        "nam": int(nam) if isinstance(nam, (int, float)) and nam == nam else None,
        "dieu_blhs": dieu,
        "dieu_khoan_diem_blhs": sorted(f"{a}|{k}|{p}" for a, k, p in dan_chieu),
        "co_dieu_toi_pham": any(DIEU_TOI_PHAM_DAU <= int(d) <= DIEU_TOI_PHAM_CUOI for d in dieu),
        "nhac_blhs_1999": n1999,
        "nhac_blhs_2015": n2015,
        "tham_chieu_so_tham": [f"{s}|{n}|{d}" for s, n, d in tham_chieu_so_tham(vb)],
        "md5": hashlib.md5(re.sub(r"\s+", " ", vb).strip().encode("utf-8")).hexdigest(),
        "so_ky_tu": len(vb),
        "url_web": row.get("web_url"),
        "url_pdf": row.get("pdf_url"),
        "van_ban": vb,
    }


def loc_shard(nguon: str | Path, dich: str | Path, kich_thuoc_lo: int = 2000) -> dict:
    """Đọc shard theo lô, ghi parquet các văn bản hình sự có trích dẫn BLHS. Trả về {'tong', 'hinh_su', 'co_blhs'}."""
    import pyarrow as pa  # noqa: PLC0415
    import pyarrow.parquet as pq  # noqa: PLC0415
    tk = Counter()
    pf = pq.ParquetFile(str(nguon))
    luoc_do = _luoc_do()
    tam = Path(str(dich) + ".part")
    with pq.ParquetWriter(str(tam), luoc_do, compression="zstd") as w:
        dem: list[dict] = []

        def xa() -> None:
            if dem:
                w.write_table(pa.Table.from_pylist(dem, schema=luoc_do))
                dem.clear()

        for lo in pf.iter_batches(batch_size=kich_thuoc_lo, columns=list(COT_DOC)):
            for row in lo.to_pylist():
                tk["tong"] += 1
                if row.get("category") != "Criminal":
                    continue
                tk["hinh_su"] += 1
                dc = dan_chieu_blhs(row)
                if not dc:
                    continue
                tk["co_blhs"] += 1
                dem.append(ban_ghi_tu_hang(row, dc))
            xa()
    tam.replace(dich)
    return dict(tk)


# --------------------------------------------------------------------------------------------------------------------
# 4. Loại bỏ, gom vụ, chia tập
# --------------------------------------------------------------------------------------------------------------------
def loai_bo(ban_ghi: list[dict], so_ky_tu_toi_thieu: int = SO_KY_TU_TOI_THIEU, cap_giu: set[str] | None = None,
            chi_co_dieu_toi_pham: bool = False) -> tuple[list[dict], list[tuple[str, str]]]:
    """(giữ, [(ma, lý_do)]). Lý do đầu tiên gặp theo thứ tự: quyet_dinh, qua_ngan, cap_khong_giu, khong_co_dieu_toi_pham,
    trung_ma, trung_nguyen_van (giữ văn bản xuất hiện trước)."""
    giu, bo = [], []
    da_thay_md5: set[str] = set()
    da_thay_ma: set[str] = set()
    for b in ban_ghi:
        if b["loai_van_ban"] != "ban_an":
            ly_do = "quyet_dinh"
        elif b["so_ky_tu"] < so_ky_tu_toi_thieu:
            ly_do = "qua_ngan"
        elif cap_giu is not None and b["cap"] not in cap_giu:
            ly_do = "cap_khong_giu"
        elif chi_co_dieu_toi_pham and not b["co_dieu_toi_pham"]:
            ly_do = "khong_co_dieu_toi_pham"
        elif b["ma"] in da_thay_ma:
            ly_do = "trung_ma"
        elif b["md5"] in da_thay_md5:
            ly_do = "trung_nguyen_van"
        else:
            ly_do = None
        if ly_do:
            bo.append((b["ma"], ly_do))
            continue
        da_thay_ma.add(b["ma"])
        da_thay_md5.add(b["md5"])
        giu.append(b)
    return giu, bo


NGUONG_UNG_VIEN = 3      # một tham chiếu khớp nhiều hơn số này văn bản sơ thẩm thì coi là mơ hồ, không nối


def gom_vu(ban_ghi: list[dict]) -> tuple[dict[str, str], dict]:
    """(ma -> khóa nhóm, thống kê nối). Hai việc nối: (a) bản án CẤP TRÊN (phúc thẩm, giám đốc thẩm, tái thẩm, chưa rõ cấp) nêu bản án
    sơ thẩm (số + năm + ngày) khớp 1..3 bản án sơ thẩm đang có -> cùng nhóm; (b) cùng (số bản án, tòa, ngày) -> cùng nhóm
    (cùng bản án đăng hai lần với chữ khác nhau). Bản án sơ thẩm không bao giờ đi nối theo tham chiếu của chính nó (xem đầu file)."""
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

    theo_khoa: dict[tuple, list[str]] = {}
    theo_ban_an: dict[tuple, str] = {}
    for b in ban_ghi:
        sn = so_va_nam(b["so_chuan"])
        if b["cap"] == "so_tham" and sn and b["ngay"]:
            theo_khoa.setdefault((sn[0], sn[1], b["ngay"]), []).append(b["ma"])
        k = (b["so_chuan"], b["toa_an"], b["ngay"])
        if b["so_chuan"] and b["toa_an"] and b["ngay"]:
            if k in theo_ban_an:
                noi(b["ma"], theo_ban_an[k])
            else:
                theo_ban_an[k] = b["ma"]
    tk = Counter()
    for b in ban_ghi:
        if b["cap"] == "so_tham":
            continue
        tk["cap_tren"] += 1
        if not b["tham_chieu_so_tham"]:
            tk["khong_nua_so_tham"] += 1
            continue
        da_noi = False
        for r in b["tham_chieu_so_tham"]:
            so, nam, ngay = r.split("|")
            ung_vien = theo_khoa.get((int(so), int(nam), ngay), [])
            if not ung_vien:
                tk["khong_tim_thay_so_tham"] += 1
            elif len(ung_vien) > NGUONG_UNG_VIEN:
                tk["mo_ho"] += 1
            else:
                for u in ung_vien:
                    noi(b["ma"], u)
                da_noi = True
        tk["da_noi_voi_so_tham" if da_noi else "khong_noi_duoc"] += 1
    return {m: goc(m) for m in cha}, dict(tk)


def _bam(seed: int, khoa_nhom: str) -> float:
    return int(hashlib.sha256(f"{seed}:{khoa_nhom}".encode()).hexdigest()[:12], 16) / 16 ** 12


def chia_tap(nhom: dict[str, str], ti_le_test: float = 0.3, seed: int = 2026) -> dict[str, str]:
    """ma -> 'train' | 'test'. Cả nhóm vào một tập: test nếu băm(seed, khóa nhóm) < ti_le_test."""
    return {m: ("test" if _bam(seed, k) < ti_le_test else "train") for m, k in nhom.items()}


def kiem_ro_ri(ban_ghi: list[dict], tap: dict[str, str]) -> dict:
    """Kiểm LẠI sau khi chia, viết riêng khỏi gom_vu: mọi cặp (bản án cấp trên, sơ thẩm khớp 1..3 văn bản) có nằm khác tập không;
    trùng nguyên văn và trùng mã giữa hai tập. Chỉ xét bản án cấp trên: tham chiếu trong bản án sơ thẩm không phải cùng vụ."""
    theo_khoa: dict[tuple, list[str]] = {}
    for b in ban_ghi:
        sn = so_va_nam(b["so_chuan"])
        if b["cap"] == "so_tham" and sn and b["ngay"]:
            theo_khoa.setdefault((sn[0], sn[1], b["ngay"]), []).append(b["ma"])
    cap_khac_tap, cap_kiem = 0, 0
    for b in ban_ghi:
        if b["cap"] == "so_tham":
            continue
        for r in b["tham_chieu_so_tham"]:
            so, nam, ngay = r.split("|")
            uv = theo_khoa.get((int(so), int(nam), ngay), [])
            if 1 <= len(uv) <= NGUONG_UNG_VIEN:
                for u in uv:
                    cap_kiem += 1
                    cap_khac_tap += tap[u] != tap[b["ma"]]
    md5_tap: dict[str, set[str]] = {}
    for b in ban_ghi:
        md5_tap.setdefault(b["md5"], set()).add(tap[b["ma"]])
    return {"cap_tren_so_tham_kiem": cap_kiem, "cap_tren_so_tham_khac_tap": cap_khac_tap,
            "md5_o_ca_hai_tap": sum(1 for s in md5_tap.values() if len(s) > 1),
            "ma_o_ca_hai_tap": len(ban_ghi) - len({b["ma"] for b in ban_ghi})}


def thong_ke_tap(ban_ghi: list[dict], tap: dict[str, str], nhom: dict[str, str]) -> dict:
    """Số liệu để xem hai tập có cân đối không (cấp, tòa, năm, Điều phổ biến) và Điều nào chỉ có ở một tập."""
    ra: dict = {}
    dieu_tap: dict[str, Counter] = {}
    for t in ("train", "test"):
        bg = [b for b in ban_ghi if tap[b["ma"]] == t]
        dieu = Counter(d for b in bg for d in b["dieu_blhs"])
        dieu_tap[t] = dieu
        ra[t] = {
            "so_van_ban": len(bg),
            "so_nhom_vu": len({nhom[b["ma"]] for b in bg}),
            "cap": dict(Counter(b["cap"] for b in bg).most_common()),
            "cap_toa": dict(Counter(b["cap_toa"] for b in bg).most_common()),
            "nam": dict(sorted(Counter(b["nam"] for b in bg).items(), key=lambda kv: (kv[0] is None, kv[0] or 0))),
            "co_dieu_toi_pham": sum(b["co_dieu_toi_pham"] for b in bg),
            "nhac_blhs_1999": sum(b["nhac_blhs_1999"] for b in bg),
            "nhac_blhs_2015": sum(b["nhac_blhs_2015"] for b in bg),
            "so_ky_tu_trung_binh": round(sum(b["so_ky_tu"] for b in bg) / max(len(bg), 1)),
            "dieu_pho_bien": dict(dieu.most_common(10)),
        }
    ra["dieu_chi_o_test"] = sorted(set(dieu_tap["test"]) - set(dieu_tap["train"]), key=int)
    ra["dieu_chi_o_train"] = sorted(set(dieu_tap["train"]) - set(dieu_tap["test"]), key=int)
    tong = len(ban_ghi)
    ra["ti_le_test_thuc_te"] = round(ra["test"]["so_van_ban"] / tong, 4) if tong else None
    return ra


# --------------------------------------------------------------------------------------------------------------------
# 5. Ghi
# --------------------------------------------------------------------------------------------------------------------
COT_JSONL = ("ma", "tap", "nhom_vu", "so_ban_an", "toa_an", "cap_toa", "ngay", "nam", "cap", "cap_cong_thong_tin", "cap_theo_van_ban",
             "mau_thuan_cap", "ma_loai", "dieu_blhs", "dieu_khoan_diem_blhs", "co_dieu_toi_pham", "nhac_blhs_1999", "nhac_blhs_2015",
             "tham_chieu_so_tham", "so_ky_tu", "md5", "url_web", "url_pdf", "van_ban")


class GhiGz:
    """Ghi *.jsonl.gz xác định (không ghi giờ vào đầu gzip) -> chạy lại cùng đầu vào cho đúng file cũ."""

    def __init__(self, path: Path):
        self._raw = path.open("wb")
        self._gz = gzip.GzipFile(filename="", mode="wb", fileobj=self._raw, compresslevel=6, mtime=0)
        self.n = 0

    def ghi(self, d: dict) -> None:
        self._gz.write((json.dumps({k: d[k] for k in COT_JSONL}, ensure_ascii=False) + "\n").encode("utf-8"))
        self.n += 1

    def dong(self) -> None:
        self._gz.close()
        self._raw.close()


def doc_jsonl_gz(path: str | Path):
    """Đọc lại file đã ghi: yield từng dict."""
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for dong in f:
            yield json.loads(dong)


def ghi_tap(file_loc: list[Path], giu: set[str], tap: dict[str, str], nhom: dict[str, str], ra: Path,
            kich_thuoc_lo: int = 2000) -> dict[str, int]:
    """Đọc lại các file lọc theo lô, ghi train.jsonl.gz / test.jsonl.gz theo thứ tự shard rồi thứ tự hàng."""
    import pyarrow.parquet as pq  # noqa: PLC0415
    w = {t: GhiGz(ra / f"{t}.jsonl.gz") for t in ("train", "test")}
    try:
        for f in file_loc:
            for lo in pq.ParquetFile(str(f)).iter_batches(batch_size=kich_thuoc_lo):
                for row in lo.to_pylist():
                    if row["ma"] in giu:
                        row["tap"], row["nhom_vu"] = tap[row["ma"]], nhom[row["ma"]]
                        w[row["tap"]].ghi(row)
    finally:
        for x in w.values():
            x.dong()
    return {t: x.n for t, x in w.items()}
