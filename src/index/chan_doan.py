"""Chẩn đoán câu hỏi sinh sẵn (doc2query) và quyết định có NÊN dùng chúng hay không. Chạy offline trên chỉ mục, không gọi LLM.

Vì sao có module này: lần đầu dùng câu hỏi sinh sẵn (1708 câu, qwen2.5:3b, lời nhắc có ví dụ) kết quả tệ hơn không dùng và càng
tăng hệ số càng tệ. Đo lại trên chính dữ liệu đó (128 câu thử = 58 câu kiểm tra + 70 câu dev) cho thấy:
  - chỉ 38% câu sinh tìm ra đúng Điều nguồn ở hạng 1; xếp hạng CHỈ bằng câu sinh đạt Hit@1 26% so với 69% khi xếp bằng chữ luật;
  - khi "chữ luật" và "câu sinh" bất đồng, câu sinh đúng 9% còn chữ luật đúng 64% (điểm câu sinh càng cao càng KHÔNG đáng tin,
    vì nhiều câu cao điểm là câu chép từ ví dụ trong lời nhắc, lặp ở hàng chục Điều);
  - không công thức kết hợp nào hơn không dùng vượt mức nhiễu (max-sàn, z-score, RRF, xếp lại trong top-N, hiệu chỉnh hub): sai ở dữ liệu, không ở công thức.
Nên cách đúng là KIỂM DỮ LIỆU trước khi dùng, bằng các số đo dưới đây; ngưỡng là heuristic có giải thích, không phải chân lý.
"""
from __future__ import annotations

import re
import sqlite3
import unicodedata
from datetime import date

import numpy as np

from src.index.cau_hoi import CHU_NUOC_NGOAI, _hang_dieu
from src.index.store import chuan_hoa

# Ngưỡng quyết định (heuristic):
NGUONG_TOP3 = 0.70         # >= 70% câu sinh phải đưa Điều nguồn vào top 3 khi tìm bằng chính câu đó (đúng tiêu chí của vòng lọc giu). Lần đầu mình đặt
                           #   ngưỡng hạng 1 >= 60% rồi đổi sang top 3 SAU khi thấy kết quả qwen3:8b (hạng 1 54%, top 3 76%, mà xếp hạng ngang chữ luật):
                           #   đổi sau khi thấy số, nên chỉ coi là cửa kiểm sơ bộ; quyết định cuối dựa vào quét hệ số khi câu sinh đã phủ gần hết Điều.
NGUONG_TRUNG = 0.03        # <= 3% câu sinh trùng/gần trùng câu của Điều khác (câu chép ví dụ, câu chung chung): chúng không phân biệt được Điều nào
NGUONG_CUU_PHA = 0.5       # (số câu chữ luật sai mà câu sinh cứu được) / (số câu chữ luật đúng mà câu sinh phá) >= 0.5, trong "thế giới đóng" (xem so_phieu)
NGUONG_PHU = 0.9           # câu sinh phải phủ >= 90% Điều về tội phạm thì kết quả quét hệ số mới đáng tin (ít hơn: Điều không có câu sinh không bị gây nhiễu)
GAN_TRUNG = 0.95           # cosine >= 0.95 với câu của Điều khác coi là gần như cùng một câu


def chuan_chu(t: str) -> str:
    return re.sub(r"\W+", " ", unicodedata.normalize("NFC", t).lower()).strip()


def _toi_da_theo_nhom(S: np.ndarray, nhom: np.ndarray, n: int) -> np.ndarray:
    """S: (số câu, số cột); nhom: nhãn nhóm 0..n-1 của từng cột. Trả (số câu, n) = max theo nhóm; nhóm rỗng = -inf."""
    ra = np.full((S.shape[0], n), -np.inf, dtype=np.float32)
    if not S.shape[1]:
        return ra
    o = np.argsort(nhom, kind="stable")
    g = nhom[o]
    dau = np.flatnonzero(np.r_[True, g[1:] != g[:-1]])
    ra[:, g[dau]] = np.maximum.reduceat(S[:, o], dau, axis=1)
    return ra


