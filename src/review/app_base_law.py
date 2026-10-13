"""Giao diện duyệt văn bản gốc (hai cột): trái = văn bản nguồn, phải = kết quả parse.

Chạy:  streamlit run src/review/app_base_law.py
Người duyệt: (1) xử lý cờ validator, (2) đối chiếu 30 Điều mẫu với bản chính thức, (3) bấm Duyệt -> raw/<số hiệu>/review.json.
Giao diện chỉ ghi review.json; nạp vào CSDL là scripts/ingest_base_law.py.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from src.config import raw_dir  # noqa: E402
from src.review.base_law_review import (  # noqa: E402
    approve, blocking_problems, file_sha256, flag_key, load_parsed, load_review, new_review, save_review,
)
from src.review.base_law_view import (  # noqa: E402
    dieu_at_line, dieu_matches_source, dieu_spans, node_to_text, path_to, sample_dieu,
)
from src.validate.base_law import CANH_BAO, LOI, THONG_TIN, summarize, validate_base_law  # noqa: E402

WINDOW_BEFORE, WINDOW_AFTER = 12, 48
ICON = {LOI: "🔴", CANH_BAO: "🟠", THONG_TIN: "🔵"}

st.set_page_config(page_title="Lexo — duyệt văn bản gốc", layout="wide")


@st.cache_resource(show_spinner="Đang đọc parsed.json ...")
def load_doc(path: str, sha: str):
    law = load_parsed(Path(path))
    return law, validate_base_law(law), dieu_spans(law), sample_dieu(law)


def line_of(message: str) -> int | None:
    m = re.search(r"dòng (\d+)", message)
    return int(m.group(1)) if m else None


def jump_to(line: int) -> None:
    st.session_state["jump_line"] = line


def on_pick_dieu(spans_by_key: dict) -> None:
    key = st.session_state.get("dieu_pick")
    if key in spans_by_key:
        st.session_state["jump_line"] = spans_by_key[key][1]


# ---------- chọn văn bản ----------
slugs = sorted(p.parent.name for p in raw_dir().glob("*/parsed.json"))
st.title("Duyệt văn bản gốc")
if not slugs:
    st.info(f"Chưa có văn bản nào trong {raw_dir()}. Chạy trước: python scripts/parse_base_law.py <file.docx> --ten-viet-tat <VIẾT TẮT>")
    st.stop()
slug = st.sidebar.selectbox("Văn bản", slugs)
directory = raw_dir() / slug
parsed_path = directory / "parsed.json"
sha = file_sha256(parsed_path)
law, flags, spans, sample = load_doc(str(parsed_path), sha)
spans_by_key = {d.ky_hieu: (d, a, b) for d, a, b in spans}

saved = load_review(directory / "review.json")
if saved is not None and saved.get("parsed_sha256") != sha:
    st.sidebar.warning("review.json cũ thuộc bản parse khác — bỏ qua, duyệt lại từ đầu.")
    saved = None
review = saved or new_review(sha)

state_key = f"{slug}:{sha}"
if st.session_state.get("_doc") != state_key:            # đổi văn bản hoặc parse lại: nạp lại trạng thái từ review.json
    st.session_state["_doc"] = state_key
    st.session_state["jump_line"] = len(law.preamble)
    st.session_state["nguoi_duyet"] = review.get("nguoi_duyet", "")
    st.session_state["ghi_chu"] = review.get("ghi_chu", "")
    for f in flags:
        fk = flag_key(f)
        if f.level == LOI:
            st.session_state[f"mien::{fk}"] = review.get("mien_loi", {}).get(fk, "")
        elif f.level == CANH_BAO:
            st.session_state[f"xem::{fk}"] = fk in review.get("da_xem_canh_bao", [])
    for k in sample:
        st.session_state[f"mau::{k}"] = k in review.get("mau_doi_chieu", [])

# ---------- tổng quan ----------
m = law.meta
st.caption(f"{m.so_hieu} — {m.ten_day_du} ({m.ten_viet_tat}) · ban hành {m.ngay_ban_hanh} · hiệu lực theo văn bản {m.ngay_hieu_luc} · nguồn {law.source.get('name')}")
counts = summarize(law)
cols = st.columns(len(counts))
for c, (k, v) in zip(cols, counts.items()):
    c.metric(k, v)
if review.get("da_duyet"):
    st.success(f"Đã duyệt bởi {review.get('nguoi_duyet')} ngày {review.get('ngay_duyet')} (có thể sửa và duyệt lại).")

# ---------- cờ validator ----------
st.subheader("1. Cờ của validator")
n_err = sum(f.level == LOI for f in flags)
n_warn = sum(f.level == CANH_BAO for f in flags)
st.write(f"{n_err} lỗi (mỗi lỗi phải được miễn kèm ghi chú), {n_warn} cảnh báo (mỗi cảnh báo phải được xem).")
for i, f in enumerate(flags):
    fk = flag_key(f)
    line = f.line if f.line is not None else line_of(f.message)
    c1, c2, c3 = st.columns([6, 1, 4])
    c1.markdown(f"{ICON[f.level]} **{f.level}** — {f.message}")
    if line is not None:
        c2.button("Xem dòng", key=f"go{i}", on_click=jump_to, args=(line,))
    if f.level == LOI:
        c3.text_input("Ghi chú miễn lỗi (bắt buộc)", key=f"mien::{fk}", placeholder="vd: lỗi do văn bản nguồn, đã đối chiếu bản chính thức")
    elif f.level == CANH_BAO:
        c3.checkbox("Đã xem", key=f"xem::{fk}")

# ---------- hai cột ----------
st.subheader("2. Đối chiếu nguồn ↔ kết quả parse")
st.selectbox("Nhảy tới Điều", list(spans_by_key), key="dieu_pick", index=None, placeholder="chọn số Điều",
             on_change=on_pick_dieu, args=(spans_by_key,))
jump = min(max(int(st.session_state["jump_line"]), 0), max(len(law.lines) - 1, 0))
left, right = st.columns(2)
with left:
    st.markdown(f"**Văn bản nguồn** (dòng {jump}, đã chuẩn hoá Ð→Đ và khoảng trắng)")
    lo, hi = max(0, jump - WINDOW_BEFORE), min(len(law.lines), jump + WINDOW_AFTER)
    st.code("\n".join(f"{'>>' if i == jump else '  '} {i:5d} | {law.lines[i]}" for i in range(lo, hi)), language=None, wrap_lines=True)
with right:
    hit = dieu_at_line(law, jump)
    if hit is None:
        st.markdown("**Kết quả parse** — dòng này không thuộc Điều nào (tiêu đề Phần/Chương/Mục hoặc phần mở đầu).")
    else:
        dieu, a, b = hit
        trail = " › ".join(f"{n.loai} {n.ky_hieu}" for n in path_to(law, dieu))
        ok = dieu_matches_source(law, dieu, a, b)
        st.markdown(f"**Kết quả parse** — Điều {dieu.ky_hieu} (dòng {a}–{b - 1}) · {trail or 'gốc'} · "
                    + ("✅ khớp nguồn" if ok else "❌ KHÔNG khớp nguồn"))
        st.code(node_to_text(dieu), language=None, wrap_lines=True)

# ---------- mẫu đối chiếu ----------
st.subheader("3. Đối chiếu tay 30 Điều mẫu với bản chính thức (vbpl.vn / văn bản hợp nhất)")
st.caption("Danh sách cố định (seed) nên lần duyệt nào cũng như nhau. Mở từng Điều ở mục 2, so với bản chính thức, tick khi khớp 100%.")
per_row = 6
for start in range(0, len(sample), per_row):
    row = st.columns(per_row)
    for col, k in zip(row, sample[start:start + per_row]):
        col.checkbox(f"Điều {k}", key=f"mau::{k}")

# ---------- duyệt ----------
st.subheader("4. Duyệt")
nguoi = st.text_input("Người duyệt", key="nguoi_duyet")
ghi_chu = st.text_area("Ghi chú chung (tuỳ chọn)", key="ghi_chu")


def collect() -> dict:
    r = new_review(sha)
    r["mien_loi"] = {flag_key(f): st.session_state.get(f"mien::{flag_key(f)}", "").strip()
                     for f in flags if f.level == LOI and st.session_state.get(f"mien::{flag_key(f)}", "").strip()}
    r["da_xem_canh_bao"] = [flag_key(f) for f in flags if f.level == CANH_BAO and st.session_state.get(f"xem::{flag_key(f)}")]
    r["mau_doi_chieu"] = [k for k in sample if st.session_state.get(f"mau::{k}")]
    r["ghi_chu"] = ghi_chu
    r["nguoi_duyet"] = nguoi.strip()
    return r


draft = collect()
missing = []
if not nguoi.strip():
    missing.append("chưa ghi tên người duyệt")
missing += [p for p in blocking_problems(law, {**draft, "da_duyet": True}, sha) if not p.startswith("Thiếu tên")]
todo_sample = [k for k in sample if k not in draft["mau_doi_chieu"]]
if todo_sample:
    missing.append(f"còn {len(todo_sample)}/{len(sample)} Điều mẫu chưa đối chiếu")

b1, b2 = st.columns(2)
if b1.button("Lưu nháp (chưa duyệt)", key="luu_nhap"):
    save_review(draft, directory / "review.json")
    st.success("Đã lưu nháp.")
if b2.button("Duyệt và lưu", type="primary", disabled=bool(missing), key="duyet"):
    save_review(approve(draft, nguoi), directory / "review.json")
    st.success(f"Đã duyệt. Nạp vào CSDL bằng: python scripts/ingest_base_law.py {slug}")
if missing:
    st.warning("Chưa thể bấm Duyệt:\n\n" + "\n".join(f"- {x}" for x in missing))
