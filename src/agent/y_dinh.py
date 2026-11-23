"""Phân loại câu người dùng thành Ý ĐỊNH + THAM SỐ, bằng luật (regex), KHÔNG dùng LLM.

Khác kế hoạch v2 mục 14 (ở đó bước phân loại và trích tham số do «LLM local nhỏ» làm): các dạng câu của chức năng 1 có hình thức rất
rõ (có số Điều, có ngày, có từ «lịch sử», «so sánh»…) nên luật đủ dùng, và có ba lợi ích: chạy được khi KHÔNG có Ollama, kết quả
xác định (cùng câu → cùng ý định, kiểm thử được), không thêm một mô hình có thể phân loại sai. Chỗ duy nhất cần LLM là tách hành
vi trong tình huống dài (src/index/tach_hanh_vi.py), nằm ở lớp công cụ chứ không ở đây.

Ý định (hằng số bên dưới):
  tra_dieu      «Điều 173», «Điều 173 BLHS 2015 tại ngày 1/1/2018», «khoản 2 Điều 173»
  lich_su       «lịch sử Điều 173», «Điều 173 đã được sửa đổi những lần nào»
  so_sanh       «so sánh Điều 173 năm 2017 và hiện nay», «Điều 173 khác gì bản gốc»
  quan_he       «những luật nào đã sửa đổi Bộ luật Hình sự»
  chuyen_tiep   «điều khoản chuyển tiếp của luật sửa đổi»
  tim_mo_ta     mô tả ngắn bằng lời thường: «lén lấy xe máy của hàng xóm»
  tinh_huong    đoạn dài kể nhiều việc: tách thành từng hành vi rồi tìm Điều cho từng hành vi
  ngoai_pham_vi hỏi một luật khác BLHS (kho chỉ có BLHS)
  tro_giup      chào hỏi, «bạn làm được gì»
  trong         không có chữ nào

Mọi so khớp từ khoá làm trên bản đã BỎ DẤU (người dùng gõ «dieu 173», «lich su» vẫn hiểu).
"""
from __future__ import annotations

import calendar
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date

TRA_DIEU = "tra_dieu"
LICH_SU = "lich_su"
SO_SANH = "so_sanh"
QUAN_HE = "quan_he"
CHUYEN_TIEP = "chuyen_tiep"
TIM_MO_TA = "tim_mo_ta"
TINH_HUONG = "tinh_huong"
NGOAI_PHAM_VI = "ngoai_pham_vi"
TRO_GIUP = "tro_giup"
TRONG = "trong"
LOAI = (TRA_DIEU, LICH_SU, SO_SANH, QUAN_HE, CHUYEN_TIEP, TIM_MO_TA, TINH_HUONG, NGOAI_PHAM_VI, TRO_GIUP, TRONG)

TOI_DA_TU_THAM_CHIEU = 25      # câu có số Điều mà dài hơn ngưỡng này (và không hỏi lịch sử/so sánh) coi là tình huống kể chuyện
TU_TOI_THIEU_TINH_HUONG = 12   # từ 12 từ trở lên đi qua bước tách hành vi (câu «don» của bộ đo dài 5–41 từ, trung vị 25)
TOI_DA_DIEU = 5                # số Điều tối đa xử lý trong một câu «Điều 1, Điều 2…»

# Mốc đặc biệt chưa biết ngày cụ thể; lớp agent đổi sang ngày thật theo kho luật.
MOC_GOC = "GOC"                # «bản gốc», «lúc ban hành»: ngày bắt đầu hiệu lực của văn bản
MOC_HOM_NAY = "HOM_NAY"        # «hiện nay», «hiện hành»

VI_DU = (
    "Điều 173",
    "Lịch sử sửa đổi Điều 173",
    "So sánh Điều 173 bản gốc và hiện hành",
    "Điều 173 có hiệu lực tại ngày 01/01/2019",
    "lén lấy xe máy của hàng xóm",
    "Những luật nào đã sửa đổi Bộ luật Hình sự?",
)


def chuan_hoa(s: str) -> str:
    """NFC (bàn phím Windows/Mac có thể cho dạng tổ hợp), chữ thường, gộp khoảng trắng."""
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s or "")).strip().lower()


def bo_dau(s: str) -> str:
    out = []
    for c in s:
        if c in "đĐ":
            out.append("d" if c == "đ" else "D")
            continue
        out.append("".join(x for x in unicodedata.normalize("NFD", c) if unicodedata.category(x) != "Mn"))
    return "".join(out)


