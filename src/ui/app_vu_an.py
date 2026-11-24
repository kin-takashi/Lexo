"""Giao diện Chức năng 2 (Streamlit, chạy trên máy): nhập nội dung vụ án → bản tóm tắt kiểu cáo trạng: người nào, làm gì, có dấu hiệu phạm tội gì
(Điều/khoản), vì sao, kèm đoạn trích nguyên văn từ sự việc và nguyên văn Điều luật trong kho để đối chiếu.

Chạy:  streamlit run src/ui/app_vu_an.py        (Windows: bấm đúp chay_phan_tich_vu_an.bat)

Giao diện chỉ hiển thị KetQuaVuAn; logic ở src/agent/vu_an.py. Thiếu Ollama thì chỉ gợi ý Điều (có thông báo). Chỉ để THAM KHẢO.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from src.agent.agent import Agent  # noqa: E402
from src.agent.cong_cu import CongCu, KhoLoi  # noqa: E402
from src.agent.trinh_bay import md_thoat  # noqa: E402
from src.agent.vu_an import MIEN_TRU_VU_AN, KetQuaVuAn, PhanTichVuAn, Toi, Trich, thanh_cao_trang  # noqa: E402
from src.query.lookup import fmt_date  # noqa: E402

st.set_page_config(page_title="Lexo — Phân tích vụ án", page_icon="⚖️", layout="wide")

VI_DU = {
    "Trộm xe máy rồi bán": ("Khoảng 22 giờ ngày 12/3/2024, Nguyễn Văn A rủ Trần Văn B đến nhà anh Hoàng Văn H ở phường X. A và B phá khoá cổng, dắt trộm một chiếc "
                            "xe máy Honda Wave trị giá 15 triệu đồng. Sáng hôm sau, A đem xe bán cho Lê Văn C với giá 4 triệu đồng; C biết rõ chiếc xe do trộm "
                            "cắp mà có nhưng vẫn mua để bán lại kiếm lời. Số tiền bán xe, A và B chia nhau tiêu xài cá nhân."),
    "Đánh nhau gây thương tích": ("Khoảng 20 giờ ngày 5/6/2023, tại quán nhậu trên đường Y, Phạm Văn D và Hoàng Văn E xảy ra cãi vã với anh Nguyễn Văn K vì va chạm "
                                  "chỗ ngồi. D dùng tay đấm nhiều cái vào mặt anh K; E cầm chai bia đập vào đầu anh K khiến anh K ngã xuống đất. Anh K phải nhập "
                                  "viện, bị gãy xương hàm, kết luận giám định tỷ lệ tổn thương cơ thể là 28%."),
}


@st.cache_resource(show_spinner="Đang mở kho luật ...")
def lay_phan_tich(db: str, index: str, gia: str) -> PhanTichVuAn:
    """Tham số chỉ để khoá bộ nhớ đệm khi đổi đường dẫn (kiểm thử); CongCu.mo đọc lại cùng các biến môi trường."""
    ag = Agent(CongCu.mo(db=db or None, index=index or None, gia=bool(gia) or None))
    return PhanTichVuAn.mo(ag, gia=bool(gia))


def yeu_cau_chay() -> None:
    st.session_state["chay"] = True


def dat_vi_du(chu: str) -> None:
    st.session_state["su_viec"] = chu
    st.session_state["chay"] = True


def xoa() -> None:
    st.session_state["su_viec"] = ""
    st.session_state["kq_vu_an"] = None


# ---------------------------------------------------------------------------------------------------------------------

def thanh_ben(pv: PhanTichVuAn) -> dict:
    cc = pv.cc
    with st.sidebar:
        st.header("Tuỳ chọn")
        khac = st.checkbox("Áp dụng luật theo ngày xảy ra hành vi", key="dung_ngay",
                           help="Luật hình sự áp dụng theo thời điểm phạm tội. Không bật thì dùng bản luật có hiệu lực hôm nay.")
        ngay = None
        if khac:
            ngay = st.date_input("Ngày xảy ra hành vi", value=date.today(), min_value=date(1986, 1, 1), max_value=date(2035, 12, 31),
                                 format="DD/MM/YYYY", key="ngay_xem").isoformat()
            r = cc.van_ban_tai_ngay(ngay)
            if r.vb is not None:
                st.caption(f"Vào ngày này áp dụng: **{cc.ten_ngan(r.vb)}** (số {r.vb['so_hieu']}).")
            else:
                st.warning(r.ly_do)
        so_dieu = st.slider("Số Điều tối đa đưa vào bản soạn", 1, 6, int(pv.ch["so_dieu_soan"]), key="so_dieu",
                            help="Càng nhiều Điều thì càng ít sót tội, nhưng bản soạn chậm hơn và dễ nhiễu hơn.")
        st.caption("Tuỳ chọn áp dụng cho lần phân tích tiếp theo.")
        st.divider()
        st.subheader("Trạng thái")
        for t in pv.trang_thai():
            st.markdown(f"{'🟢' if t['ok'] else '🟠'} **{t['ten']}** — {t['mo_ta']}")
        if st.button("Kiểm tra lại kết nối", key="kt_lai", help="Bấm sau khi bật Ollama."):
            cc.lam_moi()
            pv.lam_moi()
            st.rerun()
        tt = cc.thong_tin_kho()
        st.divider()
        st.caption(f"Kho luật: {tt['ten']}" + (f", nạp ngày {fmt_date(tt['ngay_nap'])}" if tt["ngay_nap"] else ""))
    return {"ngay": ngay, "so_dieu": so_dieu}


# ---------------------------------------------------------------------------------------------------------------------

def ve_trich(t: Trich) -> None:
    st.markdown(f"> {'✅' if t.khop else '⚠️'} “{md_thoat(t.chu)}”" + ("" if t.khop else "  \n> *không tìm thấy nguyên văn trong sự việc, cần kiểm tra*"))


def vi_tri(o: Toi, kq: KetQuaVuAn) -> str:
    vb = next((d.van_ban.split(" (")[0] for d in kq.dieu if d.so == o.dieu), "Bộ luật Hình sự")
    return (f"khoản {o.khoan} " if o.khoan else "") + f"Điều {o.dieu} {vb}"


def tab_ban_cao_buoc(kq: KetQuaVuAn) -> None:
    if not kq.nguoi:
        st.info("Chưa soạn được nội dung theo từng người. Xem thông báo phía trên và tab «Điều luật liên quan» để biết các Điều đã tìm được.")
        return
    st.markdown(thanh_cao_trang(kq, md=True))
    c1, c2, _ = st.columns([1, 1, 3])
    c1.download_button("Tải bản văn (.txt)", thanh_cao_trang(kq), file_name="ban_cao_buoc_tham_khao.txt", mime="text/plain", key="tai_txt")
    c2.download_button("Tải dữ liệu (.json)", json.dumps(kq.to_dict(), ensure_ascii=False, indent=2), file_name="ket_qua_vu_an.json",
                       mime="application/json", key="tai_json")
    with st.expander("Sao chép dạng văn bản thuần"):
        st.code(thanh_cao_trang(kq), language=None)


def tab_tung_nguoi(kq: KetQuaVuAn) -> None:
    if not kq.nguoi:
        st.info("Chưa có nội dung theo từng người.")
        return
    st.caption("✅ đoạn trích có nguyên văn trong sự việc · ⚠️ không tìm thấy nguyên văn, hoặc tên không có trong sự việc: cần kiểm tra.")
    dieu = {d.so: d for d in kq.dieu}
    for i, n in enumerate(kq.nguoi, 1):
        with st.container(border=True):
            st.subheader(f"{i}. {md_thoat(n.ten)}" + ("" if n.ten_khop else " ⚠️"))
            if n.vai_tro:
                st.caption(f"Vai trò: {n.vai_tro}")
            if n.hanh_vi:
                st.markdown("**Hành vi**")
                for h in n.hanh_vi:
                    st.markdown(f"- {md_thoat(h.mo_ta)}")
                    if h.trich:
                        ve_trich(h.trich)
            for j, o in enumerate(n.toi):
                with st.container(border=True):
                    st.markdown(f":red-badge[{md_thoat(o.ten_toi)}] {md_thoat(vi_tri(o, kq))}")
                    if o.ly_do:
                        st.markdown(f"**Vì sao:** {md_thoat(o.ly_do)}")
                    for t in o.can_cu:
                        ve_trich(t)
                    with st.expander(f"Đọc nguyên văn Điều {o.dieu}"):
                        st.markdown(dieu[o.dieu].markdown)


def tab_dieu(kq: KetQuaVuAn, pv: PhanTichVuAn) -> None:
    dung = {d.so: d for d in kq.dieu}
    st.caption("Các Điều về tội phạm tìm được theo nội dung vụ án, xếp theo mức khớp. Chữ luật lấy nguyên văn từ kho, không do mô hình viết.")
    for d in kq.ung_vien:
        with st.container(border=True):
            nhan = ":green-badge[đã đưa vào bản soạn]" if d.so in dung else ":gray-badge[chỉ gợi ý]"
            st.markdown(f"**{d.hang}. {md_thoat(d.tieu_de)}**  {nhan}")
            if d.trich:
                st.caption((f"Khớp nhất ở {d.vi_tri}: " if d.vi_tri else "") + md_thoat(d.trich))
            with st.expander("Đọc nguyên văn Điều này"):
                dd = dung.get(d.so) or pv.ag.lay_dieu(d.so, kq.ngay)
                if dd is None:
                    st.write("Điều này không có hiệu lực tại ngày đã chọn.")
                else:
                    st.markdown(dd.markdown)
                    for g in dd.ghi_chu:
                        st.caption(g)


def tab_ky_thuat(kq: KetQuaVuAn, pv: PhanTichVuAn) -> None:
    st.write(f"Chế độ: `{kq.che_do}` · thời gian: {kq.giay:.1f} giây · Điều ứng viên: {[d.so for d in kq.ung_vien]} · Điều sau bước chọn: {kq.da_chon}")
    for t in pv.trang_thai():
        st.write(f"{'🟢' if t['ok'] else '🟠'} {t['ten']}: {t['mo_ta']}")
    for x in kq.ky_thuat:
        st.code(x, language=None)


def hien_thi(kq: KetQuaVuAn, pv: PhanTichVuAn) -> None:
    if kq.thong_bao:
        hop = st.warning if kq.nghiem_trong else st.info
        hop("\n".join(f"- {x}" for x in kq.thong_bao))
    if not kq.ung_vien:
        return
    soan = kq.che_do == "day_du"
    c = st.columns(4)
    c[0].metric("Người có dấu hiệu phạm tội", len(kq.nguoi) if soan else "—")
    c[1].metric("Số tội", kq.so_toi if soan else "—")
    c[2].metric("Số Điều đã xét", len(kq.dieu))
    c[3].metric("Thời gian", f"{kq.giay:.0f} giây")
    t1, t2, t3, t4 = st.tabs(["Bản cáo buộc tham khảo", "Theo từng người", "Điều luật liên quan", "Chi tiết kỹ thuật"])
    with t1:
        tab_ban_cao_buoc(kq)
    with t2:
        tab_tung_nguoi(kq)
    with t3:
        tab_dieu(kq, pv)
    with t4:
        tab_ky_thuat(kq, pv)


# ---------------------------------------------------------------------------------------------------------------------

def main() -> None:
    try:
        pv = lay_phan_tich(os.environ.get("LEXO_DB", ""), os.environ.get("LEXO_INDEX", ""), os.environ.get("LEXO_GIA", ""))
    except KhoLoi as e:
        st.error(str(e))
        st.stop()
    for w in pv.cc.canh_bao_khoi_dong:
        st.warning(w)
    tuy_chon = thanh_ben(pv)

    st.title("Lexo · Phân tích vụ án")
    st.caption("Nhập diễn biến vụ án, Lexo gợi ý ai có dấu hiệu phạm tội gì, theo Điều nào, vì sao · chỉ để tham khảo, không phải kết luận pháp lý")
    chu = st.text_area("Nội dung vụ án", key="su_viec", height=240,
                       placeholder="Dán hoặc gõ diễn biến vụ án: ai làm gì, khi nào, ở đâu, thiệt hại ra sao. Có thể dán phần «Nội dung vụ án» của bản án hoặc cáo trạng.",
                       help="Càng đủ chi tiết về từng người thì kết quả theo từng người càng đúng. Sự việc dài hơn khoảng 2.500 từ sẽ bị lược phần giữa khi soạn.")
    c1, c2, c3 = st.columns([1, 1, 5])
    c1.button("Phân tích vụ án", type="primary", key="phan_tich", on_click=yeu_cau_chay)
    c2.button("Xoá", key="xoa", on_click=xoa)
    c3.caption(f"{len(chu.split())} từ")

    if st.session_state.pop("chay", False):
        with st.status("Đang phân tích vụ án…", expanded=True) as tt:
            try:
                kq = pv.phan_tich(chu, ngay=tuy_chon["ngay"], so_dieu=tuy_chon["so_dieu"], bao=tt.write)
                tt.update(label="Đã xong" if kq.ung_vien else "Chưa phân tích được", state="complete" if kq.ung_vien else "error", expanded=False)
            except Exception as e:                                  # ranh giới giao diện: lỗi bất ngờ không được làm trang trắng
                kq = None
                tt.update(label="Có lỗi khi phân tích", state="error")
                st.error("Có lỗi khi xử lý vụ án này. Bạn thử lại, hoặc gửi nội dung bên dưới cho người phát triển.")
                st.exception(e)
        st.session_state["kq_vu_an"] = kq
    kq = st.session_state.get("kq_vu_an")
    if kq is None:
        st.caption("Thử nhanh")
        cot = st.columns(len(VI_DU))
        for i, (ten, noi_dung) in enumerate(VI_DU.items()):
            cot[i].button(ten, key=f"vd{i}", on_click=dat_vi_du, args=(noi_dung,), use_container_width=True)
    else:
        st.divider()
        hien_thi(kq, pv)

    st.divider()
    st.caption(MIEN_TRU_VU_AN)


main()
