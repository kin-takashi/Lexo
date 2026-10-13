"""Kho chỉ mục: file SQLite RIÊNG (db/chi_muc.sqlite), dẫn xuất từ CSDL luật, dựng lại được bất kỳ lúc nào.

  chunk      các đoạn (đồng bộ lại từ CSDL luật mỗi lần chạy build_index)
  fts        FTS5 trên chữ của đoạn, rowid = phien_ban_id (tìm từ khoá, BM25)
  vec_cache  vector theo (hash chữ, mô hình): SỐNG SÓT khi đồng bộ lại, nên đổi chữ chỉ tính lại phần đổi
  cau_hoi_sinh  câu hỏi đời thường do LLM sinh sẵn cho từng Điều (scripts/sinh_cau_hoi.py), cũng có vector trong vec_cache
  meta       dấu vân tay của tập đoạn lúc đồng bộ

Vector lưu dạng float32 little-endian đã chuẩn hoá độ dài 1 (cosine = tích vô hướng); đây cũng là định dạng BLOB mà
sqlite-vec đọc được, nên sau này có thể chuyển sang sqlite-vec mà không phải tính lại.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

import numpy as np

from src.index.chunks import Chunk, van_tay

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS chunk (
    phien_ban_id INTEGER PRIMARY KEY,
    van_ban_id   INTEGER NOT NULL,
    key          TEXT NOT NULL,
    loai         TEXT NOT NULL,
    hieu_luc_tu  TEXT NOT NULL,
    hieu_luc_den TEXT,
    noi_dung     TEXT NOT NULL,
    text         TEXT NOT NULL,
    hash         TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chunk_hash ON chunk (hash);
CREATE INDEX IF NOT EXISTS idx_chunk_ngay ON chunk (hieu_luc_tu, hieu_luc_den);
CREATE TABLE IF NOT EXISTS vec_cache (
    hash  TEXT NOT NULL,
    model TEXT NOT NULL,
    dim   INTEGER NOT NULL,
    vec   BLOB NOT NULL,
    PRIMARY KEY (hash, model)
);
CREATE TABLE IF NOT EXISTS cau_hoi_sinh (
    dieu      TEXT NOT NULL,      -- khoá Điều, vd 'dieu 173'
    hash_dieu TEXT NOT NULL,      -- mã băm chữ của Điều lúc sinh (đổi chữ -> sinh lại)
    mo_hinh   TEXT NOT NULL,      -- LLM đã sinh
    stt       INTEGER NOT NULL,
    cau_hoi   TEXT NOT NULL,
    hash      TEXT NOT NULL,      -- mã băm câu hỏi, khoá vào vec_cache
    giu       INTEGER NOT NULL DEFAULT 1,   -- qua lọc vòng (Điều nguồn đứng hạng đầu khi tìm bằng chính câu này)
    PRIMARY KEY (dieu, mo_hinh, stt)
);
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(text, tokenize='unicode61 remove_diacritics 0');
"""


def open_index(path: str | Path) -> sqlite3.Connection:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    if 'giu' not in {r['name'] for r in conn.execute('PRAGMA table_info(cau_hoi_sinh)')}:      # chỉ mục cũ chưa có cột giu
        conn.execute('ALTER TABLE cau_hoi_sinh ADD COLUMN giu INTEGER NOT NULL DEFAULT 1')
        conn.commit()
    return conn


def sync_chunks(idx: sqlite3.Connection, chunks: list[Chunk]) -> str:
    """Thay toàn bộ bảng chunk và fts bằng `chunks` (nhanh, không đụng vec_cache). Trả về dấu vân tay."""
    vt = van_tay(chunks)
    with idx:
        idx.execute("DELETE FROM chunk")
        idx.execute("DELETE FROM fts")
        idx.executemany(
            "INSERT INTO chunk (phien_ban_id, van_ban_id, key, loai, hieu_luc_tu, hieu_luc_den, noi_dung, text, hash) VALUES (?,?,?,?,?,?,?,?,?)",
            [(c.phien_ban_id, c.van_ban_id, c.key, c.loai, c.hieu_luc_tu, c.hieu_luc_den, c.noi_dung, c.text, c.hash) for c in chunks])
        idx.executemany("INSERT INTO fts (rowid, text) VALUES (?, ?)", [(c.phien_ban_id, c.text) for c in chunks])
        idx.execute("INSERT OR REPLACE INTO meta (k, v) VALUES ('van_tay', ?)", (vt,))
    return vt


def van_tay_da_luu(idx: sqlite3.Connection) -> str | None:
    r = idx.execute("SELECT v FROM meta WHERE k = 'van_tay'").fetchone()
    return r["v"] if r else None


def thieu_vector(idx: sqlite3.Connection, model: str) -> list[sqlite3.Row]:
    """Các (hash, text) khác nhau chưa có vector cho `model`, theo thứ tự phien_ban_id."""
    return idx.execute(
        """SELECT c.hash AS hash, MIN(c.text) AS text FROM chunk c
           LEFT JOIN vec_cache v ON v.hash = c.hash AND v.model = ?
           WHERE v.hash IS NULL GROUP BY c.hash ORDER BY MIN(c.phien_ban_id)""", (model,)).fetchall()


def thieu_vector_cau_hoi(idx: sqlite3.Connection, model: str) -> list[sqlite3.Row]:
    """Các câu hỏi sinh sẵn chưa có vector cho `model` (cột hash, text)."""
    return idx.execute(
        """SELECT c.hash AS hash, MIN(c.cau_hoi) AS text FROM cau_hoi_sinh c
           LEFT JOIN vec_cache v ON v.hash = c.hash AND v.model = ?
           WHERE v.hash IS NULL GROUP BY c.hash ORDER BY MIN(c.dieu)""", (model,)).fetchall()


def chuan_hoa(vecs) -> np.ndarray:
    a = np.asarray(vecs, dtype=np.float32)
    n = np.linalg.norm(a, axis=1, keepdims=True)
    n[n == 0] = 1.0
    return a / n


def luu_vector(idx: sqlite3.Connection, model: str, hashes: list[str], vecs) -> None:
    a = chuan_hoa(vecs)
    with idx:
        idx.executemany(
            "INSERT OR REPLACE INTO vec_cache (hash, model, dim, vec) VALUES (?,?,?,?)",
            [(h, model, a.shape[1], a[i].astype("<f4").tobytes()) for i, h in enumerate(hashes)])


def don_dep(idx: sqlite3.Connection) -> int:
    """Xoá vector của chữ không còn đoạn nào dùng. Trả về số dòng đã xoá."""
    with idx:
        cur = idx.execute("DELETE FROM vec_cache WHERE hash NOT IN (SELECT hash FROM chunk) AND hash NOT IN (SELECT hash FROM cau_hoi_sinh)")
    return cur.rowcount


def thong_ke(idx: sqlite3.Connection, model: str) -> dict:
    n_chunk = idx.execute("SELECT COUNT(*) FROM chunk").fetchone()[0]
    n_hash = idx.execute("SELECT COUNT(DISTINCT hash) FROM chunk").fetchone()[0]
    n_thieu = len(thieu_vector(idx, model))
    return {"so_doan": n_chunk, "so_chu_khac_nhau": n_hash, "chua_co_vector": n_thieu, "da_co_vector": n_hash - n_thieu}