@dataclass(frozen=True)
class Moc:
    """Một mốc thời gian người dùng nêu. `iso` là ngày dùng để tra; nếu chỉ nêu tháng/năm thì là NGÀY CUỐI kỳ
    (trạng thái cuối kỳ), `tu` là ngày đầu kỳ, để lớp trên báo «trong kỳ này có sửa đổi…»."""
    iso: str
    tu: str
    kieu: str          # 'ngay' | 'thang' | 'nam' | 'goc' | 'hom_nay'
    goc: str           # chữ người dùng gõ

    @property
    def la_ngay_that(self) -> bool:
        return self.iso not in (MOC_GOC, MOC_HOM_NAY)


@dataclass
class YDinh:
    loai: str
    cau: str
    dieu: list[str] = field(default_factory=list)      # ['173'] (chữ thường: '173a')
    viet_tat: str | None = None                        # 'BLHS' nếu người dùng nêu
    nam_van_ban: int | None = None                     # năm của văn bản nếu nêu («BLHS 2015»)
    khoan: str | None = None
    diem: str | None = None
    moc: list[Moc] = field(default_factory=list)
    mo_ta: str = ""                                    # chữ dùng để tìm (tim_mo_ta / tinh_huong)
    luu_y: list[str] = field(default_factory=list)     # điều nên nói với người dùng về cách câu của họ được hiểu
    van_ban_khac: str | None = None                    # tên luật khác BLHS được nhắc tới
    xin_ket_luan: bool = False                         # câu hỏi dạng «có tội không / bị phạt bao nhiêu năm»


# ---------------------------------------------------------------------------------------------------------------------
# Từ khoá (đã bỏ dấu)

_SO_SANH = ("so sanh", "khac gi", "khac nhau", "khac the nao", "thay doi gi", "thay doi nhu the nao", "truoc va sau", "so voi ban",
            "so voi truoc", "ban cu va ban moi", "cu va moi", "cu so voi moi", "khac so voi")
_LICH_SU = ("lich su", "sua doi", "duoc sua", "da sua", "bi sua", "thay doi", "qua cac thoi ky", "cac lan sua", "dong thoi gian",
            "timeline", "tung duoc sua", "bo sung", "nhung lan")
_CHUYEN_TIEP = ("chuyen tiep", "hoi to", "hieu luc tro ve truoc", "ap dung hoi to")
_QUAN_HE = (re.compile(r"(?:van ban|luat|nghi quyet)\s+(?:nao\s+)?(?:da\s+|dang\s+|co\s+)?(?:sua doi|bo sung|hoan hieu luc)"),
            re.compile(r"(?:bo luat hinh su|blhs)\s+(?:da\s+)?(?:duoc|bi)\s+sua"),
            re.compile(r"quan he van ban|cac van ban lien quan|van ban lien quan"))
_KET_LUAN = ("co toi khong", "co pham toi khong", "co vi pham khong", "bi phat bao nhieu", "di tu bao nhieu", "ngoi tu bao nhieu",
             "an bao nhieu", "muc an", "co bi di tu khong", "co di tu khong", "co bi khoi to khong", "co thang khong", "toi nen lam gi",
             "toi phai lam gi", "co can thiet phai thue luat su", "se bi xu", "co bi bat khong")
_CHAO = re.compile(r"^(?:xin chao|chao ban|chao|hello|hi|alo|hey)\b")
_TRO_GIUP = re.compile(r"\b(?:ban lam duoc gi|ban la ai|huong dan|cach dung|cach su dung|giup toi|tro giup|help|su dung nhu the nao|dung nhu the nao)\b")

