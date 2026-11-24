"""Bản án cbba đã lọc + chia (src/ban_an/cbba_blhs.py) -> nhãn «sự việc -> Điều BLHS» + che đáp án, bằng đúng bộ xử lý của anle_hf.

Vào : inbox/cbba_blhs/train.jsonl.gz, test.jsonl.gz (mỗi dòng đã có `tap` và `nhom_vu`).
Ra  : cùng cột như scripts/xu_ly_anle_hf.py (ma, tap, nhom_vu, dau_vao, dieu, toi_danh, nguon_nhan, cap, so_ban_an, ngay)
      để các bước sau dùng được cho cả hai nguồn.
KHÔNG chia lại: tập của từng văn bản giữ nguyên như cbba_blhs đã chia (cả nhóm vụ nằm trọn một tập).
Cấp xét xử ở đây là cấp do bộ tách tach.py đọc (HS-ST / HS-PT…), như anle_hf, không phải cột `cap` của cbba_blhs.
Không gom thêm theo «sự việc gần trùng» như anle_hf.gom_vu (so từng cặp: không làm nổi với hàng trăm nghìn văn bản).
Chỉ dùng thư viện chuẩn + anle_hf (+ vài hàm của tach).

Thứ tự xử lý một văn bản (xu_ly_mot):
  1. bo_dau_trang                    bỏ các dòng «## Page N» do trích PDF (không còn nằm trong đầu vào của mô hình)
  2. anle_hf.xu_ly                   tách bốn phần, nhãn, che đáp án, dò lộ nhãn (đúng bộ xử lý của nguồn anle)
  3. cat_phan_vks                    đầu vào chỉ giữ phần diễn biến vụ việc: cắt tại mốc đầu tiên của phần Viện kiểm sát truy tố / đề nghị mức án
                                     (nhãn vẫn là phần QUYẾT ĐỊNH của Tòa án; phần truy tố / đề nghị của Viện kiểm sát không dùng làm đầu vào)
  4. bo_cau_phan_quyet_con_sot       chạy lại bộ bỏ câu phán quyết: bản gốc không bỏ được câu bị ngắt bằng dòng trống
  5. kiem_lo_them                    bắt thêm tên tội sau chữ «tội danh» / ngoặc «...» mà bộ dò của anle_hf bỏ sót
  6. loai_neu_lo                     còn dấu hiệu lộ nhãn -> loại khỏi train / test, ghi lý do `lo_nhan_con_lai`
Bước 3-6 là bổ sung cho dữ liệu cbba (bản án sơ thẩm có phần truy tố / luận tội, văn bản trích PDF); không sửa gì trong anle_hf.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from src.ban_an import anle_hf as hf
from src.ban_an.cbba_blhs import CAP_CONG_THONG_TIN
from src.ban_an.tach import _mem, tim_pii

CAP_EN = {v: k for k, v in CAP_CONG_THONG_TIN.items()}          # 'so_tham' -> 'First-instance'
COT_JSONL = ("ma", "tap", "nhom_vu", "dau_vao", "dieu", "toi_danh", "nguon_nhan", "cap", "so_ban_an", "ngay")
_RE_MA = re.compile(r'^\{"ma": "([^"]*)"')
TEN_TAP = ("train", "test")


def ma_trong_dong(dong: str) -> str:
    """Mã văn bản ở đầu một dòng jsonl do cbba_blhs.GhiGz ghi (khóa đầu tiên luôn là «ma»), không phải parse cả dòng."""
    m = _RE_MA.match(dong)
    if not m:
        raise ValueError(f"dòng không bắt đầu bằng {{\"ma\": ...}}: {dong[:60]!r}")
    return m.group(1)


def _bam(seed: int, ma: str) -> str:
    return hashlib.sha256(f"{seed}:{ma}".encode()).hexdigest()


def chon_ma(cac_ma: list[str], toi_da: int | None, seed: int) -> set[str] | None:
    """None = lấy hết. Còn lại: `toi_da` mã đứng đầu theo băm sha256(seed:ma) (cố định, không phụ thuộc thứ tự đọc)."""
    if toi_da is None or toi_da >= len(cac_ma):
        return None
    return set(sorted(cac_ma, key=lambda m: _bam(seed, m))[:toi_da])


def doc_dong(path: str | Path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        yield from f


def liet_ke_ma(path: str | Path) -> list[str]:
    return [ma_trong_dong(d) for d in doc_dong(path)]


def doc_tap(path: str | Path, giu: set[str] | None):
    """Yield dict từng dòng; chỉ parse dòng có mã nằm trong `giu` (None = mọi dòng)."""
    for d in doc_dong(path):
        if giu is None or ma_trong_dong(d) in giu:
            yield json.loads(d)


# --- xử lý một văn bản (hàm cấp module để multiprocessing gửi được) ---------------------------------------------------
_TEN_TOI: tuple[str, ...] = ()


def khoi_tao(ten_toi: tuple[str, ...]) -> None:
    global _TEN_TOI
    _TEN_TOI = tuple(ten_toi)


# Văn bản cbba là markdown trích từ PDF: mỗi trang mở đầu bằng một dòng «## Page N» (mọi văn bản đều có), nằm giữa hai dòng trống.
# Dấu ngắt trang cắt đôi câu («Đề nghị không / ## Page 5 / áp dụng hình phạt bổ sung») nên bộ che đáp án của anle_hf, vốn tách câu theo dòng,
# không bỏ được câu phán quyết nằm vắt qua trang -> lộ nhãn. Bỏ dấu ngắt trang, giữ một dấu xuống dòng (dòng nối giữa câu được nối lại ở anle_hf).
_RE_DONG_DAU_TRANG = re.compile(r"[ \t]*##[ \t]*Page[ \t]*\d+[ \t]*", re.I)


def bo_dau_trang(van: str) -> str:
    """Bỏ các dòng «## Page N» cùng các dòng trống quanh chúng; chỗ đó còn lại một dấu xuống dòng. Duyệt từng dòng nên thời gian tuyến tính."""
    ra: list[str] = []
    bo_dong_trong = True                                 # đầu văn bản: bỏ dòng trống mở đầu
    for dong in van.split("\n"):
        if _RE_DONG_DAU_TRANG.fullmatch(dong):
            while ra and not ra[-1].strip():
                ra.pop()
            bo_dong_trong = True
        elif bo_dong_trong and not dong.strip():
            continue
        else:
            bo_dong_trong = False
            ra.append(dong)
    return "\n".join(ra)


