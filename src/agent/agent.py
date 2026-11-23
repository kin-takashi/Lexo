"""Agent của chức năng 1: nhận MỘT câu của người dùng, quyết định gọi công cụ nào, trả về TraLoi có cấu trúc (giao diện và CLI chỉ việc hiển thị).

  câu → phan_loai (luật, y_dinh.py) → công cụ (cong_cu.py) → TraLoi

Ràng buộc của chức năng 1 (kế hoạch v2 mục 1 và 14), giữ ở đây:
  * chỉ THAM KHẢO: không kết luận có tội hay không, không dự đoán mức án; câu hỏi dạng đó vẫn được trả điều luật liên quan, kèm lời nhắc;
  * nội dung Điều luôn là NGUYÊN VĂN từ kho, không do LLM viết lại hay diễn giải (bước 4b «LLM diễn giải» của kế hoạch cố ý KHÔNG làm:
    thêm một chỗ mô hình có thể bịa mà không thêm giá trị tra cứu);
  * mọi hạ cấp (thiếu Ollama, không tách được hành vi…) đều có thông báo trong TraLoi.thong_bao, không im lặng.
"""
from __future__ import annotations

import difflib
from dataclasses import asdict, dataclass, field
from datetime import date

from src.agent import y_dinh as yd
from src.agent.cong_cu import CongCu, DieuKetQua
from src.agent.trinh_bay import cua_so_hieu_luc, diff_html, loc_khoan, markdown_dieu
from src.query import lookup as lk
from src.query.lookup import fmt_date, render, tom_tat_nguon

MIEN_TRU = ("Thông tin chỉ để tham khảo, không phải tư vấn pháp lý và không phải kết luận về một vụ việc cụ thể. Điều luật hiển thị là bản "
            "dựng lại từ văn bản gốc và các luật sửa đổi đã nạp vào kho; khi cần dùng chính thức, hãy đối chiếu văn bản do cơ quan nhà nước "
            "công bố (Công báo) hoặc hỏi luật sư.")
LOI_NHAC_KET_LUAN = ("Mình chỉ tra cứu điều luật có liên quan, không đánh giá một vụ việc cụ thể, không kết luận có phạm tội hay không và không "
                     "dự đoán mức án. Khung hình phạt nằm ở các khoản của từng Điều bên dưới; vụ việc thực tế cần ý kiến của luật sư.")
LOI_NHAC_TINH_HUONG = ("Đây là các Điều có liên quan để bạn đọc tham khảo, không phải kết luận về tội danh. Mỗi hành vi chỉ hiển thị vài Điều gần "
                       "nghĩa nhất nên có thể chưa có Điều đúng: hãy đọc nguyên văn để đối chiếu.")
TOI_DA_HANH_VI = 8


@dataclass
class DieuDayDu:
    """Nguyên văn một Điều tại một ngày."""
    so: str
    tieu_de: str                       # 'Điều 173. Tội trộm cắp tài sản'
    van_ban: str                       # 'BLHS (100/2015/QH13)'
    ngay: str                          # ngày tra (ISO)
    hieu_luc_tu: str | None            # bản đang hiển thị có hiệu lực từ
    hieu_luc_den: str | None           # … đến (None = còn hiệu lực)
    markdown: str                      # phần được hỏi (cả Điều, hoặc một khoản/điểm)
    markdown_ca_dieu: str              # cả Điều nếu markdown chỉ là một khoản/điểm, ngược lại rỗng
    text: str                          # bản chữ thường (CLI), kèm nguồn sửa đổi sau từng chỗ bị sửa
    nguon: list[str] = field(default_factory=list)        # các lần sửa đổi đã tác động lên Điều này
    so_hieu_dinh: int = 0
    pham_vi: str = ""                  # 'khoản 2' nếu đã lọc
    ghi_chu: list[str] = field(default_factory=list)
    ban_goc: bool = False              # đây là bản gốc (như khi Quốc hội thông qua), không phải bản có hiệu lực tại một ngày


@dataclass
class MocLichSu:
    ngay: str
    noi_dung: str
    so_hieu: str = ""


@dataclass
class SoSanh:
    ngay_a: str
    ngay_b: str
    co_a: bool
    co_b: bool
    html: str
    unified: str
    so_dong_khac: int
    thay_doi: list[str] = field(default_factory=list)     # các lần sửa đổi có hiệu lực giữa hai ngày
    tieu_de: str = ""
    nhan_a: str = ""                   # nhãn hiển thị của hai bên: «bản gốc» hoặc ngày; rỗng thì dùng ngày
    nhan_b: str = ""


@dataclass
class Ben:
    """Một bên của phép so sánh: bộ luật đang áp dụng vào ngày đó (hoặc bản gốc của một bộ luật)."""
    iso: str
    goc: bool
    nhan: str
    vb: object | None = None
    ly_do: str = ""


@dataclass
class HanhVi:
    mo_ta: str
    dieu: list[DieuKetQua] = field(default_factory=list)