_BLHS = re.compile(r"\b(?:blhs|bo luat hinh su|luat hinh su)\b")
_LUAT_KHAC = (
    (re.compile(r"\bblds\b|bo luat dan su|luat dan su"), "Bộ luật Dân sự"),
    (re.compile(r"\bbltths\b|\bbltt\s*hs\b|to tung hinh su"), "Bộ luật Tố tụng hình sự"),
    (re.compile(r"\bbltt?ds\b|to tung dan su"), "Bộ luật Tố tụng dân sự"),
    (re.compile(r"\bblld\b|bo luat lao dong|luat lao dong"), "Bộ luật Lao động"),
    (re.compile(r"luat giao thong|luat trat tu,? an toan giao thong"), "Luật Giao thông"),
    (re.compile(r"luat dat dai"), "Luật Đất đai"),
    (re.compile(r"luat doanh nghiep"), "Luật Doanh nghiệp"),
    (re.compile(r"luat hon nhan"), "Luật Hôn nhân và gia đình"),
    (re.compile(r"luat thue|luat quan ly thue"), "Luật Thuế"),
    (re.compile(r"xu ly vi pham hanh chinh|\bxlvphc\b"), "Luật Xử lý vi phạm hành chính"),
    (re.compile(r"luat thi hanh an"), "Luật Thi hành án"),
    (re.compile(r"\bnghi dinh\b"), "Nghị định"),
    (re.compile(r"\bthong tu\b"), "Thông tư"),
)
# lĩnh vực nằm ngoài BLHS nhưng KHÔNG chắc chắn (có thể vẫn là hình sự): chỉ nhắc, không chặn
_NGOAI_LINH_VUC = (
    ("dân sự, hôn nhân – gia đình, thừa kế", ("ly hon", "thua ke", "di chuc", "nuoi con sau ly hon", "chia tai san chung", "dang ky ket hon")),
    ("đất đai", ("tranh chap dat", "quyen su dung dat", "so do", "so hong", "sang ten dat")),
    ("lao động", ("hop dong lao dong", "sa thai", "tro cap thoi viec", "bao hiem xa hoi")),
    ("xử phạt hành chính", ("phat nguoi", "xu phat vi pham hanh chinh", "muc phat hanh chinh", "bien ban vi pham giao thong")),
    ("thuế", ("thue thu nhap", "quyet toan thue")),
)

# ---------------------------------------------------------------------------------------------------------------------
# Số Điều, khoản, điểm

_DIEU = re.compile(r"\bdieu\s*(\d{1,3}[a-z]?)(?![a-z0-9]|\s*/\s*\d)")        # «Điều 100/2015/QH13» là số hiệu văn bản, không phải Điều 100
_CHI_SO = re.compile(r"^(?:d\s*)?(\d{1,3}[a-z]?)$")
_KHOAN = re.compile(r"\bkhoan\s*(\d{1,2})\b")
_DIEM_F = re.compile(r"\bdiem\s*([a-z])\b")
_DIEM_G = re.compile(r"\bđiểm\s*([a-zđ])\b")

# ---------------------------------------------------------------------------------------------------------------------
# Ngày tháng

_SO_HIEU = re.compile(r"\b\d+\s*/\s*\d{4}\s*/\s*[a-z0-9\-]+\b")                              # 100/2015/QH13
_NAM_LUAT = re.compile(r"\b(?:blhs|bo luat hinh su|luat hinh su)\s*(?:nam\s*)?((?:19|20)\d{2})\b")
_ISO = re.compile(r"(?<!\d)((?:19|20)\d{2})-(\d{1,2})-(\d{1,2})(?!\d)")
_DMY = re.compile(r"(?<![\d/])(\d{1,2})\s*[/.\-]\s*(\d{1,2})\s*[/.\-]\s*((?:19|20)\d{2})(?!\d)")
_CHU_DMY = re.compile(r"\bngay\s*(\d{1,2})\s*thang\s*(\d{1,2})(?:\s*nam)?\s*((?:19|20)\d{2})\b")
_THANG_NAM = re.compile(r"\bthang\s*(\d{1,2})\s*(?:nam|/|-)?\s*((?:19|20)\d{2})\b")
_M_Y = re.compile(r"(?<![\d/.])(\d{1,2})\s*/\s*((?:19|20)\d{2})(?![\d/])")
_NAM = re.compile(r"\bnam\s*((?:19|20)\d{2})\b")
_NAM_TRAN = re.compile(r"\b(?:truoc|sau|tu|den|vao|luc|hoi|thoi diem|tai)\s+((?:19|20)\d{2})\b")
_GOC = re.compile(r"\b(?:ban goc|luc ban hanh|ban dau|khi moi ban hanh|nguyen van|phien ban dau)\b")
_HOM_NAY = re.compile(r"\b(?:hom nay|hien nay|hien hanh|hien tai|bay gio|moi nhat|dang co hieu luc|con hieu luc)\b")


