"""Tìm kiếm lai: vector (cosine) + từ khoá (FTS5/BM25), gộp bằng RRF, LỌC THEO NGÀY HIỆU LỰC TRƯỚC khi xếp hạng.

Lọc theo ngày trước (không lọc sau top-k) vì lọc sau có thể loại mất kết quả đúng nằm ngoài top-k ban đầu.
Quy mô vài nghìn vector nên quét chính xác bằng numpy, không cần chỉ mục gần đúng.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date

import numpy as np

CHE_DO = ("hybrid", "vector", "fts")
# Mặc định theo kết quả đo (scripts/danh_gia.py --quet, 58 câu): chưa cấu hình hybrid nào vượt vector đơn thuần ở Hit@1/MRR.
MAC_DINH = "vector"


@dataclass
class Hit:
    phien_ban_id: int
    key: str
    dieu: str                          # khoá Điều chứa đoạn, vd 'dieu 173'
    hieu_luc_tu: str
    hieu_luc_den: str | None
    noi_dung: str
    text: str
    diem: float                        # điểm RRF (càng cao càng tốt)
    cosine: float | None = None
    hang_vector: int | None = None
    hang_fts: int | None = None


@dataclass
class DieuHit:
    dieu: str
    tieu_de: str                       # dòng đầu của đoạn: 'Điều 173. Tội trộm cắp tài sản'
    diem: float
    tot_nhat: Hit
    so_doan: int                       # số đoạn của Điều này lọt vào danh sách ứng viên
    doan_noi_dung: Hit | None = None   # đoạn tốt nhất CÓ chữ riêng (đoạn tốt nhất có thể chỉ là tiêu đề Điều)


@dataclass
class KetQua:
    hits: list[Hit]
    canh_bao: list[str] = field(default_factory=list)


# Từ chức năng tiếng Việt chung chung (không chọn theo bộ câu hỏi nào): có mặt ở hầu hết đoạn luật nên không giúp phân biệt.
TU_DUNG = frozenset("""của và là bị sao thì các những một có được cho với để này khi nào gì không mà rồi ra vào trong như
hay hoặc đã sẽ đang cũng về tại do bởi nên thế ở lại đi lên xuống người ai nếu thế""".split())


def _tu_khoa(cau_hoi: str, bo_tu_dung: bool = False) -> str:
    toks = re.findall(r"\w+", cau_hoi.lower())
    if bo_tu_dung:
        toks = [t for t in toks if t not in TU_DUNG]
    return " OR ".join(f'"{t}"' for t in dict.fromkeys(toks))


def tim(idx: sqlite3.Connection, cau_hoi: str, *, embedder, ngay: str | None = None, k: int = 10,
        che_do: str = MAC_DINH, n_ung_vien: int = 50, rrf_k: int = 60,
        trong_fts: float = 1.0, bo_tu_dung: bool = False, he_so_cau_hoi: float = 0.0) -> KetQua:
    if che_do not in CHE_DO:
        raise ValueError(f"che_do phải là một trong {CHE_DO}")
    ngay = ngay or date.today().isoformat()
    canh_bao: list[str] = []
    rows = idx.execute(
        """SELECT phien_ban_id, key, hieu_luc_tu, hieu_luc_den, noi_dung, text, hash FROM chunk
           WHERE hieu_luc_tu <= ? AND (hieu_luc_den IS NULL OR ? < hieu_luc_den)""", (ngay, ngay)).fetchall()
    if not rows:
        return KetQua([], [f"không có đoạn nào có hiệu lực tại ngày {ngay}"])
    by_id = {r["phien_ban_id"]: r for r in rows}

    hang_v: dict[int, int] = {}
    cos: dict[int, float] = {}
    if che_do in ("hybrid", "vector"):
        model = embedder.name
        vecs = {r["hash"]: r["vec"] for r in idx.execute("SELECT hash, vec FROM vec_cache WHERE model = ?", (model,))}
        co = [r for r in rows if r["hash"] in vecs]
        if len(co) < len(rows):
            canh_bao.append(f"{len(rows) - len(co)}/{len(rows)} đoạn chưa có vector (chạy scripts/build_index.py), bỏ qua phần đó khi xếp hạng vector")
        if co:
            m = np.vstack([np.frombuffer(vecs[r["hash"]], dtype="<f4") for r in co])
            q = np.asarray(embedder.embed([cau_hoi])[0], dtype=np.float32)
            n = np.linalg.norm(q)
            q = q / n if n else q
            if q.shape[0] != m.shape[1]:
                raise ValueError(f"vector câu hỏi {q.shape[0]} chiều khác vector đã lưu {m.shape[1]} chiều (sai mô hình?)")
            diem = m @ q
            if he_so_cau_hoi > 0:
                _them_cau_hoi(idx, model, q, co, diem, he_so_cau_hoi, canh_bao)
            for rank, i in enumerate(np.argsort(-diem)[:n_ung_vien], 1):
                pid = co[i]["phien_ban_id"]
                hang_v[pid], cos[pid] = rank, float(diem[i])
        elif che_do == "vector":
            canh_bao.append("chưa có vector nào cho mô hình này")

    hang_f: dict[int, int] = {}
    if che_do in ("hybrid", "fts"):
        mq = _tu_khoa(cau_hoi, bo_tu_dung)
        if mq:
            rank = 0
            for r in idx.execute("SELECT rowid FROM fts WHERE fts MATCH ? ORDER BY bm25(fts) LIMIT 2000", (mq,)):
                if r["rowid"] in by_id:
                    rank += 1
                    hang_f[r["rowid"]] = rank
                    if rank >= n_ung_vien:
                        break

    diem_rrf: dict[int, float] = {}
    for hang, w in ((hang_v, 1.0), (hang_f, trong_fts)):
        for pid, rk in hang.items():
            diem_rrf[pid] = diem_rrf.get(pid, 0.0) + w / (rrf_k + rk)
    xep = sorted(diem_rrf, key=lambda p: (-diem_rrf[p], -(cos.get(p) or -1.0), p))[:k]
    hits = []
    for pid in xep:
        r = by_id[pid]
        hits.append(Hit(pid, r["key"], r["key"].split("/")[0], r["hieu_luc_tu"], r["hieu_luc_den"], r["noi_dung"], r["text"],
                        diem_rrf[pid], cos.get(pid), hang_v.get(pid), hang_f.get(pid)))
    return KetQua(hits, canh_bao)


def _them_cau_hoi(idx, model, q, co, diem, he_so, canh_bao) -> None:
    """Câu hỏi sinh sẵn: điểm của Điều >= he_so x (cosine lớn nhất giữa câu hỏi người dùng và các câu hỏi sinh sẵn của Điều đó).
    Nâng điểm của đoạn đang khớp nhất trong Điều (sửa `diem` tại chỗ), nên hiện ra đúng đoạn có chữ liên quan."""
    from src.index.cau_hoi import PHIEN_BAN_LENH
    ban = idx.execute("SELECT v FROM meta WHERE k = 'cau_hoi_lenh'").fetchone()
    if ban is None or ban["v"] != PHIEN_BAN_LENH:                       # câu sinh bằng lời nhắc cũ chép ví dụ khắp nơi: dùng chỉ làm kết quả xấu đi
        canh_bao.append("câu hỏi sinh sẵn trong chỉ mục được viết bằng lời nhắc cũ hoặc không rõ phiên bản, KHÔNG dùng "
                        "(chạy lại scripts/sinh_cau_hoi.py để sinh bằng lời nhắc hiện tại)")
        return
    rows = idx.execute("SELECT c.dieu AS dieu, v.vec AS vec FROM cau_hoi_sinh c JOIN vec_cache v ON v.hash = c.hash AND v.model = ? WHERE c.giu = 1",
                       (model,)).fetchall()
    if not rows:
        canh_bao.append("chưa có câu hỏi sinh sẵn cho mô hình này (chạy scripts/sinh_cau_hoi.py), bỏ qua phần đó")
        return
    qm = np.vstack([np.frombuffer(r["vec"], dtype="<f4") for r in rows])
    if qm.shape[1] != q.shape[0]:
        raise ValueError("vector câu hỏi sinh sẵn khác số chiều (sai mô hình?)")
    sim = qm @ q
    tot: dict[str, float] = {}
    for r, sc in zip(rows, sim):
        if sc > tot.get(r["dieu"], -2.0):
            tot[r["dieu"]] = float(sc)
    theo_dieu: dict[str, list[int]] = {}
    for i, r in enumerate(co):
        theo_dieu.setdefault(r["key"].split("/")[0], []).append(i)
    for d, sc in tot.items():
        ds = theo_dieu.get(d)
        if ds:
            i = max(ds, key=lambda j: diem[j])
            diem[i] = max(diem[i], he_so * sc)


def gop_theo_dieu(hits: list[Hit], k: int = 5) -> list[DieuHit]:
    """Gộp đoạn về Điều: điểm của Điều = điểm của đoạn tốt nhất (đáp án của người dùng thường là một Điều)."""
    best: dict[str, DieuHit] = {}
    for h in hits:                                     # hits đã xếp giảm dần
        if h.dieu not in best:
            best[h.dieu] = DieuHit(h.dieu, h.text.split("\n", 1)[0], h.diem, h, 1, h if h.noi_dung else None)
        else:
            d = best[h.dieu]
            d.so_doan += 1
            if d.doan_noi_dung is None and h.noi_dung:
                d.doan_noi_dung = h
    return sorted(best.values(), key=lambda d: -d.diem)[:k]