LUOT_BO_CAU_TOI_DA = 3
LY_DO_LO_NHAN = "lo_nhan_con_lai"


def _dat_dau_vao(b: dict, t: str, ten_toi_blhs: tuple[str, ...]) -> None:
    """Đặt lại `dau_vao` và tính lại mọi trường suy ra từ nó (băm, dấu hiệu lộ nhãn, dữ liệu cá nhân, tên tội trong lời kể, độ dài tối thiểu)."""
    b["dau_vao"] = t
    b["hash_dau_vao"] = hf.hash_van(t)
    b["ro_ri_sau_che"] = hf.con_lo(t, b["dieu"], b["toi_danh"], ten_toi_blhs)
    b["pii_sau_che"] = tim_pii(t)
    b["lo_nhan_con_lai"] = {k: v for k, v in b["ro_ri_sau_che"].items() if k in hf.LO_NHAN}
    b["ten_toi_trong_loi_ke"] = sum(len(re.findall(r"(?<!\w)" + _mem(x) + r"(?!\w)", t, re.I)) for x in set(b["toi_danh"]))
    if len(t) < hf.DAU_VAO_TOI_THIEU:
        b["dung_duoc"], b["ly_do"] = False, "dau_vao_qua_ngan"


# Bản án sơ thẩm: NỘI DUNG VỤ ÁN = (A) diễn biến vụ việc -> (B) «Tại bản cáo trạng số ... truy tố ... về tội ... theo Điều ...» -> (C) «Tại phiên tòa, đại diện
# Viện kiểm sát giữ nguyên quan điểm truy tố, đề nghị áp dụng Điều ..., xử phạt ...» -> (D) lời khai, bào chữa, nói lời sau cùng. (B) và (C) chính là đáp án
# của Viện kiểm sát; đáp án của Tòa án nằm ở phần QUYẾT ĐỊNH, đã tách riêng. Đầu vào chỉ giữ (A): cắt thẳng tại mốc đầu tiên của (B) / (C) thay vì che từng câu.
# Bản án phúc thẩm: tach.py đã đưa phần chép lại bản án sơ thẩm ra khỏi phần sự việc nên thường không còn mốc nào, và giữ nguyên.
MIN_GIU_TRUOC_MOC = 300         # ký tự: mốc nào khiến phần giữ lại ngắn hơn thế thì bỏ qua (cáo trạng dùng để mở đầu lời kể: «Theo cáo trạng của VKS, bị cáo ...»)
_RE_MOC_VKS = re.compile(
    r"(?:Tại\s+)?(?:b[ảa]n\s+)?[Cc]\s?áo\s*trạng\s+(?:số|ngày|của)"                                     # «Tại bản cáo trạng số 25/CT-VKS ngày ...»
    r"|(?-i:Tại)\s+phiên\s+t[òo]a"                                                                      # «Tại phiên tòa, ...» đầu câu (không phải «diễn biến tại phiên tòa»)
    r"|truy\s+tố[^.]{0,200}?(?:về\s+tội|theo\s+(?:điểm|khoản|điều|quy\s+định))"                         # «Viện kiểm sát ... truy tố bị cáo về tội ...»
    r"|đề\s+nghị[^.]{0,80}?(?:Hội\s+đồng\s+xét\s+xử|HĐXX)|luận\s+tội|quan\s+điểm\s+truy\s+tố", re.I)   # đề nghị của Viện kiểm sát với Hội đồng xét xử