def _cau_hoi_co_vec(idx: sqlite3.Connection, model: str, chi_giu: bool = False):
    sql = ("SELECT s.rowid AS rid, s.dieu AS dieu, s.cau_hoi AS cau_hoi, s.giu AS giu, v.vec AS vec FROM cau_hoi_sinh s "
           "JOIN vec_cache v ON v.hash = s.hash AND v.model = ?" + (" WHERE s.giu = 1" if chi_giu else ""))
    rs = idx.execute(sql, (model,)).fetchall()
    Q = np.vstack([np.frombuffer(r["vec"], dtype="<f4") for r in rs]) if rs else np.zeros((0, 0), dtype=np.float32)
    return rs, Q


def _co_trung(rs, Q: np.ndarray, nguong: float) -> np.ndarray:
    """Mảng bool theo từng câu: trùng chữ, hoặc cosine >= nguong, với một câu của Điều KHÁC."""
    n = len(rs)
    co = np.zeros(n, dtype=bool)
    if n < 2:
        return co
    dieu = sorted({r["dieu"] for r in rs})
    ma = {d: i for i, d in enumerate(dieu)}
    nhan = np.array([ma[r["dieu"]] for r in rs])
    theo_chu: dict[str, set[str]] = {}
    for r in rs:
        theo_chu.setdefault(chuan_chu(r["cau_hoi"]), set()).add(r["dieu"])
    for i, r in enumerate(rs):
        if len(theo_chu[chuan_chu(r["cau_hoi"])]) > 1:
            co[i] = True
    for a in range(0, n, 1024):                                     # theo khối để không dựng ma trận n x n khổng lồ
        S = Q[a:a + 1024] @ Q.T
        S[nhan[a:a + 1024, None] == nhan[None, :]] = -1.0           # cùng Điều không tính là trùng
        co[a:a + 1024] |= S.max(axis=1) >= nguong
    return co


def loc_trung(idx: sqlite3.Connection, model: str, nguong: float = GAN_TRUNG) -> dict:
    """Đặt giu = 0 cho câu trùng chữ hoặc gần trùng (cosine >= nguong) với câu của Điều khác. Câu như vậy không phân biệt được Điều nào
    (thường là câu chép từ ví dụ trong lời nhắc, hoặc câu chung chung); cả hai phía đều bị bỏ. Chạy SAU loc_vong (vì loc_vong đặt lại giu)."""
    rs, Q = _cau_hoi_co_vec(idx, model)
    if not rs:
        return {"so_cau": 0, "trung": 0, "loai": 0}
    co = _co_trung(rs, Q, nguong)
    loai = sum(1 for r, c in zip(rs, co) if c and r["giu"] == 1)
    with idx:
        idx.executemany("UPDATE cau_hoi_sinh SET giu = 0 WHERE rowid = ?", [(r["rid"],) for r, c in zip(rs, co) if c])
    return {"so_cau": len(rs), "trung": int(co.sum()), "loai": loai}


def thong_ke_cau_hoi(idx: sqlite3.Connection, model: str, nguong_trung: float = GAN_TRUNG, chi_dieu: set[str] | None = None) -> dict:
    """Số đo chất lượng bản thân các câu sinh sẵn (không cần bộ câu hỏi nào): vòng khứ hồi, trùng giữa các Điều, chữ nước ngoài, độ phủ.
    chi_dieu: chỉ tính các câu của những Điều này (vd các Điều về tội phạm trong bộ dev), trùng vẫn xét với MỌI Điều."""
    tong = idx.execute("SELECT COUNT(*) FROM cau_hoi_sinh").fetchone()[0]
    rs, Q = _cau_hoi_co_vec(idx, model)
    ra = {"tong": tong, "co_vec": 0, "so_dieu": 0, "hang1": 0, "top3": 0, "giu": 0, "dieu_du_3": 0,
          "chu_ngoai": 0, "trung": 0, "ti_hang1": 0.0, "ti_top3": 0.0, "ti_trung": 0.0}
    if not rs:
        return ra
    trung_all = _co_trung(rs, Q, nguong_trung)
    chon = [i for i, r in enumerate(rs) if chi_dieu is None or r["dieu"] in chi_dieu]
    if not chon:
        return ra
    rs_c, Q_c, trung = [rs[i] for i in chon], Q[chon], trung_all[chon]
    n = len(rs_c)
    hang = _hang_dieu(idx, model, Q_c, [r["dieu"] for r in rs_c])
    giu_theo_dieu: dict[str, int] = {}
    for r in rs_c:
        if r["giu"] == 1:
            giu_theo_dieu[r["dieu"]] = giu_theo_dieu.get(r["dieu"], 0) + 1
    ra.update(co_vec=n, so_dieu=len({r["dieu"] for r in rs_c}), hang1=sum(1 for h in hang if h == 1),
              top3=sum(1 for h in hang if h is not None and h <= 3), giu=sum(1 for r in rs_c if r["giu"] == 1),
              dieu_du_3=sum(1 for v in giu_theo_dieu.values() if v >= 3),
              chu_ngoai=sum(1 for r in rs_c if CHU_NUOC_NGOAI.search(r["cau_hoi"])), trung=int(trung.sum()))
    ra.update(ti_hang1=ra["hang1"] / n, ti_top3=ra["top3"] / n, ti_trung=ra["trung"] / n)
    return ra


