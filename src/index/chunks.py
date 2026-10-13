"""Chia CSDL luật thành các ĐOẠN (chunk) để tìm kiếm.

Quy tắc (Bước 4 của kế hoạch):
  * Mỗi PHIÊN BẢN có chữ của một nút Điều/Khoản/Điểm là một đoạn, kể cả bản đã hết hiệu lực (để tra theo ngày).
    Chương/Mục/Phần chỉ là khung nên không thành đoạn. Phiên bản có khoảng hiệu lực rỗng (chưa từng có hiệu lực) bị bỏ.
  * Điều chỉ có tiêu đề (không có chữ riêng) vẫn thành một đoạn gồm đúng tiêu đề, để câu hỏi theo tên tội tìm ra Điều.
  * Mỗi đoạn mang NGỮ CẢNH: tên Điều, và với Điểm thì thêm câu dẫn của Khoản. Một Điểm đứng riêng như "có tổ chức;"
    không đủ nghĩa để tìm kiếm. Ngữ cảnh lấy theo phiên bản của nút cha có hiệu lực vào ngày phiên bản con bắt đầu.
  * `hash` = SHA-256 của chữ đưa vào mô hình. Cùng chữ thì dùng lại vector đã tính; đổi chữ (vd sau hiệu đính) thì chỉ
    đoạn đổi phải tính lại.
"""
from __future__ import annotations

import hashlib
import sqlite3
from dataclasses import dataclass

from src.validate.vbhn import key_of

KHUNG = {"phan", "chuong", "muc", "tieu_muc"}
VO_CUC = "9999-12-31"
LEAD_TOI_DA = 300


@dataclass(frozen=True)
class Chunk:
    phien_ban_id: int
    van_ban_id: int
    key: str                  # vd 'dieu 173/khoan 1/diem a' (cùng dạng src/validate/vbhn.key_of)
    loai: str
    hieu_luc_tu: str
    hieu_luc_den: str | None
    noi_dung: str             # chữ riêng của nút (để hiển thị)
    text: str                 # chữ đưa vào embedding và FTS: có thêm ngữ cảnh
    hash: str


def _chu(s: str | None) -> str:
    return (s or "").strip()


def _lead(text: str, toi_da: int) -> str:
    if len(text) <= toi_da:
        return text
    cat = text[:toi_da].rsplit(" ", 1)[0].rstrip(",;: ")
    return cat + "…"


def hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


_SQL = """SELECT p.id, p.don_vi_id, d.cha_id, d.loai, p.ky_hieu, p.tieu_de, p.noi_dung, p.hieu_luc_tu, p.hieu_luc_den
          FROM phien_ban_noi_dung p JOIN don_vi_luat d ON d.id = p.don_vi_id
          WHERE d.van_ban_id = ? ORDER BY d.id, p.hieu_luc_tu"""


def build_chunks(conn: sqlite3.Connection, van_ban_id: int, *, lead_toi_da: int = LEAD_TOI_DA) -> list[Chunk]:
    rows = conn.execute(_SQL, (van_ban_id,)).fetchall()
    units: dict[int, tuple[int | None, str]] = {}          # id nút -> (cha_id, loai)
    versions: dict[int, list] = {}                          # id nút -> các phiên bản theo ngày bắt đầu
    for r in rows:
        units[r["don_vi_id"]] = (r["cha_id"], r["loai"])
        versions.setdefault(r["don_vi_id"], []).append(r)

    def at(uid: int, ngay: str):
        vs = versions.get(uid, [])
        for v in vs:
            if v["hieu_luc_tu"] <= ngay < (v["hieu_luc_den"] or VO_CUC):
                return v
        return vs[0] if vs else None

    def key(uid: int, ngay: str) -> str:
        v = at(uid, ngay)
        cha, loai = units[uid]
        parent_key = key(cha, ngay) if (cha is not None and loai != "dieu") else None
        return key_of(loai, v["ky_hieu"], parent_key)

    def dau_dieu(dv) -> str:
        td = _chu(dv["tieu_de"])
        return f"Điều {dv['ky_hieu']}. {td}" if td else f"Điều {dv['ky_hieu']}."

    out: list[Chunk] = []
    for uid, vs in versions.items():
        cha, loai = units[uid]
        if loai in KHUNG:
            continue
        for v in vs:
            den = v["hieu_luc_den"]
            if den is not None and den <= v["hieu_luc_tu"]:
                continue                                    # khoảng rỗng: chưa từng có hiệu lực
            noi, td = _chu(v["noi_dung"]), _chu(v["tieu_de"])
            if not noi and not (loai == "dieu" and td):
                continue
            ngay = v["hieu_luc_tu"]
            anc: dict[str, object] = {}
            cur = cha
            while cur is not None:
                cha_c, loai_c = units[cur]
                pv = at(cur, ngay)
                if pv is not None and loai_c in ("dieu", "khoan"):
                    anc[loai_c] = pv
                cur = cha_c
            if loai == "dieu":
                lines = [dau_dieu(v)] + ([noi] if noi else [])
            else:
                lines = [dau_dieu(anc["dieu"])] if "dieu" in anc else []
                if loai == "khoan":
                    lines.append(f"Khoản {v['ky_hieu']}: {noi}")
                elif loai == "diem":
                    if "khoan" in anc:
                        k = anc["khoan"]
                        lines.append(f"Khoản {k['ky_hieu']}: {_lead(_chu(k['noi_dung']), lead_toi_da)}")
                    lines.append(f"Điểm {v['ky_hieu']}: {noi}")
                else:
                    lines.append(noi)
            text = "\n".join(lines)
            out.append(Chunk(v["id"], van_ban_id, key(uid, ngay), loai, ngay, den, noi, text, hash_text(text)))
    out.sort(key=lambda c: c.phien_ban_id)
    return out


def van_tay(chunks: list[Chunk]) -> str:
    """Dấu vân tay của tập đoạn: đổi nếu id phiên bản, ngày hiệu lực hoặc chữ đổi. Dùng để biết chỉ mục đã cũ chưa."""
    h = hashlib.sha256()
    for c in chunks:
        h.update(f"{c.phien_ban_id}|{c.hieu_luc_tu}|{c.hieu_luc_den}|{c.hash}\n".encode("utf-8"))
    return h.hexdigest()