_RE_HET_CAU = re.compile(r"[.!?:;][\"”’)]?\s+")


def cat_truoc_truy_to(t: str) -> tuple[str, bool]:
    """(phần diễn biến vụ việc, đã cắt?). Cắt tại đầu câu chứa mốc đầu tiên của phần truy tố / đề nghị của Viện kiểm sát; mốc nằm trong
    MIN_GIU_TRUOC_MOC ký tự đầu thì bỏ qua. Không có mốc hợp lệ -> trả nguyên văn bản."""
    for m in _RE_MOC_VKS.finditer(t):
        q = 0
        for h in _RE_HET_CAU.finditer(t, 0, m.start()):
            q = h.end()
        if q >= MIN_GIU_TRUOC_MOC:
            return t[:q].rstrip(), True
    return t, False


def cat_phan_vks(b: dict, ten_toi_blhs: tuple[str, ...] = ()) -> dict:
    """Áp cat_truoc_truy_to lên `dau_vao` của bản ghi dùng được rồi tính lại các trường suy ra. `cat_phan_vks` ghi True / False; `so_ky_tu_truoc_cat` ghi độ dài trước khi cắt."""
    if not b["dung_duoc"]:
        return b
    t, cat = cat_truoc_truy_to(b["dau_vao"])
    b["cat_phan_vks"] = cat
    if cat:
        b["so_ky_tu_truoc_cat"] = len(b["dau_vao"])
        _dat_dau_vao(b, t, ten_toi_blhs)
    return b