def _chi_so(hang: list[int | None]) -> dict:
    n = len(hang)
    return {"hit1": sum(1 for r in hang if r and r <= 1) / n, "hit3": sum(1 for r in hang if r and r <= 3) / n,
            "hit5": sum(1 for r in hang if r and r <= 5) / n, "mrr": sum(1 / r for r in hang if r) / n}


def so_phieu(idx: sqlite3.Connection, emb, bo: list[dict], ngay: str | None = None) -> dict:
    """Trên một bộ câu hỏi có đáp án, cho "chữ luật" và "câu sinh" mỗi bên chọn Điều hạng 1 rồi so: khi hai bên BẤT ĐỒNG ai đúng hơn?
    cuu = chữ luật sai mà câu sinh đúng (mức tối đa câu sinh có thể cứu được); pha = chữ luật đúng mà câu sinh sai (mức tối đa câu sinh có thể phá).
    Chỉ dùng câu sinh có giu = 1."""
    ngay = ngay or date.today().isoformat()
    model = emb.name
    ch = idx.execute("""SELECT c.key AS key, v.vec AS vec FROM chunk c JOIN vec_cache v ON v.hash = c.hash AND v.model = ?
                        WHERE c.hieu_luc_tu <= ? AND (c.hieu_luc_den IS NULL OR ? < c.hieu_luc_den)""", (model, ngay, ngay)).fetchall()
    if not ch:
        raise ValueError("chưa có vector đoạn nào cho mô hình này (chạy scripts/build_index.py)")
    rs, Q = _cau_hoi_co_vec(idx, model, chi_giu=True)
    if not rs:
        raise ValueError("chưa có câu hỏi sinh sẵn nào được giữ (chạy scripts/sinh_cau_hoi.py)")
    ten = sorted({r["key"].split("/")[0] for r in ch})
    vt = {t: i for i, t in enumerate(ten)}
    M = np.vstack([np.frombuffer(r["vec"], dtype="<f4") for r in ch])
    q = chuan_hoa(emb.embed([c["cau_hoi"] for c in bo]))
    C = _toi_da_theo_nhom(q @ M.T, np.array([vt[r["key"].split("/")[0]] for r in ch]), len(ten))
    ok = [i for i, r in enumerate(rs) if r["dieu"] in vt]
    K = _toi_da_theo_nhom(q @ Q[ok].T, np.array([vt[rs[i]["dieu"]] for i in ok]), len(ten))

    def hang(S: np.ndarray, dung: list[list[int]]):
        ra = []
        for i, ds in enumerate(dung):
            tot = [d for d in ds if np.isfinite(S[i, d])]
            ra.append(min(1 + int((S[i] > S[i, d]).sum()) for d in tot) if tot else None)
        return ra

    dung = [[vt[f"dieu {d}"] for d in c["dieu"] if f"dieu {d}" in vt] for c in bo]
    co_q = np.isfinite(K.max(axis=1))
    # THẾ GIỚI ĐÓNG: cả hai bên chỉ được chọn trong số Điều ĐÃ CÓ câu sinh. Nếu để chữ luật chọn giữa mọi Điều mà câu sinh chỉ chọn giữa vài chục
    # Điều đã sinh thì câu sinh được ưu ái ("cứu 13 / phá 4" trong khi so công bằng chỉ là 5 / 4: chữ luật ngang câu sinh, 88% / 89%).
    cot = np.flatnonzero(np.isfinite(K.max(axis=0)))
    ngoai = np.setdiff1d(np.arange(len(ten)), cot)
    C = C.copy()
    C[:, ngoai] = -np.inf
    # Chỉ so phiếu trên câu mà Điều đáp án CÓ câu sinh: nếu câu sinh mới phủ một phần luật thì các câu còn lại câu sinh không thể đúng,
    # đếm vào chỉ làm kết quả giả tệ ("cứu 0 / phá 52").
    phu = [i for i in range(len(bo)) if any(np.isfinite(K[i, d]) for d in dung[i])]
    ra = {"n": len(phu), "n_tong": len(bo), "n_ung_vien": int(len(cot))}
    if not phu:
        zero = {"hit1": 0.0, "hit3": 0.0, "hit5": 0.0, "mrr": 0.0}
        return {**ra, "chu": zero, "cau_hoi": dict(zero), "dong_y": 0, "bat_dong": 0, "chu_dung_khi_bat_dong": 0,
                "cau_hoi_dung_khi_bat_dong": 0, "cuu": 0, "pha": 0}
    C, K, dung, co_q = C[phu], K[phu], [dung[i] for i in phu], co_q[phu]
    hc, hq = hang(C, dung), hang(K, dung)
    top_c, top_q = C.argmax(axis=1), K.argmax(axis=1)
    n = len(phu)
    dc = [top_c[i] in dung[i] for i in range(n)]
    dq = [bool(co_q[i]) and top_q[i] in dung[i] for i in range(n)]
    bat = [i for i in range(n) if co_q[i] and top_c[i] != top_q[i]]
    return {**ra, "chu": _chi_so(hc), "cau_hoi": _chi_so(hq), "dong_y": sum(1 for i in range(n) if co_q[i] and top_c[i] == top_q[i]),
            "bat_dong": len(bat), "chu_dung_khi_bat_dong": sum(1 for i in bat if dc[i]), "cau_hoi_dung_khi_bat_dong": sum(1 for i in bat if dq[i]),
            "cuu": sum(1 for i in range(n) if not dc[i] and dq[i]), "pha": sum(1 for i in range(n) if dc[i] and not dq[i])}


