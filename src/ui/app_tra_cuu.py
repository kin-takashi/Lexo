"""Giao diện tra cứu cho người dùng thường (Streamlit, chạy trên máy, không cần mạng).

Chạy:  streamlit run src/ui/app_tra_cuu.py        (Windows: bấm đúp chay_tra_cuu.bat)

Người dùng gõ MỘT ô duy nhất (số Điều, câu hỏi lịch sử/so sánh, mô tả hành vi bằng lời thường, hoặc kể cả tình huống); agent
(src/agent/agent.py) tự chọn cách xử lý. Giao diện chỉ hiển thị TraLoi, không có logic nghiệp vụ.
Chỉ để THAM KHẢO: không kết luận pháp lý (kế hoạch v2 mục 1 và 14).
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from src.agent import y_dinh as yd  # noqa: E402
from src.agent.agent import MIEN_TRU, Agent, DieuDayDu, TraLoi  # noqa: E402
from src.agent.cong_cu import CongCu, DieuKetQua, KhoLoi  # noqa: E402
from src.agent.trinh_bay import md_thoat  # noqa: E402
from src.query.lookup import fmt_date, ngay_cuoi_hieu_luc  # noqa: E402

st.set_page_config(page_title="Lexo — Tra cứu Bộ luật Hình sự", page_icon="⚖️", layout="centered")

VI_DU_TINH_HUONG = ("Chủ quán karaoke biết nhiều nhóm khách thuê phòng để hút ma túy đá nhưng vẫn cho thuê, còn tính thêm tiền dọn dẹp. "
                    "Ngoài ra anh còn bán từng gói ma túy tổng hợp cho khách ngay tại quán để kiếm thêm.")
QUAN_HE = {"sua_doi": "sửa đổi", "bo_sung": "bổ sung", "thay_the": "thay thế", "bai_bo": "bãi bỏ", "hoan_hieu_luc": "hoãn hiệu lực",
           "huong_dan": "hướng dẫn", "dinh_chi": "đình chỉ"}


@st.cache_resource(show_spinner="Đang mở kho luật ...")
def lay_agent(db: str, index: str, gia: str) -> Agent:
    """Tham số chỉ để khoá bộ nhớ đệm khi đổi đường dẫn (kiểm thử); CongCu.mo đọc lại cùng các biến môi trường."""
    return Agent(CongCu.mo(db=db or None, index=index or None, gia=bool(gia) or None))


def het_ngay(den_iso: str) -> str:
    """hieu_luc_den là ngày bản MỚI bắt đầu; bản cũ còn hiệu lực đến hết ngày liền trước."""
    return fmt_date((date.fromisoformat(den_iso) - timedelta(days=1)).isoformat())


def yeu_cau_chay() -> None:
    st.session_state["chay"] = True


def dat_cau(cau: str) -> None:
    st.session_state["cau_nhap"] = cau
    st.session_state["chay"] = True


# ---------------------------------------------------------------------------------------------------------------------

def thanh_ben(ag: Agent) -> dict:
    cc = ag.cc
    with st.sidebar:
        st.header("Tuỳ chọn")
        khac = st.checkbox("Xem luật theo một ngày khác hôm nay", key="dung_ngay",
                           help="Dùng khi cần biết điều luật có hiệu lực vào một thời điểm trong quá khứ. Câu hỏi nêu ngày cụ thể thì theo câu hỏi.")
        ngay = None
        if khac:
            ngay = st.date_input("Ngày", value=date.today(), min_value=date(1986, 1, 1), max_value=date(2035, 12, 31),
                                 format="DD/MM/YYYY", key="ngay_xem").isoformat()
            r = cc.van_ban_tai_ngay(ngay)                           # bộ luật áp dụng theo thời gian hiệu lực của từng bộ luật, hiện ngay để người dùng biết
            if r.vb is not None:
                st.caption(f"Vào ngày này áp dụng: **{cc.ten_ngan(r.vb)}** (số {r.vb['so_hieu']}), hiệu lực từ {fmt_date(r.vb['ngay_hieu_luc'])}"
                           + (f" đến hết {fmt_date(ngay_cuoi_hieu_luc(r.vb))}" if r.vb["ngay_het_hieu_luc"] else " đến nay") + ".")
            else:
                st.warning(r.ly_do)
        tach = st.toggle("Tách tình huống dài thành từng hành vi", value=cc.co_tach, disabled=not cc.co_tach, key="tach",
                         help="Tình huống kể nhiều việc sẽ được tách ra, mỗi việc tìm Điều riêng.")
        m = st.slider("Số Điều gợi ý cho mỗi hành vi", 1, 5, int(cc.ch["so_dieu_moi_hanh_vi"]), key="m_dieu")
        xep_lai = st.toggle("Xếp lại kết quả (chậm hơn, hơi chính xác hơn)", value=False, disabled=not cc.co_the_xep_lai, key="xep_lai")
        if khac or not cc.co_tach or not cc.co_the_xep_lai:
            st.caption("Tuỳ chọn áp dụng cho lần tra cứu tiếp theo.")
        st.divider()
        st.subheader("Trạng thái")
        for t in cc.trang_thai():
            st.markdown(f"{'🟢' if t['ok'] else '🟠'} **{t['ten']}** — {t['mo_ta']}")
        if st.button("Kiểm tra lại kết nối", key="kt_lai", help="Bấm sau khi bật Ollama."):
            cc.lam_moi()
            st.rerun()
        tt = cc.thong_tin_kho()
        st.divider()
        st.caption(f"Kho luật: {tt['ten']}" + (f", nạp ngày {fmt_date(tt['ngay_nap'])}" if tt["ngay_nap"] else ""))
        if tt["cac_bo_luat"]:
            st.caption("Bộ luật đã nạp: " + "; ".join(
                f"{b['ten']} (từ {fmt_date(b['hieu_luc_tu'])}" + (f" đến hết {fmt_date(b['hieu_luc_den'])}" if b["hieu_luc_den"] else " đến nay") + ")" for b in tt["cac_bo_luat"]))
        if tt["chua_nap"]:
            st.caption("Chưa nạp (ngày thuộc các thời kỳ này chưa tra được): " + "; ".join(
                f"{c['ten']} ({fmt_date(c['tu'])} – {fmt_date(c['den'])})" for c in tt["chua_nap"]))
        for x in tt["hieu_luc_theo"]:
            st.caption(f"Ngày bắt đầu hiệu lực theo {x['so_hieu']}" + (f" ({x['vi_tri_nguon']})" if x["vi_tri_nguon"] else "") + f": {fmt_date(x['ngay_hieu_luc_moi'])}.")
        def ds_sua_doi(ds: list[dict]) -> str:
            return ", ".join(f"{s['so_hieu']} (hiệu lực {fmt_date(s['ngay_hieu_luc'])})" for s in ds)
        if len(tt["cac_bo_luat"]) > 1:                       # nhiều bộ luật nối tiếp: nói rõ luật sửa đổi nào thuộc bộ luật nào
            theo_bo = [f"{b['ten']}: {ds_sua_doi(b['sua_doi'])}" for b in tt["cac_bo_luat"] if b["sua_doi"]]
            if theo_bo:
                st.caption("Luật sửa đổi đã nạp — " + "; ".join(theo_bo))
        elif tt["sua_doi"]:
            st.caption("Luật sửa đổi đã nạp: " + "; ".join(f"{s['so_hieu']} (hiệu lực {fmt_date(s['ngay_hieu_luc'])})" for s in tt["sua_doi"]))
        if tt["lenh_cho_duyet"] or tt["hieu_dinh_cho_duyet"]:
            st.caption(f"Đang chờ duyệt: {tt['lenh_cho_duyet']} lệnh sửa đổi, {tt['hieu_dinh_cho_duyet']} đề xuất hiệu đính kỹ thuật (chưa ảnh hưởng nội dung hiển thị).")
    return {"ngay": ngay, "tach": tach, "m": m, "xep_lai": xep_lai or None}


# ---------------------------------------------------------------------------------------------------------------------

def ve_dieu(d: DieuDayDu) -> None:
    with st.container(border=True):
        st.subheader(md_thoat(d.tieu_de))
        den = f"đến hết {het_ngay(d.hieu_luc_den)}" if d.hieu_luc_den else "đến nay"
        khoang = "bản gốc (như khi Quốc hội thông qua)" if d.ban_goc else f"bản có hiệu lực từ {fmt_date(d.hieu_luc_tu)} {den}"
        st.caption(f"{d.van_ban} · {khoang}" + (f" · chỉ hiển thị {d.pham_vi}" if d.pham_vi else ""))
        st.markdown(d.markdown)
        for g in d.ghi_chu:
            st.caption(g)
        if d.markdown_ca_dieu:
            with st.expander("Xem cả Điều"):
                st.markdown(d.markdown_ca_dieu)
        if d.nguon:
            with st.expander(f"Nguồn sửa đổi ({len(d.nguon)})"):
                for n in d.nguon:
                    st.markdown(f"- {n}")


def ve_ket_qua(k: DieuKetQua, ag: Agent, ngay: str, khoa: str) -> None:
    with st.container(border=True):
        st.markdown(f"**{k.hang}. {md_thoat(k.tieu_de)}**")
        if k.trich:
            st.caption((f"Khớp nhất ở {k.vi_tri}: " if k.vi_tri else "") + md_thoat(k.trich))
        with st.expander("Đọc nguyên văn Điều này"):
            d = ag.lay_dieu(k.so, ngay)
            if d is None:
                st.write("Điều này không có hiệu lực tại ngày đã chọn.")
            else:
                st.markdown(d.markdown)
                for g in d.ghi_chu:
                    st.caption(g)
        st.button(f"Lịch sử sửa đổi Điều {k.so}", key=f"{khoa}_ls", on_click=dat_cau, args=(f"Lịch sử sửa đổi Điều {k.so}",))


def ve_goi_y(goi_y: list[str], khoa: str, tieu_de: str = "Có thể hỏi tiếp") -> None:
    if not goi_y:
        return
    st.caption(tieu_de)
    for i, g in enumerate(goi_y):
        st.button(g, key=f"{khoa}_gy{i}", on_click=dat_cau, args=(g,))


def hien_thi(tl: TraLoi, ag: Agent) -> None:
    if tl.tom_tat:
        st.markdown(f"*{tl.tom_tat}*")
    if tl.thong_bao:
        hop = st.warning if (tl.nghiem_trong or tl.trang_thai in ("khong_co", "ngoai_pham_vi")) else st.info
        hop("\n".join(f"- {x}" for x in tl.thong_bao))
    ngay = tl.ngay or date.today().isoformat()

    for d in tl.dieu:
        ve_dieu(d)

    if tl.lich_su:
        for e in tl.lich_su:
            st.markdown(f"**{fmt_date(e.ngay)}** — {md_thoat(e.noi_dung)}")

    if tl.so_sanh:
        s = tl.so_sanh
        st.subheader(f"{s.tieu_de}: {s.nhan_a or fmt_date(s.ngay_a)} → {s.nhan_b or fmt_date(s.ngay_b)}")
        st.caption("Nền đỏ gạch ngang: phần của bản cũ bị bỏ hoặc đổi. Nền xanh: phần mới thêm hoặc đổi. Không tô màu: giữ nguyên.")
        if s.co_a or s.co_b:
            st.markdown(s.html, unsafe_allow_html=True)
        if s.thay_doi:
            st.markdown("**Các lần sửa đổi có hiệu lực giữa hai ngày**")
            for x in s.thay_doi:
                st.markdown(f"- {md_thoat(x)}")

    for i, h in enumerate(tl.hanh_vi, 1):
        st.markdown(f"#### Hành vi {i}" if tl.da_tach else "#### Cả tình huống")
        st.write(h.mo_ta)
        if not h.dieu:
            st.caption("Không tìm thấy Điều phù hợp.")
        for k in h.dieu:
            ve_ket_qua(k, ag, ngay, f"hv{i}_{k.so}")

    for k in tl.ket_qua:
        ve_ket_qua(k, ag, ngay, f"kq_{k.so}")

    for r in tl.quan_he:
        vai = "tác động lên văn bản đang xét" if r["huong"] == "tac_dong_len_vb" else "văn bản đang xét tác động lên"
        st.markdown(f"**{md_thoat(r['so_hieu'])}** — {md_thoat(r['ten_day_du'])}  \n"
                    f"{QUAN_HE.get(r['loai_quan_he'], r['loai_quan_he'])} · {vai} · ban hành {fmt_date(r['ngay_ban_hanh'])} · hiệu lực {fmt_date(r['ngay_hieu_luc'])}")

    for r in tl.chuyen_tiep:
        loai = "hiệu lực" if r["loai"] == "hieu_luc" else "chuyển tiếp"
        with st.expander(f"{r['so_hieu']} — {r['vi_tri']} ({loai})"):
            st.markdown(md_thoat(r["noi_dung"]).replace("\n", "\n\n"))

    if tl.trang_thai in ("tro_giup", "trong", "ngoai_pham_vi"):
        ve_goi_y(tl.goi_y, "tl", "Thử một trong các câu sau")
    else:
        ve_goi_y(tl.goi_y, "tl")

    with st.expander("Chi tiết kỹ thuật"):
        y = tl.y_dinh
        st.write(f"Loại câu hỏi mình nhận ra: `{y.loai}`")
        thamso = {k: v for k, v in {"dieu": y.dieu, "khoan": y.khoan, "diem": y.diem, "mốc": [(m.iso, m.goc) for m in y.moc], "văn bản": y.viet_tat,
                                    "năm văn bản": y.nam_van_ban}.items() if v}
        if thamso:
            st.json(thamso)
        for x in tl.ky_thuat:
            st.code(x, language=None)


# ---------------------------------------------------------------------------------------------------------------------

def main() -> None:
    try:
        ag = lay_agent(os.environ.get("LEXO_DB", ""), os.environ.get("LEXO_INDEX", ""), os.environ.get("LEXO_GIA", ""))
    except KhoLoi as e:
        st.error(str(e))
        st.stop()
    for w in ag.cc.canh_bao_khoi_dong:
        st.warning(w)
    tuy_chon = thanh_ben(ag)

    st.title("Lexo")
    st.caption("Tra cứu Bộ luật Hình sự và các luật sửa đổi theo từng thời kỳ · chỉ để tham khảo, không phải tư vấn pháp lý")
    cau = st.text_area("Bạn muốn tra gì?", key="cau_nhap", height=110, on_change=yeu_cau_chay,
                       placeholder="Gõ số Điều (vd: Điều 173), hỏi lịch sử sửa đổi, mô tả một hành vi bằng lời thường, hoặc kể cả một tình huống…",
                       help="Nhấn Ctrl+Enter hoặc bấm «Tra cứu».")
    st.button("Tra cứu", type="primary", key="tra_cuu", on_click=yeu_cau_chay)

    if st.session_state.pop("chay", False):
        with st.spinner("Đang tra cứu… (tình huống dài có thể mất vài giây)"):
            try:
                st.session_state["tl"] = ag.hoi(cau, ngay=tuy_chon["ngay"], tach=tuy_chon["tach"], xep_lai=tuy_chon["xep_lai"], m=tuy_chon["m"])
            except Exception as e:                                  # ranh giới giao diện: lỗi bất ngờ không được làm trang trắng
                st.session_state["tl"] = None
                st.error("Có lỗi khi xử lý câu hỏi này. Bạn thử diễn đạt lại, hoặc gửi nội dung bên dưới cho người phát triển.")
                st.exception(e)
    tl = st.session_state.get("tl")
    if tl is None:
        st.caption("Thử nhanh")
        for i, v in enumerate((*yd.VI_DU, VI_DU_TINH_HUONG)):
            st.button(v if len(v) < 70 else v[:67] + "…", key=f"vd{i}", on_click=dat_cau, args=(v,))
    else:
        st.divider()
        hien_thi(tl, ag)

    st.divider()
    st.caption(MIEN_TRU)


main()