def bo_cau_phan_quyet_con_sot(b: dict, ten_toi_blhs: tuple[str, ...] = ()) -> dict:
    """Chạy lại hf.bo_cau_phan_quyet trên đầu vào đã che, tối đa LUOT_BO_CAU_TOI_DA lượt, rồi tính lại mọi trường suy ra từ `dau_vao`.

    Lý do: văn bản trích từ PDF hay ngắt câu bằng dòng trống («Đề nghị Hội đồng xét xử:» / dòng trống / «Tuyên bố ...»). hf.bo_cau_phan_quyet nối dòng
    bị ngắt bằng cách đổi dấu xuống dòng (không đứng sau . ! ? :) thành dấu cách, nên với «\\n\\n » nó chỉ đổi dấu xuống dòng thứ hai: câu vẫn nằm trên hai dòng,
    không dòng nào đủ để bị bỏ, trong khi bộ dò hf.con_lo tìm trên cả văn bản và báo lộ nhãn. Lượt sau nối được hai dòng rồi bỏ câu.
    Chỉ đụng tới bản ghi dùng được; bản ghi không có câu nào để bỏ giữ nguyên từng ký tự."""
    if not b["dung_duoc"]:
        return b
    t, tong = b["dau_vao"], 0
    for _ in range(LUOT_BO_CAU_TOI_DA):
        t2, n = hf.bo_cau_phan_quyet(t)
        if not n:
            break
        t, tong = t2, tong + n
    if not tong:
        return b
    b["da_che"] = {**b["da_che"], "cau_phan_quyet": b["da_che"].get("cau_phan_quyet", 0) + tong}
    b["cau_phan_quyet_bo_them"] = tong
    _dat_dau_vao(b, t, ten_toi_blhs)
    return b


NAM_AP_DUNG_BLHS_2015 = 2018        # BLHS 2015 có hiệu lực thi hành từ 01/01/2018 (Nghị quyết 41/2017/QH14)
LY_DO_TRUOC_NAM = "truoc_nam_ap_dung_blhs_2015"


def nam_ban_an(b: dict) -> int | None:
    """Năm của bản án: ngày ghi trong văn bản (do bộ tách đọc, dạng 'YYYY-MM-DD') nếu có, không thì năm trên cổng thông tin (`nam`)."""
    ngay = b.get("ngay")
    if isinstance(ngay, str) and re.match(r"\d{4}-\d{2}-\d{2}", ngay):
        return int(ngay[:4])
    nam = b.get("nam")
    return int(nam) if nam else None


def loai_truoc_nam(b: dict, tu_nam: int | None = NAM_AP_DUNG_BLHS_2015) -> dict:
    """Bản án xét xử trước `tu_nam` thì số Điều ở nhãn là số Điều của BLHS 1999 (Điều 138 = trộm cắp, Điều 194 = ma túy), không phải BLHS 2015 mà nhãn
    của cả bộ dữ liệu giả định -> loại. Đo trên mẫu 6.000 bản án: 15 / 3.905 văn bản dùng được. Không rõ năm thì giữ."""
    if b["dung_duoc"] and tu_nam:
        n = nam_ban_an(b)
        if n is not None and n < tu_nam:
            b["dung_duoc"], b["ly_do"] = False, LY_DO_TRUOC_NAM
    return b


_DAU_NGOAC = r"[«»‹›'‘’`´\"“”„]"


def kiem_lo_them(b: dict) -> dict:
    """Bộ dò của anle_hf bỏ sót tên tội của nhãn đứng ngay sau chữ «tội» / «tội danh» khi có dấu ngoặc lạ («Trộm cắp tài sản») hoặc khi có chữ «danh»
    (bộ che chỉ nhận «tội “...”» bằng ngoặc kép thẳng / cong). Đo trên mẫu 2.000 bản án cbba: 15 / 1.349 văn bản dùng được. Thêm khóa
    `ten_toi_sau_chu_toi` vào lo_nhan_con_lai để cùng đi qua một cổng với các dấu hiệu lộ nhãn khác."""
    if not b["dung_duoc"]:
        return b
    n = sum(len(re.findall(r"tội\s*(?:danh)?\s*:?\s*" + _DAU_NGOAC + r"?\s*" + _mem(x), b["dau_vao"], re.I)) for x in set(b["toi_danh"]))
    if n:
        b["lo_nhan_con_lai"] = {**b["lo_nhan_con_lai"], "ten_toi_sau_chu_toi": n}
    return b


def loai_neu_lo(b: dict) -> dict:
    """Văn bản còn dấu hiệu lộ nhãn sau khi che thì không đưa vào train / test (đầu vào chứa đáp án làm hỏng cả huấn luyện lẫn đánh giá).
    Bản ghi giữ nguyên `lo_nhan_con_lai` để thống kê theo kiểu."""
    if b["dung_duoc"] and b["lo_nhan_con_lai"]:
        b["dung_duoc"], b["ly_do"] = False, LY_DO_LO_NHAN
    return b