@dataclass
class TraLoi:
    loai: str
    cau: str
    y_dinh: yd.YDinh
    trang_thai: str = "ok"             # ok | khong_co | ngoai_pham_vi | tro_giup | trong
    tom_tat: str = ""                  # «Mình hiểu: tra nguyên văn Điều 173 tại ngày …»
    thong_bao: list[str] = field(default_factory=list)    # cho người dùng đọc (cảnh báo, hạ cấp)
    ky_thuat: list[str] = field(default_factory=list)     # chi tiết kỹ thuật (nằm trong phần mở rộng)
    ngay: str = ""
    dieu: list[DieuDayDu] = field(default_factory=list)
    ket_qua: list[DieuKetQua] = field(default_factory=list)
    hanh_vi: list[HanhVi] = field(default_factory=list)
    lich_su: list[MocLichSu] = field(default_factory=list)
    so_sanh: SoSanh | None = None
    quan_he: list[dict] = field(default_factory=list)
    chuyen_tiep: list[dict] = field(default_factory=list)
    goi_y: list[str] = field(default_factory=list)
    da_tach: bool = False
    mien_tru: str = MIEN_TRU
    nghiem_trong: bool = False         # thông báo cần hiện ở khung cảnh báo (kết quả rất có thể sai), không chỉ là ghi chú

    def to_dict(self) -> dict:
        return asdict(self)


def _them(ds: list[str], moi: list[str]) -> None:
    for x in moi:
        if x and x not in ds:
            ds.append(x)