def ti_le_cuu_pha(ph: dict) -> float | None:
    """cuu / pha; None nếu cả hai bằng 0 (câu sinh không có tác dụng gì); vô cực nếu chỉ cứu không phá."""
    if ph["pha"] == 0:
        return None if ph["cuu"] == 0 else float("inf")
    return ph["cuu"] / ph["pha"]


MIN_PHIEU = 20             # cần ít nhất 20 câu dev có đáp án thuộc Điều đã sinh mới so phiếu được (ít hơn thì cứu/phá chỉ là nhiễu)
MIN_DIEU_DAI_DIEN = 100    # thống kê bản thân câu sinh chỉ đáng tin khi mẫu đủ rộng: sinh cho Điều đầu (Phần chung) cho số đo lệch hẳn


def ket_luan(tk: dict, ph: dict | None, phu: tuple[int, int] | None = None) -> tuple[str, list[str]]:
    """(trang_thai, ly do). phu = (số Điều về tội phạm đã có câu giữ, tổng số Điều về tội phạm).
    'DAT'      = qua mọi ngưỡng và câu sinh đã phủ >= NGUONG_PHU: đáng quét hệ số;
    'DAT_SO_BO'= qua mọi ngưỡng nhưng mới phủ một phần: đáng sinh nốt (số đo trên mẫu một phần lạc quan, chưa quét hệ số);
    'CHUA_DAT' = trượt ngưỡng: giữ chỉ dùng chữ luật, sinh lại (đổi model/lời nhắc);
    'THIEU'    = mẫu chưa đủ để kết luận (phủ ít Điều, ít câu dev so được)."""
    if not tk["co_vec"]:
        return "THIEU", ["chưa có câu sinh nào có vector"]
    ly: list[str] = []
    if tk["ti_top3"] < NGUONG_TOP3:
        ly.append(f"chỉ {tk['ti_top3']:.0%} câu sinh đưa Điều nguồn vào top 3 khi tìm bằng chính câu đó (cần ≥ {NGUONG_TOP3:.0%})")
    if tk["ti_trung"] > NGUONG_TRUNG:
        ly.append(f"{tk['ti_trung']:.1%} câu sinh trùng hoặc gần trùng câu của Điều khác (cần ≤ {NGUONG_TRUNG:.0%})")
    if tk["chu_ngoai"]:
        ly.append(f"{tk['chu_ngoai']} câu còn chữ nước ngoài")
    if ly and tk["so_dieu"] >= MIN_DIEU_DAI_DIEN:
        return "CHUA_DAT", ly                                # mẫu rộng mà đã hỏng thì khỏi cần so phiếu
    if ph is None:
        return "THIEU", ly + ["chưa so phiếu với chữ luật (chạy lại không kèm --chi-thong-ke; cần Ollama để nhúng ~70 câu dev)"]
    if ph["n"] < MIN_PHIEU:
        return "THIEU", ly + [f"chưa so phiếu được: mới có {ph['n']} câu dev có đáp án thuộc Điều đã sinh (cần ≥ {MIN_PHIEU}); mẫu "
                              f"{tk['so_dieu']} Điều cũng chưa chắc đại diện (nếu là các Điều đầu thì toàn Phần chung, không phải điều về tội phạm)"]
    r = ti_le_cuu_pha(ph)
    if r is None or (r != float("inf") and r < NGUONG_CUU_PHA):
        ly.append(f"khi bất đồng với chữ luật, câu sinh cứu {ph['cuu']} câu nhưng phá {ph['pha']} câu (cần cứu/phá ≥ {NGUONG_CUU_PHA})")
    if ly:
        return "CHUA_DAT", ly
    if phu is not None and phu[1] and phu[0] < NGUONG_PHU * phu[1]:
        return "DAT_SO_BO", [f"câu sinh mới phủ {phu[0]}/{phu[1]} Điều về tội phạm ({phu[0] / phu[1]:.0%}); cần ≥ {NGUONG_PHU:.0%} để quét hệ số có giá trị"]
    return "DAT", []