def _hop_le(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def tim_moc(f: str, nam_da_co: frozenset[int] = frozenset(), *, co_dieu: bool = False) -> tuple[list[Moc], int | None, list[str], str]:
    """Tìm các mốc thời gian trong câu `f` (đã bỏ dấu, chữ thường). Trả (mốc, năm văn bản nếu nêu, lưu ý, phần còn lại của câu).
    Quy tắc chống nhầm: số hiệu «100/2015/QH13» và «BLHS 2015» không phải ngày; chỉ nhận năm trần khi có chữ «năm» hoặc
    «trước/sau/từ/đến/vào/lúc/tại» đứng trước; nếu chỉ có đúng một «năm X» mà X là năm của văn bản trong kho, và câu có số Điều,
    thì hiểu là năm của văn bản (vd «Điều 173 năm 2015»)."""
    luu_y: list[str] = []
    moc: list[Moc] = []
    f = _SO_HIEU.sub(" ", f)
    nam_luat: int | None = None
    m = _NAM_LUAT.search(f)
    if m:
        nam_luat = int(m.group(1))
        f = _NAM_LUAT.sub(" blhs ", f)

    def them_ngay(y: int, mo: int, d: int, goc: str) -> None:
        dt = _hop_le(y, mo, d)
        if dt is None:
            luu_y.append(f"Ngày «{goc.strip()}» không hợp lệ nên bị bỏ qua.")
            return
        moc.append(Moc(dt.isoformat(), dt.isoformat(), "ngay", f"{dt.day:02d}/{dt.month:02d}/{dt.year}"))

    for rx, ky in ((_ISO, "ymd"), (_CHU_DMY, "dmy"), (_DMY, "dmy")):
        for mm in rx.finditer(f):
            a, b, c = (int(x) for x in mm.groups())
            them_ngay(a, b, c, mm.group(0)) if ky == "ymd" else them_ngay(c, b, a, mm.group(0))
        f = rx.sub(" ", f)

    def them_thang(y: int, mo: int, goc: str) -> None:
        if not 1 <= mo <= 12:
            luu_y.append(f"Tháng «{goc.strip()}» không hợp lệ nên bị bỏ qua.")
            return
        moc.append(Moc(date(y, mo, calendar.monthrange(y, mo)[1]).isoformat(), date(y, mo, 1).isoformat(), "thang", f"tháng {mo}/{y}"))

    for rx, ky in ((_THANG_NAM, "my"), (_M_Y, "my")):
        for mm in rx.finditer(f):
            them_thang(int(mm.group(2)), int(mm.group(1)), mm.group(0))
        f = rx.sub(" ", f)

    nam_tran: list[tuple[int, str]] = []
    for rx in (_NAM, _NAM_TRAN):
        for mm in rx.finditer(f):
            nam_tran.append((int(mm.group(1)), mm.group(0)))
        f = rx.sub(" ", f)
    if co_dieu and nam_luat is None and len(nam_tran) == 1 and not moc and nam_tran[0][0] in nam_da_co:
        nam_luat = nam_tran[0][0]                                      # «Điều 173 năm 2015»: năm của văn bản, không phải ngày cần xem
        nam_tran = []
    for y, goc in nam_tran:
        moc.append(Moc(date(y, 12, 31).isoformat(), date(y, 1, 1).isoformat(), "nam", f"năm {y}"))

    if _GOC.search(f):
        moc.append(Moc(MOC_GOC, MOC_GOC, "goc", "bản gốc"))
        f = _GOC.sub(" ", f)
    if _HOM_NAY.search(f):
        moc.append(Moc(MOC_HOM_NAY, MOC_HOM_NAY, "hom_nay", "hiện nay"))
        f = _HOM_NAY.sub(" ", f)
    return moc, nam_luat, luu_y, re.sub(r"\s+", " ", f).strip()


# ---------------------------------------------------------------------------------------------------------------------

def _co(f: str, tu_khoa: tuple[str, ...]) -> bool:
    return any(k in f for k in tu_khoa)


def _ngoai_linh_vuc(f: str) -> str | None:
    for ten, khoa in _NGOAI_LINH_VUC:
        if _co(f, khoa):
            return ten
    return None


def phan_loai(cau: str, *, nam_van_ban: frozenset[int] | tuple[int, ...] = (2015,)) -> YDinh:
    """Câu người dùng → YDinh. `nam_van_ban`: năm của các văn bản có tên viết tắt trong kho (để nhận ra «Điều 173 năm 2015»)."""
    nam_da_co = frozenset(nam_van_ban)
    nfc = chuan_hoa(cau)
    f = bo_dau(nfc)
    y = YDinh(TRONG, (cau or "").strip())
    if not nfc:
        return y
    n_tu = len(nfc.split())
    refs: list[str] = []
    for mm in _DIEU.finditer(f):
        if mm.group(1) not in refs:
            refs.append(mm.group(1))
    mo_so = _CHI_SO.match(f) if not refs else None
    if mo_so:                                                           # gõ trơn «173» hay «d173»
        refs = [mo_so.group(1)]
    y.dieu = refs[:TOI_DA_DIEU]
    if len(refs) > TOI_DA_DIEU:
        y.luu_y.append(f"Chỉ xử lý {TOI_DA_DIEU} Điều đầu tiên trong câu.")
    y.xin_ket_luan = _co(f, _KET_LUAN)
    if _BLHS.search(f):
        y.viet_tat = "BLHS"
    khac = [ten for rx, ten in _LUAT_KHAC if rx.search(f)]
    if khac:
        y.van_ban_khac = khac[0]

    # 1. Hỏi luật khác: chặn nếu là kiểu tra cứu («Điều 5 BLDS») hoặc câu ngắn; câu kể chuyện dài chỉ nhắc
    if khac and (refs or n_tu <= 10):
        y.loai = NGOAI_PHAM_VI
        return y
    if khac:
        y.luu_y.append(f"Câu có nhắc {khac[0]}; kho này không có luật đó, kết quả chỉ gồm các Điều của Bộ luật Hình sự 2015.")

    # 2. Chào hỏi / trợ giúp
    if not refs and not y.dieu and ((_CHAO.match(f) and n_tu <= 4) or _TRO_GIUP.search(f)):
        y.loai = TRO_GIUP
        return y

    # 3. Có số Điều
    if refs:
        moc, nam_luat, luu_y, con_lai = tim_moc(f, nam_da_co, co_dieu=True)
        y.moc, y.nam_van_ban = moc, nam_luat
        y.luu_y += luu_y
        if len(refs) == 1:
            mk = _KHOAN.search(f)
            y.khoan = mk.group(1) if mk else None
            md = _DIEM_G.search(nfc) or _DIEM_F.search(f)
            y.diem = md.group(1) if md and y.khoan else None
        so_sanh = _co(f, _SO_SANH)
        if so_sanh or (_co(f, _LICH_SU) and n_tu <= TOI_DA_TU_THAM_CHIEU):
            y.loai = SO_SANH if so_sanh else LICH_SU
            return y
        if _co(f, _CHUYEN_TIEP) and n_tu <= TOI_DA_TU_THAM_CHIEU:
            y.loai = CHUYEN_TIEP
            return y
        if n_tu <= TOI_DA_TU_THAM_CHIEU:
            y.loai = TRA_DIEU
            return y
        y.loai = TINH_HUONG                                           # vừa có số Điều vừa kể chuyện dài: ưu tiên tình huống
        y.mo_ta = y.cau
        y.moc = []
        y.luu_y.append("Câu vừa có số Điều vừa kể tình huống, nên mình tìm theo tình huống. Muốn xem nguyên văn một Điều, "
                       "hãy gõ riêng, ví dụ «Điều 173».")
        y.dieu = []
        return y

    # 4. Không có số Điều (điều khoản chuyển tiếp xét trước quan hệ: «điều khoản chuyển tiếp của luật sửa đổi» chứa cả hai)
    if _co(f, _CHUYEN_TIEP):
        y.loai = CHUYEN_TIEP
        return y
    if any(r.search(f) for r in _QUAN_HE):
        y.loai = QUAN_HE
        return y
    lv = _ngoai_linh_vuc(f)
    if lv:
        y.luu_y.append(f"Câu hỏi có vẻ thuộc lĩnh vực {lv}, ngoài Bộ luật Hình sự (kho này chỉ có Bộ luật Hình sự 2015). "
                       "Kết quả dưới đây chỉ là các Điều hình sự có nghĩa gần nhất, có thể không liên quan.")
    y.mo_ta = y.cau
    if n_tu >= TU_TOI_THIEU_TINH_HUONG:
        y.loai = TINH_HUONG                                           # câu dài kể chuyện: không đọc ngày trong câu (ngày xảy ra việc ≠ ngày cần xem luật)
        return y
    moc, nam_luat, luu_y, _ = tim_moc(f, nam_da_co, co_dieu=False)
    y.loai, y.moc, y.nam_van_ban = TIM_MO_TA, moc, nam_luat
    y.luu_y += luu_y
    return y