def xu_ly_mot(args: tuple[int, dict]) -> dict:
    """(số thứ tự, dòng cbba_blhs) -> bản ghi của anle_hf.xu_ly, thêm tap / nhom_vu / nam của cbba_blhs. Không ném lỗi."""
    stt, d = args
    row = {"markdown": bo_dau_trang(d["van_ban"]), "doc_name": d["ma"], "instance_level": CAP_EN.get(d.get("cap_cong_thong_tin") or "")}
    b = loai_neu_lo(kiem_lo_them(bo_cau_phan_quyet_con_sot(cat_phan_vks(hf.xu_ly(row, stt, _TEN_TOI), _TEN_TOI), _TEN_TOI)))
    b["tap"], b["nhom_vu"], b["nam"] = d["tap"], d["nhom_vu"], d.get("nam")
    return b


def thong_ke(ban_ghi: list[dict], loai: list[dict], dau_vao: dict[str, int]) -> dict:
    dieu_tap = {t: Counter(x for b in ban_ghi if b["tap"] == t for x in b["dieu"]) for t in TEN_TAP}
    tat_ca = Counter(x for b in ban_ghi for x in b["dieu"])
    tong = len(ban_ghi) + len(loai)
    return {
        "dau_vao": dau_vao,
        "da_xu_ly": tong,
        "dung_duoc": len(ban_ghi),
        "ti_le_dung_duoc": round(len(ban_ghi) / tong, 4) if tong else None,
        "dung_duoc_theo_tap": {t: sum(1 for b in ban_ghi if b["tap"] == t) for t in TEN_TAP},
        "ly_do_loai": dict(Counter(b["ly_do"] for b in loai).most_common()),
        "cap_bo_tach": dict(Counter(b["cap"] for b in ban_ghi).most_common()),
        "nguon_nhan": dict(Counter(b["nguon_nhan"] for b in ban_ghi).most_common()),
        "so_toi_moi_van_ban": dict(sorted(Counter(min(len(b["dieu"]), 3) for b in ban_ghi).items())),
        "so_dieu_khac_nhau": len(tat_ca),
        "dieu_pho_bien": dict(tat_ca.most_common(10)),
        "dieu_chi_o_test": sorted(set(dieu_tap["test"]) - set(dieu_tap["train"]), key=lambda x: (len(x), x)),
        "so_dieu_chi_o_train": len(set(dieu_tap["train"]) - set(dieu_tap["test"])),
        "bi_loai_vi_lo_nhan_theo_kieu": dict(sum((Counter(b.get("lo_nhan_con_lai") or {}) for b in loai if b["ly_do"] == LY_DO_LO_NHAN), Counter()).most_common()),
        "van_ban_da_cat_phan_vks": sum(1 for b in ban_ghi if b.get("cat_phan_vks")),
        "ti_le_giu_lai_sau_cat_trung_vi": (lambda r: round(r[len(r) // 2], 3) if r else None)(
            sorted(len(b["dau_vao"]) / b["so_ky_tu_truoc_cat"] for b in ban_ghi if b.get("cat_phan_vks"))),
        "van_ban_con_lo_nhan": sum(1 for b in ban_ghi if b["lo_nhan_con_lai"]),
        "van_ban_co_ro_ri_truoc_che": sum(1 for b in ban_ghi if b["ro_ri_truoc_che"]),
        "van_ban_con_truy_to_tran": sum(1 for b in ban_ghi if b["ro_ri_sau_che"].get("truy_to")),
        "van_ban_nhac_ten_toi_trong_loi_ke": sum(1 for b in ban_ghi if b["ten_toi_trong_loi_ke"]),
        "van_ban_con_du_lieu_ca_nhan": sum(1 for b in ban_ghi if b["pii_sau_che"]),
        "da_che": dict(sum((Counter(b["da_che"]) for b in ban_ghi), Counter())),
    }


def ghi_jsonl(path: Path, ds: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for b in ds:
            f.write(json.dumps({k: b[k] for k in COT_JSONL}, ensure_ascii=False) + "\n")