def ket_luan_quet(hang: list[tuple[float, float, float]], nhieu_hit1: float = 0.03, nhieu_mrr: float = 0.03) -> tuple[bool, str]:
    """hang: [(he_so, hit1, mrr), ...] có dòng he_so = 0 là baseline. Chỉ coi là có lợi nếu có ít nhất 2 hệ số LIỀN KỀ cùng hơn baseline
    >= nhieu_hit1 (Hit@1) hoặc >= nhieu_mrr (MRR) và không hệ số nào trong dải đó tệ hơn baseline quá nửa mức nhiễu. 'Hệ số ổn định, đừng chọn ô cao nhất'."""
    hang = sorted(hang)
    base = next(((h1, m) for h, h1, m in hang if h == 0), None)
    if base is None:
        return False, "thiếu dòng baseline (hệ số 0)"
    thu = [(h, h1, m) for h, h1, m in hang if h > 0]
    tot = [h1 - base[0] >= nhieu_hit1 or m - base[1] >= nhieu_mrr for h, h1, m in thu]
    te = [h1 - base[0] < -nhieu_hit1 / 2 or m - base[1] < -nhieu_mrr / 2 for h, h1, m in thu]
    for i in range(len(thu) - 1):
        if tot[i] and tot[i + 1] and not te[i] and not te[i + 1]:
            return True, f"hệ số {thu[i][0]}–{thu[i + 1][0]} hơn baseline ổn định (Hit@1 {thu[i][1]:.0%}/{thu[i + 1][1]:.0%} so với {base[0]:.0%})"
    return False, "không có dải ≥ 2 hệ số liền kề nào hơn baseline vượt ngưỡng nhiễu: GIỮ hệ số 0 (không dùng câu sinh sẵn)"