class Agent:
    def __init__(self, cong_cu: CongCu):
        self.cc = cong_cu

    # ------------------------------------------------------------------ cửa vào

    def hoi(self, cau: str, *, ngay: str | None = None, tach: bool = True, xep_lai: bool | None = None, m: int | None = None, k: int = 5) -> TraLoi:
        """`ngay`: ngày xem mặc định (ISO) khi câu không nêu ngày; câu nêu ngày thì theo câu. `tach`: có tách tình huống thành hành vi không.
        `xep_lai`: None = theo cấu hình. `m`: số Điều mỗi hành vi; `k`: số Điều khi tìm một mô tả."""
        y = yd.phan_loai(cau, nam_van_ban=self.cc.nam_van_ban())
        tl = TraLoi(y.loai, (cau or "").strip(), y)
        _them(tl.thong_bao, y.luu_y)
        if y.xin_ket_luan:
            tl.thong_bao.append(LOI_NHAC_KET_LUAN)
        dich = {
            yd.TRA_DIEU: lambda: self._tra_dieu(tl, y, ngay),
            yd.LICH_SU: lambda: self._lich_su(tl, y),
            yd.SO_SANH: lambda: self._so_sanh(tl, y, ngay),
            yd.QUAN_HE: lambda: self._quan_he(tl, y),
            yd.CHUYEN_TIEP: lambda: self._chuyen_tiep(tl, y),
            yd.TIM_MO_TA: lambda: self._tim_mo_ta(tl, y, ngay, xep_lai, k),
            yd.TINH_HUONG: lambda: self._tinh_huong(tl, y, ngay, tach, xep_lai, m),
            yd.NGOAI_PHAM_VI: lambda: self._ngoai_pham_vi(tl, y),
            yd.TRO_GIUP: lambda: self._tro_giup(tl),
            yd.TRONG: lambda: self._trong(tl),
        }
        dich[y.loai]()
        return tl

    def lay_dieu(self, so: str, ngay: str | None = None) -> DieuDayDu | None:
        """Nguyên văn một Điều tại một ngày, của bộ luật đang áp dụng vào ngày đó (đường tắt cho giao diện: bấm «đọc nguyên văn» từ kết quả
        tìm kiếm). None nếu ngày đó không có bộ luật nào trong kho hoặc Điều không có hiệu lực."""
        ngay = ngay or self._hom_nay()
        vb = self.cc.van_ban_tai_ngay(ngay).vb
        if vb is None:
            return None
        u = self.cc.xem_dieu(vb["id"], so, ngay)
        if u is None:
            return None
        return self._dieu_day_du(TraLoi(yd.TRA_DIEU, "", yd.YDinh(yd.TRA_DIEU, "")), vb, u, so, ngay, None, None)

    # ------------------------------------------------------------------ tiện ích

    def _hom_nay(self) -> str:
        return date.today().isoformat()

    def _giai_moc(self, y: yd.YDinh, vb) -> list[tuple[str, yd.Moc]]:
        """Đổi mốc đặc biệt (bản gốc, hiện nay) ra ngày thật. «Bản gốc» = ngày bắt đầu hiệu lực của bộ luật `vb`; chỗ cần phân biệt bản gốc
        với bản có hiệu lực vào ngày đó thì nhìn `mc.iso == MOC_GOC`."""
        ra = []
        for mc in y.moc:
            iso = (self._ngay_goc(vb) if mc.iso == yd.MOC_GOC else self._hom_nay() if mc.iso == yd.MOC_HOM_NAY else mc.iso)
            if iso:
                ra.append((iso, mc))
        return ra

    @staticmethod
    def _ngay_goc(vb) -> str | None:
        return vb["ngay_hieu_luc"] or vb["ngay_ban_hanh"] if vb is not None else None

    def _van_ban(self, tl: TraLoi, y: yd.YDinh):
        """Bộ luật theo tên người dùng nêu; không nêu thì bộ luật đang áp dụng hôm nay (dùng cho câu không phụ thuộc ngày: lịch sử, quan hệ…)."""
        vb, loi = self.cc.van_ban(y.viet_tat, y.nam_van_ban)
        if vb is None:
            tl.trang_thai = "khong_co"
            tl.thong_bao.append(loi or "Không xác định được văn bản.")
        return vb

    def _ten_vb(self, vb) -> str:
        return f"{vb['ten_viet_tat'] or vb['ten_day_du']} ({vb['so_hieu']})"

    def _neu_luat(self, y: yd.YDinh) -> bool:
        """Người dùng chỉ đích danh MỘT bộ luật bằng năm («BLHS 2015», «BLHS 1999»). Chỉ nêu tên viết tắt («Điều 173 BLHS») thì bộ luật vẫn do NGÀY quyết định."""
        return y.nam_van_ban is not None

    def _ho_luat(self, tl: TraLoi, y: yd.YDinh):
        """(bộ luật nêu đích danh | None, tên viết tắt | None, có tiếp tục được không). Tên viết tắt không có trong kho → ghi lỗi vào `tl`."""
        if self._neu_luat(y):
            vb = self._van_ban(tl, y)
            return vb, y.viet_tat, vb is not None
        if y.viet_tat is not None:
            vb, loi = self.cc.van_ban(y.viet_tat, None)
            if vb is None:
                tl.trang_thai = "khong_co"
                tl.thong_bao.append(loi or "Không xác định được văn bản.")
                return None, None, False
        return None, y.viet_tat, True

    def _ly_khong_co(self, vb, so: str, iso: str, goc: bool = False) -> str:
        """Vì sao không có Điều `so` của bộ luật `vb` vào ngày `iso`: cả bộ luật chưa/không còn hiệu lực ngày đó, hay riêng Điều này."""
        ly = "" if goc else self.cc.mo_ta_ngoai_cua_so(vb, iso)
        return ly or self.cc.giai_thich_khong_co(vb["id"], so, iso, goc)

    def _luat_va_ngay(self, tl: TraLoi, y: yd.YDinh, ngay: str | None):
        """Chọn bộ luật và ngày cho câu tra Điều. Người dùng nêu bộ luật (BLHS 2015, BLHS 1999…) thì theo đó; không nêu thì lấy bộ luật đang áp dụng vào
        NGÀY CẦN XEM (mốc trong câu > ngày chọn ở thanh bên > hôm nay) theo thời gian hiệu lực của từng bộ luật. Trả (bộ luật, ngày, mốc đầu tiên,
        có phải bản gốc) hoặc None (đã ghi lý do vào `tl`)."""
        mc = y.moc[0] if y.moc else None
        goc = mc is not None and mc.iso == yd.MOC_GOC
        hom_nay = self._hom_nay()
        vb, vt, ok = self._ho_luat(tl, y)
        if not ok:
            return None
        if goc and vb is None:
            vb = self.cc.van_ban(vt, None)[0] if vt else self.cc.van_ban_hien_hanh()
            if vb is None:
                tl.trang_thai = "khong_co"
                tl.thong_bao.append("Kho chưa có bộ luật nào.")
                return None
        if goc:
            ngay_tra = self._ngay_goc(vb) or hom_nay
        elif mc is not None:
            ngay_tra = hom_nay if mc.iso == yd.MOC_HOM_NAY else mc.iso
        else:
            ngay_tra = ngay or hom_nay
            if vb is not None and ngay is None and vb["ngay_het_hieu_luc"] and hom_nay >= vb["ngay_het_hieu_luc"]:
                cuoi = lk.ngay_cuoi_hieu_luc(vb)                     # bộ luật đã hết hiệu lực mà không nêu ngày: bản cuối cùng của nó
                tl.thong_bao.append(f"{self.cc.ten_ngan(vb)} đã hết hiệu lực từ {fmt_date(vb['ngay_het_hieu_luc'])}; "
                                    f"mình hiển thị bản có hiệu lực vào ngày cuối cùng ({fmt_date(cuoi)}).")
                ngay_tra = cuoi
        if vb is None:
            r = self.cc.van_ban_tai_ngay(ngay_tra, vt)
            if r.vb is None:
                tl.ngay = ngay_tra
                tl.trang_thai = "khong_co"
                tl.thong_bao.append(r.ly_do)
                return None
            vb = r.vb
        return vb, ngay_tra, mc, goc

    def _luat_de_tim(self, tl: TraLoi, y: yd.YDinh, ngay_tra: str):
        """Bộ luật để TÌM THEO MÔ TẢ vào `ngay_tra`: phải có bộ luật áp dụng vào ngày đó và chỉ mục tìm kiếm phải có bộ luật đó. None thì đã ghi lý do."""
        vb, vt, ok = self._ho_luat(tl, y)
        if not ok:
            return None
        if vb is not None:
            ly = self.cc.mo_ta_ngoai_cua_so(vb, ngay_tra)
        else:
            r = self.cc.van_ban_tai_ngay(ngay_tra, vt)
            vb, ly = r.vb, r.ly_do
        if vb is None or ly:
            tl.trang_thai = "khong_co"
            tl.thong_bao.append(ly or "Không xác định được bộ luật.")
            return None
        if self.cc.chi_muc is not None and not self.cc.co_chi_muc_cho(vb["id"]):
            tl.trang_thai = "khong_co"
            tl.thong_bao.append(f"Chỉ mục tìm kiếm chưa có {self.cc.ten_ngan(vb)} (số {vb['so_hieu']}) nên chưa tìm theo mô tả vào ngày {fmt_date(ngay_tra)} được. "
                                "Bạn vẫn xem được nguyên văn nếu biết số Điều.")
            return None
        return vb

    def _pham_vi_kho(self) -> str:
        tt = self.cc.thong_tin_kho()
        cac = [f"{b['ten']} (từ {fmt_date(b['hieu_luc_tu'])}" + (f" đến hết {fmt_date(b['hieu_luc_den'])}" if b["hieu_luc_den"] else " đến nay") + ")" for b in tt["cac_bo_luat"]]
        return "; ".join(cac)

    def _su_kien_trong_ky(self, vb, so: str, mc: yd.Moc) -> list[str]:
        """Sửa đổi rơi vào giữa kỳ người dùng nêu (tháng/năm), để họ biết bản cuối kỳ khác bản đầu kỳ."""
        if mc.kieu not in ("thang", "nam"):
            return []
        return [f"{fmt_date(e.ngay)}: {e.mo_ta(4)}" for e in self.cc.lich_su(vb["id"], so) if mc.tu <= e.ngay <= mc.iso]

    # ------------------------------------------------------------------ tra Điều

    def _dieu_day_du(self, tl: TraLoi, vb, u, so: str, ngay: str, khoan: str | None, diem: str | None, goc: bool = False) -> DieuDayDu | None:
        tu, den = (None, None) if goc else cua_so_hieu_luc(u)
        loc, pham_vi, loi = loc_khoan(u, khoan, diem)
        if loi:
            tl.thong_bao.append(loi)
            loc, pham_vi = u, ""
        md = markdown_dieu(loc, tieu_de=False)                  # tiêu đề đã nằm ở đầu thẻ
        ghi_chu = []
        if goc:
            ghi_chu.append(f"Đây là bản gốc, đúng như khi Quốc hội thông qua"
                           + (f" ngày {fmt_date(vb['ngay_ban_hanh'])}" if vb["ngay_ban_hanh"] else "") + f"; {self.cc.ten_ngan(vb)} có hiệu lực từ {fmt_date(vb['ngay_hieu_luc'])}.")
            cung_ngay = [e for e in self.cc.lich_su(vb["id"], so) if e.ngay == vb["ngay_hieu_luc"]]
            if cung_ngay:
                ghi_chu.append("Điều này đã được sửa đổi ngay từ ngày bộ luật có hiệu lực (" + "; ".join(e.ten_ngan for e in cung_ngay)
                               + f"), nên bản gốc chưa từng được áp dụng riêng. Muốn xem bản đang áp dụng, hỏi «Điều {so} tại ngày …».")
        else:
            sap = [e for e in self.cc.lich_su(vb["id"], so) if e.ngay > ngay]
            for e in sap:
                ghi_chu.append(f"Sẽ có sửa đổi hiệu lực từ {fmt_date(e.ngay)} (chưa áp dụng tại ngày {fmt_date(ngay)}): {e.mo_ta(4)}")
        cho = self.cc.hieu_dinh_cho_duyet(vb["id"], so)
        if cho:
            ghi_chu.append(f"Có {len(cho)} đề xuất hiệu đính kỹ thuật CHƯA được duyệt cho Điều này (chưa áp vào chữ ở trên): " + "; ".join(
                f"{r['khoa']}: “{r['tu_cu']}” → “{r['thanh_moi']}”" for r in cho))
        n_hd = sum(len(x.hieu_dinh) for x in u.walk())
        if n_hd:
            ghi_chu.append(f"Điều này có {n_hd} chỗ đã hiệu đính kỹ thuật theo văn bản hợp nhất chính thức (đã được người duyệt xác nhận).")
        return DieuDayDu(
            so=so, tieu_de=f"Điều {u.ky_hieu}. {u.tieu_de or ''}".rstrip(), van_ban=self._ten_vb(vb), ngay=ngay, hieu_luc_tu=tu, hieu_luc_den=den,
            markdown=md, markdown_ca_dieu=markdown_dieu(u, tieu_de=False) if pham_vi else "", text=render(loc, ghi_chu=True),
            nguon=[f"{n.ten_ngan}" + (f" ({n.vi_tri_nguon})" if n.vi_tri_nguon else "") + f", hiệu lực từ {fmt_date(n.hieu_luc_tu)}" for n in tom_tat_nguon(u)],
            so_hieu_dinh=n_hd, pham_vi=pham_vi, ghi_chu=ghi_chu, ban_goc=goc)

    def _tra_dieu(self, tl: TraLoi, y: yd.YDinh, ngay: str | None) -> None:
        sel = self._luat_va_ngay(tl, y, ngay)
        if sel is None:
            return
        vb, ngay_tra, mc, goc = sel
        tl.ngay = ngay_tra
        ten = self.cc.ten_ngan(vb)
        if len(y.moc) > 1:
            tl.thong_bao.append(f"Câu có nhiều mốc thời gian; mình xem theo mốc đầu tiên ({fmt_date(ngay_tra)}). Muốn đối chiếu hai thời điểm, hãy hỏi «so sánh».")
        if mc is not None and mc.kieu in ("thang", "nam"):
            tl.thong_bao.append(f"Bạn nêu «{mc.goc}», mình lấy bản có hiệu lực vào cuối kỳ ({fmt_date(ngay_tra)}).")
        if ngay_tra > self._hom_nay():
            tl.thong_bao.append("Ngày này ở tương lai: kết quả chỉ gồm các sửa đổi đã được nạp vào kho, có thể chưa đầy đủ.")
        ds = ", ".join(f"Điều {s}" for s in y.dieu)
        tl.tom_tat = (f"Mình hiểu: xem nguyên văn {ds} {ten} bản gốc (như khi Quốc hội thông qua)." if goc
                      else f"Mình hiểu: xem nguyên văn {ds} {ten} tại ngày {fmt_date(ngay_tra)}.").replace("  ", " ")
        ly = "" if goc else self.cc.mo_ta_ngoai_cua_so(vb, ngay_tra)        # người dùng nêu một bộ luật mà ngày đó nằm ngoài thời gian hiệu lực của nó
        if ly:
            tl.trang_thai = "khong_co"
            tl.thong_bao.append(ly)
            return
        one = len(y.dieu) == 1
        for so in y.dieu:
            u = self.cc.xem_dieu(vb["id"], so, ngay_tra, goc=goc)
            if u is None:
                tl.thong_bao.append(self._ly_khong_co(vb, so, ngay_tra, goc))
                continue
            dd = self._dieu_day_du(tl, vb, u, so, ngay_tra, y.khoan if one else None, y.diem if one else None, goc=goc)
            if mc is not None and not goc:
                dd.ghi_chu += [f"Trong {mc.goc} có sửa đổi hiệu lực từ {x}" for x in self._su_kien_trong_ky(vb, so, mc)]
            tl.dieu.append(dd)
        if not tl.dieu:
            tl.trang_thai = "khong_co"
        else:
            tl.tom_tat = tl.tom_tat.replace(ds, ", ".join(f"Điều {d.so}" for d in tl.dieu), 1)
        _them(tl.thong_bao, self.cc.canh_bao_kho(vb["id"], co_ngay=mc is not None or ngay is not None))
        if tl.dieu:
            so = tl.dieu[0].so
            tl.goi_y = [f"Lịch sử sửa đổi Điều {so}", f"So sánh Điều {so} bản gốc và hiện hành"]

    # ------------------------------------------------------------------ lịch sử

    def _lich_su(self, tl: TraLoi, y: yd.YDinh) -> None:
        vb = self._van_ban(tl, y)
        if vb is None:
            return
        so = y.dieu[0]
        if len(y.dieu) > 1:
            tl.thong_bao.append(f"Chỉ xem lịch sử một Điều mỗi lần; mình xem Điều {so}.")
        hom_nay = self._hom_nay()
        ngay_xem = hom_nay if not vb["ngay_het_hieu_luc"] or hom_nay < vb["ngay_het_hieu_luc"] else lk.ngay_cuoi_hieu_luc(vb)   # bộ luật đã hết hiệu lực: bản cuối của nó
        ev = self.cc.lich_su(vb["id"], so)
        co_goc = self.cc.xem_dieu(vb["id"], so, vb["ngay_hieu_luc"], goc=True) is not None if vb["ngay_hieu_luc"] else False
        if not ev and self.cc.xem_dieu(vb["id"], so, ngay_xem) is None and not co_goc:
            tl.trang_thai = "khong_co"
            tl.thong_bao.append(self.cc.giai_thich_khong_co(vb["id"], so, ngay_xem))
            return
        ten = self.cc.ten_ngan(vb)
        if co_goc:
            if vb["ngay_hieu_luc"] == vb["ngay_hieu_luc_theo_van_ban"]:
                nd = f"Ban hành trong {vb['ten_day_du']} (hiệu lực theo văn bản)"
            else:
                theo = ", ".join(x["so_hieu"] for x in self.cc.nguon_doi_hieu_luc(vb["id"]))
                nd = (f"Bắt đầu hiệu lực (ngày ghi trong văn bản là {fmt_date(vb['ngay_hieu_luc_theo_van_ban'])}, "
                      f"thực tế đã được dời sang {fmt_date(vb['ngay_hieu_luc'])}" + (f" theo {theo}" if theo else "") + ")")
            tl.lich_su.append(MocLichSu(vb["ngay_hieu_luc"], nd, vb["so_hieu"]))
        tl.lich_su += [MocLichSu(e.ngay, e.mo_ta(10), e.so_hieu) for e in ev]
        tl.ngay = ngay_xem
        tl.tom_tat = f"Mình hiểu: xem các lần Điều {so} {ten} được sửa đổi, bổ sung, bãi bỏ.".replace("  ", " ")
        if len(tl.lich_su) <= (1 if co_goc else 0):
            tl.thong_bao.append(f"Điều {so} chưa từng bị sửa đổi trong các luật đã nạp vào kho.")
        if vb["ngay_het_hieu_luc"] and hom_nay >= vb["ngay_het_hieu_luc"]:
            tl.thong_bao.append(f"{ten} đã hết hiệu lực từ {fmt_date(vb['ngay_het_hieu_luc'])}; đây là lịch sử của bộ luật đó.")
        _them(tl.thong_bao, self.cc.canh_bao_kho(vb["id"], co_ngay=True))
        tl.goi_y = [f"So sánh Điều {so} bản gốc và hiện hành", f"Điều {so}"]

    # ------------------------------------------------------------------ so sánh

    def _doi_ben(self, mc: yd.Moc | None, iso: str | None, vb0, hien, vt: str | None = None) -> Ben:
        """Một mốc (hoặc một ngày) → bên so sánh: bộ luật nêu rõ trong câu, hoặc bộ luật đang áp dụng vào ngày đó. «Bản gốc» là bản gốc của
        bộ luật nêu rõ / đang áp dụng hôm nay."""
        if mc is not None and mc.iso == yd.MOC_GOC:
            vb = vb0 or hien
            return Ben(self._ngay_goc(vb) or self._hom_nay(), True, "bản gốc", vb)
        if mc is not None:
            iso = self._hom_nay() if mc.iso == yd.MOC_HOM_NAY else mc.iso
        nhan = fmt_date(iso)
        if vb0 is not None:
            return Ben(iso, False, nhan, vb0)
        r = self.cc.van_ban_tai_ngay(iso, vt)
        return Ben(iso, False, nhan, r.vb, r.ly_do)

    def _so_sanh(self, tl: TraLoi, y: yd.YDinh, ngay: str | None) -> None:
        vb0, vt, ok = self._ho_luat(tl, y)
        if not ok:
            return
        hien = vb0 or (self.cc.van_ban(vt, None)[0] if vt else self.cc.van_ban_hien_hanh())
        so = y.dieu[0]
        if len(y.dieu) > 1:
            tl.thong_bao.append(f"Chỉ so sánh một Điều mỗi lần; mình so sánh Điều {so}.")
        hom_nay = self._hom_nay()
        cuoi = f"{'ngày bạn chọn' if ngay else 'hiện nay'} ({fmt_date(ngay or hom_nay)})"
        if len(y.moc) >= 2:
            ben = [self._doi_ben(mc, None, vb0, hien, vt) for mc in y.moc[:2]]
        elif len(y.moc) == 1:
            ben = [self._doi_ben(y.moc[0], None, vb0, hien, vt), self._doi_ben(None, ngay or hom_nay, vb0, hien, vt)]
            tl.thong_bao.append(f"Câu chỉ nêu một mốc; mình so với {cuoi}.")
        else:
            ben = [self._doi_ben(yd.Moc(yd.MOC_GOC, yd.MOC_GOC, "goc", "bản gốc"), None, vb0, hien, vt), self._doi_ben(None, ngay or hom_nay, vb0, hien, vt)]
            tl.thong_bao.append(f"Câu không nêu mốc nào; mình so bản gốc (như khi Quốc hội thông qua) với {cuoi}.")
        a, b = sorted(ben, key=lambda x: (x.iso, 0 if x.goc else 1))
        tl.ngay = b.iso
        if a.vb is None and b.vb is None:
            tl.trang_thai = "khong_co"
            for x in (a, b):
                _them(tl.thong_bao, [x.ly_do])
            return
        if a.vb is None or b.vb is None or a.vb["id"] != b.vb["id"]:
            self._so_sanh_khac_luat(tl, so, a, b)
            return
        vb = a.vb
        ua, ub = self.cc.so_sanh(vb["id"], so, a.iso, b.iso, goc_a=a.goc)
        if ua is None and ub is None:
            tl.trang_thai = "khong_co"
            tl.thong_bao += [self._ly_khong_co(vb, so, a.iso, a.goc), self._ly_khong_co(vb, so, b.iso)]
            return
        for u, x in ((ua, a), (ub, b)):
            if u is None:
                tl.thong_bao.append(self._ly_khong_co(vb, so, x.iso, x.goc))
        ta = render(ua) if ua else ""
        tb = render(ub) if ub else ""
        html, so_khac = diff_html(ta, tb)
        unified = "\n".join(difflib.unified_diff(ta.splitlines(), tb.splitlines(), fromfile=f"Điều {so} @ {a.nhan}", tofile=f"Điều {so} @ {b.nhan}", lineterm=""))
        thay_doi = [f"{fmt_date(e.ngay)}: {e.mo_ta(6)}" for e in self.cc.lich_su(vb["id"], so) if (a.iso < e.ngay <= b.iso) or (a.goc and e.ngay == a.iso and e.ngay <= b.iso)]
        tl.so_sanh = SoSanh(a.iso, b.iso, ua is not None, ub is not None, html, unified, so_khac, thay_doi, f"Điều {so}", a.nhan, b.nhan)
        if ua is not None and ub is not None and not so_khac:
            tl.thong_bao.append(f"Điều {so} giống nhau ở hai thời điểm {a.nhan} và {b.nhan}.")
        tl.tom_tat = f"Mình hiểu: so sánh Điều {so} {self.cc.ten_ngan(vb)} giữa {a.nhan} và {b.nhan}.".replace("  ", " ")
        _them(tl.thong_bao, self.cc.canh_bao_kho(vb["id"], co_ngay=True))
        tl.goi_y = [f"Lịch sử sửa đổi Điều {so}", f"Điều {so}"]

    def _so_sanh_khac_luat(self, tl: TraLoi, so: str, a: Ben, b: Ben) -> None:
        """Hai thời điểm thuộc hai bộ luật khác nhau (hoặc một bên không có bộ luật trong kho): không so từng chữ vì bộ luật mới viết lại và đánh số lại
        toàn bộ; hiển thị riêng nguyên văn Điều ở mỗi bên có bộ luật."""
        if a.vb is not None and b.vb is not None:
            tl.thong_bao.append(f"Hai thời điểm thuộc hai bộ luật khác nhau ({self.cc.ten_ngan(a.vb)} và {self.cc.ten_ngan(b.vb)}). Bộ luật mới được viết lại và đánh số lại, "
                                f"số Điều giữa hai bộ luật không tương ứng nhau, nên mình không so từng chữ mà hiển thị riêng nguyên văn Điều {so} ở mỗi thời điểm.")
        for x in (a, b):
            if x.vb is None:
                _them(tl.thong_bao, [f"Bên {x.nhan}: {x.ly_do}"])
                continue
            u = self.cc.xem_dieu(x.vb["id"], so, x.iso, goc=x.goc)
            if u is None:
                tl.thong_bao.append(f"Bên {x.nhan}: " + self._ly_khong_co(x.vb, so, x.iso, x.goc))
                continue
            tl.dieu.append(self._dieu_day_du(tl, x.vb, u, so, x.iso, None, None, goc=x.goc))
        if not tl.dieu:
            tl.trang_thai = "khong_co"
        tl.tom_tat = f"Mình hiểu: so sánh Điều {so} giữa {a.nhan} và {b.nhan}."
        tl.goi_y = [f"Lịch sử sửa đổi Điều {so}", f"Điều {so}"]

    # ------------------------------------------------------------------ quan hệ, chuyển tiếp

    def _quan_he(self, tl: TraLoi, y: yd.YDinh) -> None:
        vb = self._van_ban(tl, y)
        if vb is None:
            return
        tl.quan_he = self.cc.quan_he(vb["id"])
        tl.tom_tat = f"Mình hiểu: xem các văn bản có quan hệ với {self._ten_vb(vb)} (sửa đổi, bổ sung, hoãn hiệu lực…)."
        if not tl.quan_he:
            tl.trang_thai = "khong_co"
            tl.thong_bao.append("Kho chưa ghi nhận văn bản nào có quan hệ với văn bản này.")
        tl.goi_y = ["Điều khoản chuyển tiếp của các luật sửa đổi"]

    def _chuyen_tiep(self, tl: TraLoi, y: yd.YDinh) -> None:
        vb = self._van_ban(tl, y)
        if vb is None:
            return
        tl.chuyen_tiep = self.cc.chuyen_tiep(vb["id"])
        tl.tom_tat = f"Mình hiểu: xem nguyên văn điều khoản hiệu lực và chuyển tiếp của các luật đã sửa đổi {vb['ten_viet_tat'] or vb['so_hieu']}."
        tl.thong_bao.append("Đây là nguyên văn các điều khoản. Hệ thống KHÔNG tự suy ra việc áp dụng hồi tố cho một vụ việc cụ thể; hãy đọc kỹ hoặc hỏi luật sư.")
        if not tl.chuyen_tiep:
            tl.trang_thai = "khong_co"
            tl.thong_bao.append("Kho chưa có điều khoản hiệu lực / chuyển tiếp nào.")

    # ------------------------------------------------------------------ tìm theo mô tả

    def _tim_mo_ta(self, tl: TraLoi, y: yd.YDinh, ngay: str | None, xep_lai: bool | None, k: int) -> None:
        moc = self._giai_moc(y, self.cc.van_ban_hien_hanh())
        ngay_tra = moc[0][0] if moc else (ngay or self._hom_nay())
        tl.ngay = ngay_tra
        tl.tom_tat = f"Mình hiểu: tìm các Điều có nội dung gần với «{y.mo_ta or y.cau}» (bản có hiệu lực ngày {fmt_date(ngay_tra)})."
        vb = self._luat_de_tim(tl, y, ngay_tra)
        if vb is None:
            return
        kq, tb, kt = self.cc.tim_dieu(y.mo_ta or y.cau, ngay_tra, k=k, xep_lai=xep_lai)
        tl.ket_qua = kq
        _them(tl.thong_bao, tb)
        _them(tl.ky_thuat, kt)
        if not kq:
            tl.trang_thai = "khong_co"
            tl.thong_bao.append("Không tìm thấy Điều nào phù hợp. Thử mô tả bằng từ khác, hoặc nêu số Điều nếu bạn biết.")
        else:
            tl.goi_y = [f"Điều {kq[0].so}", f"Lịch sử sửa đổi Điều {kq[0].so}"]

    # ------------------------------------------------------------------ tình huống nhiều hành vi

    def _tinh_huong(self, tl: TraLoi, y: yd.YDinh, ngay: str | None, tach: bool, xep_lai: bool | None, m: int | None) -> None:
        ngay_tra = ngay or self._hom_nay()
        tl.ngay = ngay_tra
        if self._luat_de_tim(tl, y, ngay_tra) is None:               # ngày chọn không có bộ luật trong kho (hoặc chỉ mục thiếu): nói rõ, không tìm bậy
            tl.tom_tat = f"Mình hiểu: tìm các Điều gần với tình huống (bản có hiệu lực ngày {fmt_date(ngay_tra)})."
            return
        m = m or int(self.cc.ch["so_dieu_moi_hanh_vi"])
        khong_ollama = not self.cc.co_tach and not self.cc.co_vector
        if khong_ollama:
            tl.nghiem_trong = True
            tl.thong_bao.append("Chưa có Ollama nên cả việc tách hành vi lẫn tìm theo nghĩa đều tắt: với tình huống kể nhiều việc, kết quả sẽ rất kém "
                                "(thường chỉ ra một phần số Điều cần tìm). Hãy bật Ollama rồi bấm «Kiểm tra lại kết nối» ở thanh bên.")
        if tach:
            hanh_vi, tb, kt = self.cc.tach(y.mo_ta)
            _them(tl.thong_bao, tb)
            _them(tl.ky_thuat, kt)
            tl.da_tach = self.cc.co_tach and not tb
        else:
            hanh_vi = [y.mo_ta]
            if self.cc.co_tach:
                tl.thong_bao.append("Bạn đã tắt tách hành vi nên mình tìm theo cả tình huống như một câu hỏi.")
            elif not khong_ollama:
                tl.thong_bao.append("Chưa có mô hình tách hành vi nên mình tìm theo cả tình huống như một câu hỏi; tình huống kể nhiều việc có thể chỉ ra một phần số Điều cần tìm.")
        hanh_vi = hanh_vi[:TOI_DA_HANH_VI]
        so_dieu = m if tl.da_tach else int(self.cc.ch["so_dieu_khi_khong_tach"])
        for mo_ta in hanh_vi:
            kq, tb, kt = self.cc.tim_dieu(mo_ta, ngay_tra, k=so_dieu, xep_lai=xep_lai)
            _them(tl.thong_bao, tb)
            _them(tl.ky_thuat, kt)
            tl.hanh_vi.append(HanhVi(mo_ta, kq))
        if khong_ollama:                                        # cảnh báo mạnh đã nói rõ; bỏ dòng «đang tìm theo từ khoá» lặp ý
            tl.thong_bao = [x for x in tl.thong_bao if not x.startswith("Đang tìm theo từ khoá")]
        if not any(h.dieu for h in tl.hanh_vi):
            tl.trang_thai = "khong_co"
            tl.thong_bao.append("Không tìm thấy Điều nào phù hợp.")
        tl.thong_bao.append(LOI_NHAC_TINH_HUONG)
        n = len(tl.hanh_vi)
        tl.tom_tat = (f"Mình hiểu: tình huống có {n} hành vi; mỗi hành vi được tìm Điều riêng (bản có hiệu lực ngày {fmt_date(ngay_tra)})."
                      if tl.da_tach else f"Mình hiểu: tìm các Điều gần với cả tình huống (bản có hiệu lực ngày {fmt_date(ngay_tra)}).")

    # ------------------------------------------------------------------ còn lại

    def _ngoai_pham_vi(self, tl: TraLoi, y: yd.YDinh) -> None:
        tl.trang_thai = "ngoai_pham_vi"
        co = ", ".join(f"{r['ten_day_du']} ({r['ten_viet_tat']})" for r in self.cc.danh_sach_van_ban()) or "chưa có văn bản nào"
        tl.thong_bao.append(f"Mình chưa có {y.van_ban_khac or 'văn bản đó'}. Hiện kho chỉ có: {co}.")
        tl.tom_tat = "Câu hỏi nằm ngoài phạm vi của kho."
        tl.goi_y = list(yd.VI_DU[:3])

    def _tro_giup(self, tl: TraLoi) -> None:
        tl.trang_thai = "tro_giup"
        tt = self.cc.thong_tin_kho()
        pham_vi = self._pham_vi_kho()
        chua = "; ".join(f"{c['ten']} (từ {fmt_date(c['tu'])} đến hết {fmt_date(c['den'])})" for c in tt["chua_nap"])
        tl.tom_tat = (f"Mình tra cứu {tt['ten']} (hiện có {tt['so_dieu']} Điều)" + (f"; kho có: {pham_vi}" if len(tt["cac_bo_luat"]) > 1 or tt["chua_nap"] else "")
                      + (f"; chưa nạp: {chua}" if chua else "") + ". Bạn có thể: gõ số Điều để xem nguyên văn; hỏi lịch sử sửa đổi hoặc "
                      "so sánh hai thời điểm; mô tả một hành vi bằng lời thường để tìm Điều liên quan; hoặc kể cả một tình huống nhiều việc để mình "
                      "tách từng hành vi. Mình chỉ tra cứu, không đưa ra kết luận pháp lý.")
        tl.goi_y = list(yd.VI_DU)

    def _trong(self, tl: TraLoi) -> None:
        tl.trang_thai = "trong"
        tl.tom_tat = "Bạn hãy gõ câu hỏi, ví dụ số Điều hoặc mô tả một hành vi."
        tl.goi_y = list(yd.VI_DU[:4])


def thanh_van_ban(tl: TraLoi, *, day_du: bool = True) -> str:
    """TraLoi → chữ thường để in ra terminal."""
    ra: list[str] = []
    if tl.tom_tat:
        ra.append(tl.tom_tat)
    for x in tl.thong_bao:
        ra.append(f"Lưu ý: {x}")
    for d in tl.dieu:
        ra.append(f"\n[{d.van_ban}] " + ("bản gốc (như khi Quốc hội thông qua)" if d.ban_goc else
                  f"bản có hiệu lực từ {fmt_date(d.hieu_luc_tu)}" + (f" đến trước {fmt_date(d.hieu_luc_den)}" if d.hieu_luc_den else ""))
                  + (f" — chỉ {d.pham_vi}" if d.pham_vi else ""))
        ra.append(d.text if day_du else d.tieu_de)
        ra += [f"Lưu ý: {x}" for x in d.ghi_chu]
        if d.nguon:
            ra.append("Điều này đã được sửa đổi, bổ sung bởi: " + "; ".join(d.nguon))
    for e in tl.lich_su:
        ra.append(f"  {fmt_date(e.ngay)}  {e.noi_dung}")
    if tl.so_sanh:
        ra.append(tl.so_sanh.unified or "(giống nhau)")
        ra += [f"  thay đổi giữa hai ngày: {x}" for x in tl.so_sanh.thay_doi]
    for h in tl.hanh_vi:
        ra.append(f"\nHành vi: {h.mo_ta}")
        ra += [f"  {k.hang}. {k.tieu_de}" + (f"  [{k.vi_tri}]" if k.vi_tri else "") for k in h.dieu]
    for k in tl.ket_qua:
        ra.append(f"{k.hang}. {k.tieu_de}" + (f"  [{k.vi_tri}]" if k.vi_tri else "") + (f"\n     {k.trich}" if k.trich else ""))
    for r in tl.quan_he:
        ra.append(f"  {fmt_date(r['ngay_hieu_luc'])}  {r['loai_quan_he']}  {r['so_hieu']} — {r['ten_day_du']}")
    for r in tl.chuyen_tiep:
        ra.append(f"\n— {r['so_hieu']} {r['vi_tri']} ({'hiệu lực' if r['loai'] == 'hieu_luc' else 'chuyển tiếp'}):\n{r['noi_dung']}")
    if tl.goi_y:
        ra.append("\nCó thể hỏi tiếp: " + " | ".join(tl.goi_y))
    ra.append("\n" + tl.mien_tru)
    return "\n".join(ra)
