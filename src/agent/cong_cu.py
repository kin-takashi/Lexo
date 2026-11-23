"""Lớp CÔNG CỤ của agent: mọi truy cập kho luật, chỉ mục tìm kiếm, Ollama và mô hình xếp lại nằm ở đây; lớp agent (agent.py) chỉ
gọi các hàm này. Tách như vậy để kiểm thử agent bằng công cụ giả (không cần Ollama, không cần kho thật).

Nguyên tắc (kế hoạch v2 mục 14): tra chính xác, lịch sử, so sánh, quan hệ văn bản là CODE xác định, không qua LLM. LLM chỉ dùng để
tách hành vi trong tình huống dài; vector chỉ để tìm theo nghĩa. Thiếu thành phần nào thì hạ cấp có thông báo, không im lặng:
  không có Ollama / bge-m3     → tìm theo từ khoá (FTS5, BM25) thay vì vector
  không có mô hình tách hành vi → tìm theo cả tình huống như MỘT truy vấn (mốc «không tách» của scripts/danh_gia_nhieu.py)
  không có mô hình xếp lại      → giữ thứ tự của tìm kiếm
"""
from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from src.config import ROOT, db_path, index_path, load_config
from src.index.cau_hoi import LLMError, gom_dieu
from src.index.chunks import build_chunks, van_tay
from src.index.embedder import EmbedError, HashEmbedder, OllamaEmbedder
from src.index.search import gop_theo_dieu, tim
from src.index.store import van_tay_da_luu
from src.index.tach_hanh_vi import LLMGiaTach, TachLLM, tach_mot
from src.index.tim_du import so_dieu
from src.index.xep_lai import BgeReranker, XepLaiError, xep_lai_top
from src.query import lookup as lk
from src.query.lookup import fmt_date

# Bộ luật CÓ THẬT nhưng kho chưa nạp, để khi người dùng chọn một ngày thuộc thời kỳ đó thì nói rõ «ngày này thuộc bộ luật X, Lexo chưa nạp»
# thay vì im lặng hoặc trả nhầm bộ luật khác. Tự bỏ qua khi kho đã có văn bản cùng số hiệu. tu = ngày bắt đầu hiệu lực, den = ngày ĐẦU TIÊN
# không còn hiệu lực (khoảng nửa mở). nam = các năm người dùng hay gõ sau «BLHS» để chỉ bộ luật này; nam_ban_hanh = năm thông qua.
LUAT_CHUA_NAP_MAC_DINH = [
    {"viet_tat": "BLHS", "so_hieu": "15/1999/QH10", "ten_ngan": "BLHS 1999",
     "ten": "Bộ luật hình sự năm 1999 (số 15/1999/QH10, đã được sửa đổi, bổ sung năm 2009 bởi Luật số 37/2009/QH12)",
     "tu": "2000-07-01", "den": "2018-01-01", "nam": [1999, 2009], "nam_ban_hanh": 1999},
    {"viet_tat": "BLHS", "so_hieu": "", "ten_ngan": "BLHS 1985", "ten": "Bộ luật hình sự năm 1985",
     "tu": "1986-01-01", "den": "2000-07-01", "nam": [1985], "nam_ban_hanh": 1985},
]

MAC_DINH_AGENT = {
    "luat_chua_nap": LUAT_CHUA_NAP_MAC_DINH,
    "tach_model": ["qwen3-8b-lexo-sach-n368", "lexo-tach"],     # mô hình tách hành vi: lấy cái đầu tiên Ollama đang có
    "so_dieu_moi_hanh_vi": 3,                                   # m = 3 (khớp scripts/danh_gia_nhieu.py)
    "so_dieu_khi_khong_tach": 5,                                # khi không tách được: hiển thị 5 Điều cho cả tình huống
    "xep_lai": False,                                           # mặc định tắt: cần onnxruntime + tải ~2,3 GB (scripts/tai_xep_lai.py)
    "xep_lai_w": 0.25,
    "xep_lai_top": 5,
    "mo_hinh_xep_lai": "models/bge-reranker-v2-m3",
    "thoi_gian_cho_ollama": 2.0,
    "thoi_gian_tach": 180,
}


class KhoLoi(RuntimeError):
    """Thiếu thứ không thể thiếu (kho luật). Thông báo viết cho người dùng cuối."""


def cau_hinh_agent(cfg: dict | None = None) -> dict:
    ch = dict(MAC_DINH_AGENT)
    ch.update((cfg or {}).get("agent") or {})
    if isinstance(ch["tach_model"], str):
        ch["tach_model"] = [ch["tach_model"]]
    return ch


def kiem_tra_ollama(endpoint: str, timeout: float = 2.0) -> tuple[bool, list[str]]:
    """(Ollama có trả lời không, tên các model đã tải)."""
    try:
        with urllib.request.urlopen(endpoint.rstrip("/") + "/api/tags", timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8"))
        return True, [str(m.get("name", "")) for m in data.get("models", [])]
    except (urllib.error.URLError, OSError, ValueError):
        return False, []


def co_model(ten: str, danh_sach: list[str]) -> bool:
    """«bge-m3» khớp «bge-m3» hoặc «bge-m3:latest»; «qwen3:8b» chỉ khớp đúng «qwen3:8b»."""
    return any(n == ten or (":" not in ten and n.startswith(ten + ":")) for n in danh_sach)


def _mo_chi_doc(path: Path) -> sqlite3.Connection:
    """Mở SQLite chỉ đọc, dùng được từ nhiều luồng (Streamlit chạy mỗi phiên ở một luồng); mọi truy cập đi qua CongCu._khoa."""
    try:
        c = sqlite3.connect(f"{path.resolve().as_uri()}?mode=ro", uri=True, check_same_thread=False)
        c.execute("SELECT 1 FROM sqlite_master LIMIT 1")
    except sqlite3.Error:
        c = sqlite3.connect(str(path), check_same_thread=False)
    c.row_factory = sqlite3.Row
    return c


def cat(s: str, n: int = 300) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def nhan_vi_tri(key: str) -> str:
    """'dieu 173/khoan 2/diem a' -> 'khoản 2, điểm a'; 'dieu 173' -> ''."""
    ten = {"khoan": "khoản", "diem": "điểm"}
    ra = []
    for p in key.split("/")[1:]:
        loai, _, ky = p.partition(" ")
        ra.append(f"{ten.get(loai, loai)} {ky}")
    return ", ".join(ra)


@dataclass
class DieuKetQua:
    """Một Điều trong kết quả tìm kiếm."""
    so: str                    # '173'
    khoa: str                  # 'dieu 173'
    tieu_de: str               # 'Điều 173. Tội trộm cắp tài sản'
    trich: str                 # đoạn chữ khớp nhất (cắt gọn)
    vi_tri: str                # 'khoản 1' - nơi đoạn khớp nằm; rỗng nếu khớp tiêu đề
    hang: int
    cosine: float | None = None


@dataclass
class LuatTaiNgay:
    """Bộ luật nào đang áp dụng vào một ngày. vb=None thì `ly_do` là câu giải thích viết cho người dùng."""
    ngay: str
    vb: sqlite3.Row | None
    ly_do: str = ""
    chua_nap: dict | None = None        # thời kỳ của bộ luật đã biết nhưng chưa nạp, nếu ngày rơi vào đó


class CongCu:
    def __init__(self, luat: sqlite3.Connection, chi_muc: sqlite3.Connection | None = None, *, embedder=None, tach_llm=None,
                 tach_ten: str | None = None, xep_lai=None, cau_hinh: dict | None = None, endpoint: str = "http://localhost:11434",
                 embed_ten: str = "bge-m3", kiem_tra_mang: bool = False, canh_bao_khoi_dong: list[str] | None = None):
        self.luat, self.chi_muc = luat, chi_muc
        self.ch = cau_hinh_agent({"agent": cau_hinh} if cau_hinh else None)
        self.endpoint, self.embed_ten = endpoint, embed_ten
        self.canh_bao_khoi_dong = list(canh_bao_khoi_dong or [])
        self.embedder, self.tach_llm, self.tach_ten, self._xep_lai = embedder, tach_llm, tach_ten, xep_lai
        self._tiem = {"embedder": embedder is not None, "tach": tach_llm is not None}      # đã truyền vào (giả/thử): làm_mới không ghi đè
        self._khoa = threading.RLock()
        self._ollama: tuple[bool, list[str]] = (False, [])
        self._loi_xep_lai: str | None = None
        self._van_ban_dieu: dict[str, str] | None = None
        self.xep_lai_mac_dinh = bool(self.ch["xep_lai"])
        if kiem_tra_mang:
            self.lam_moi()

    # ------------------------------------------------------------------ khởi tạo từ cấu hình

    @classmethod
    def mo(cls, *, db: str | Path | None = None, index: str | Path | None = None, gia: bool | None = None,
           kiem_tra_cu: bool = True) -> CongCu:
        """Mở kho thật theo config.yaml. Biến môi trường LEXO_DB / LEXO_INDEX ghi đè đường dẫn; LEXO_GIA=1 hoặc gia=True dùng
        vector giả + LLM tách giả (CHỈ để thử giao diện, kết quả không có nghĩa)."""
        cfg = load_config()
        dbp = Path(db or os.environ.get("LEXO_DB") or db_path())
        ip = Path(index or os.environ.get("LEXO_INDEX") or index_path())
        if not dbp.exists():
            raise KhoLoi(f"Chưa có kho luật ({dbp}). Cần nạp luật trước (xem README, các bước 1–3).")
        luat = _mo_chi_doc(dbp)
        chi_muc = _mo_chi_doc(ip) if ip.exists() else None
        canh_bao: list[str] = []
        if chi_muc is None:
            canh_bao.append(f"Chưa có chỉ mục tìm kiếm ({ip.name}); chức năng tìm theo mô tả chưa dùng được. Chạy: python scripts/build_index.py")
        elif kiem_tra_cu:
            canh_bao += _kiem_tra_chi_muc_cu(luat, chi_muc)
        local = cfg.get("llm_local") or {}
        endpoint = local.get("endpoint") or "http://localhost:11434"
        embed_ten = (cfg.get("embedding") or {}).get("ollama_model") or "bge-m3"
        gia = bool(os.environ.get("LEXO_GIA")) if gia is None else gia
        cc = cls(luat, chi_muc, cau_hinh=cfg.get("agent"), endpoint=endpoint, embed_ten=embed_ten, canh_bao_khoi_dong=canh_bao,
                 embedder=HashEmbedder() if gia else None, tach_llm=LLMGiaTach() if gia else None, tach_ten="gia" if gia else None)
        if not gia:
            cc.lam_moi()
        return cc

    def lam_moi(self) -> None:
        """Hỏi lại Ollama đang có gì (bấm «Kiểm tra lại» sau khi bật Ollama). Không đụng tới thành phần được truyền sẵn."""
        ok, models = kiem_tra_ollama(self.endpoint, float(self.ch["thoi_gian_cho_ollama"]))
        with self._khoa:
            self._ollama = (ok, models)
            if not self._tiem["embedder"]:
                self.embedder = OllamaEmbedder(self.embed_ten, self.endpoint, timeout=120, retries=1) if ok and co_model(self.embed_ten, models) else None
            if not self._tiem["tach"]:
                self.tach_llm = self.tach_ten = None
                for ten in self.ch["tach_model"]:
                    if ok and co_model(ten, models):
                        self.tach_ten = ten
                        self.tach_llm = TachLLM(ten, self.endpoint, dinh_dang="schema", no_think_mem="lexo" not in ten.lower(),
                                                timeout=int(self.ch["thoi_gian_tach"]), retries=1)
                        break

    # ------------------------------------------------------------------ trạng thái

    @property
    def co_vector(self) -> bool:
        return self.embedder is not None and self.chi_muc is not None

    @property
    def co_tach(self) -> bool:
        return self.tach_llm is not None

    @property
    def co_the_xep_lai(self) -> bool:
        """Có thể bật bước xếp lại không: mô hình ONNX đã tải và đủ thư viện."""
        if self._xep_lai is not None:
            return True
        thu_muc = ROOT / self.ch["mo_hinh_xep_lai"]
        return (thu_muc / "onnx" / "model.onnx").exists() and all(importlib.util.find_spec(m) for m in ("onnxruntime", "tokenizers"))

    def trang_thai(self) -> list[dict]:
        """Bảng trạng thái cho người dùng: [{'ten', 'ok', 'mo_ta'}]."""
        ok_ollama, models = self._ollama
        tt = self.thong_tin_kho()
        ra = [{"ten": "Kho luật", "ok": True, "mo_ta": f"{tt['ten']}: {tt['so_dieu']} Điều hiện hành, {len(tt['sua_doi'])} luật sửa đổi đã nạp"}]
        if self.chi_muc is None:
            ra.append({"ten": "Tìm theo mô tả", "ok": False, "mo_ta": "chưa dựng chỉ mục (python scripts/build_index.py)"})
        elif self.embedder is not None:
            ra.append({"ten": "Tìm theo mô tả", "ok": True, "mo_ta": f"theo nghĩa ({getattr(self.embedder, 'name', 'vector')}) + từ khoá"})
        else:
            ly_do = "Ollama chưa chạy" if not ok_ollama else f"Ollama chưa có model {self.embed_ten} (ollama pull {self.embed_ten})"
            ra.append({"ten": "Tìm theo mô tả", "ok": False, "mo_ta": f"chỉ theo từ khoá — {ly_do}"})
        if self.tach_llm is not None:
            ra.append({"ten": "Tách hành vi", "ok": True, "mo_ta": f"mô hình {self.tach_ten}"})
        else:
            ly_do = "Ollama chưa chạy" if not ok_ollama else f"Ollama chưa có {' / '.join(self.ch['tach_model'])}"
            ra.append({"ten": "Tách hành vi", "ok": False, "mo_ta": f"tắt, tình huống dài tìm như một truy vấn — {ly_do}"})
        if self.co_the_xep_lai:
            ra.append({"ten": "Xếp lại kết quả", "ok": True, "mo_ta": "có thể bật (chậm hơn, hơi chính xác hơn)"})
        else:
            ra.append({"ten": "Xếp lại kết quả", "ok": False, "mo_ta": "chưa cài (tuỳ chọn; xem README, Bước 4c)"})
        return ra

    # ------------------------------------------------------------------ kho luật

    def danh_sach_van_ban(self) -> list[sqlite3.Row]:
        """Các bộ luật chính trong kho, theo thứ tự bắt đầu hiệu lực (vd BLHS 1999 rồi BLHS 2015); cùng tên viết tắt là các bộ nối tiếp nhau."""
        with self._khoa:
            return lk.van_ban_goc(self.luat)

    def nam_van_ban(self) -> frozenset[int]:
        """Năm thông qua của các bộ luật đã biết (đã nạp hoặc chưa) để nhận ra «Điều 173 năm 2015» là năm của văn bản chứ không phải một ngày cần xem."""
        nam = {int(r["ngay_ban_hanh"][:4]) for r in self.danh_sach_van_ban() if r["ngay_ban_hanh"]}
        nam |= {int(e["nam_ban_hanh"]) for e in self.ch["luat_chua_nap"] if e.get("nam_ban_hanh")}
        return frozenset(nam)

    def viet_tat_mac_dinh(self) -> str | None:
        ds = self.danh_sach_van_ban()
        return ds[-1]["ten_viet_tat"] if ds else None

    def luat_chua_nap(self) -> list[dict]:
        """Bộ luật đã biết có tồn tại nhưng kho chưa nạp (cấu hình agent.luat_chua_nap); bỏ những bộ kho đã có (cùng số hiệu)."""
        co = {r["so_hieu"] for r in self.danh_sach_van_ban()}
        return [dict(e) for e in self.ch["luat_chua_nap"] if not e.get("so_hieu") or e["so_hieu"] not in co]

    def ten_ngan(self, vb) -> str:
        """'BLHS 2015' khi có nhiều bộ luật cùng tên viết tắt (đã nạp hoặc đã biết), 'BLHS' khi chỉ có một."""
        vt = vb["ten_viet_tat"] or vb["ten_day_du"]
        up = (vb["ten_viet_tat"] or "").upper()
        n = sum(1 for r in self.danh_sach_van_ban() if (r["ten_viet_tat"] or "").upper() == up)
        n += sum(1 for e in self.luat_chua_nap() if e["viet_tat"].upper() == up)
        nam = (vb["ngay_ban_hanh"] or "")[:4]
        return f"{vt} {nam}" if n > 1 and nam else vt

    def van_ban_hien_hanh(self) -> sqlite3.Row | None:
        """Bộ luật đang áp dụng hôm nay; nếu kho chỉ có bộ luật đã hết hiệu lực thì bộ nạp sau cùng."""
        with self._khoa:
            ds = self.danh_sach_van_ban()
            r = lk.van_ban_hieu_luc_tai(self.luat, date.today().isoformat(), self.viet_tat_mac_dinh()) if ds else None
            return r or (ds[-1] if ds else None)

    def _mo_ta_kho(self, vt: str | None) -> str:
        ds = [r for r in self.danh_sach_van_ban() if (r["ten_viet_tat"] or "").upper() == (vt or "").upper()]
        return "; ".join(f"{self.ten_ngan(r)} (hiệu lực từ {fmt_date(r['ngay_hieu_luc'])}"
                         + (f" đến hết {fmt_date(lk.ngay_cuoi_hieu_luc(r))}" if r["ngay_het_hieu_luc"] else "") + ")" for r in ds) or "chưa có bộ luật nào"

    def van_ban_tai_ngay(self, ngay: str, viet_tat: str | None = None) -> LuatTaiNgay:
        """Bộ luật đang áp dụng vào `ngay` theo thời gian hiệu lực của từng bộ luật (BLHS 2015 chỉ từ 01/01/2018). Không có thì `ly_do` giải thích:
        ngày đó thuộc bộ luật nào mà kho chưa nạp, hoặc sớm hơn mọi bộ luật đã biết."""
        with self._khoa:
            vt = viet_tat or self.viet_tat_mac_dinh()
            vb = lk.van_ban_hieu_luc_tai(self.luat, ngay, vt)
            if vb is not None:
                return LuatTaiNgay(ngay, vb)
            ky = next((e for e in self.luat_chua_nap() if e["viet_tat"].upper() == (vt or "").upper() and e["tu"] <= ngay < e["den"]), None)
            kho = self._mo_ta_kho(vt)
            if ky is not None:
                het = fmt_date((date.fromisoformat(ky["den"]) - timedelta(days=1)).isoformat())
                ly = (f"Ngày {fmt_date(ngay)} thuộc thời kỳ áp dụng {ky['ten']} (hiệu lực từ {fmt_date(ky['tu'])} đến hết {het}). "
                      f"Lexo chưa nạp bộ luật này nên chưa tra được vào ngày đó. Kho hiện có: {kho}.")
            else:
                ly = f"Không có bộ luật nào trong kho có hiệu lực vào ngày {fmt_date(ngay)}. Kho hiện có: {kho}."
            return LuatTaiNgay(ngay, None, ly, ky)

    def mo_ta_ngoai_cua_so(self, vb, ngay: str) -> str:
        """Rỗng nếu `ngay` nằm trong thời gian hiệu lực của bộ luật `vb`; ngược lại là câu giải thích, kèm bộ luật đang áp dụng vào ngày đó."""
        ten = self.ten_ngan(vb)
        tu, het = vb["ngay_hieu_luc"], vb["ngay_het_hieu_luc"]
        if tu and ngay < tu:
            ly = f"{ten} chỉ có hiệu lực từ {fmt_date(tu)}, nên chưa có hiệu lực vào ngày {fmt_date(ngay)}."
        elif het and ngay >= het:
            ly = f"{ten} đã hết hiệu lực từ {fmt_date(het)}; ngày {fmt_date(ngay)} không còn thuộc bộ luật này."
        else:
            return ""
        r = self.van_ban_tai_ngay(ngay, vb["ten_viet_tat"])
        if r.vb is None:
            return f"{ly} {r.ly_do}"
        if r.vb["id"] != vb["id"]:
            ly += f" Vào ngày đó bộ luật đang áp dụng là {self.ten_ngan(r.vb)} (số {r.vb['so_hieu']})."
        return ly

    def van_ban(self, viet_tat: str | None = None, nam: int | None = None) -> tuple[sqlite3.Row | None, str | None]:
        """(văn bản, lỗi). Không nêu gì → bộ luật đang áp dụng hôm nay. Nêu tên (và năm) → đúng bộ luật đó, kể cả đã hết hiệu lực;
        nêu bộ luật đã biết nhưng chưa nạp («BLHS 1999», «BLHS 2009») → lỗi nói rõ là chưa nạp."""
        with self._khoa:
            ds = self.danh_sach_van_ban()
            if not ds:
                return None, "Kho chưa có văn bản nào có tên viết tắt."
            if viet_tat is None and nam is None:
                return self.van_ban_hien_hanh(), None
            vt = viet_tat or self.viet_tat_mac_dinh()
            if nam is not None:
                khai = next((e for e in self.ch["luat_chua_nap"] if e["viet_tat"].upper() == vt.upper() and nam in (e.get("nam") or ())), None)
                if khai is not None:
                    co = [r for r in ds if khai.get("so_hieu") and r["so_hieu"] == khai["so_hieu"]]
                    if co:
                        return co[0], None
                    return None, f"Kho chưa nạp {khai['ten']}. Hiện có: {self._mo_ta_kho(vt)}."
            kq = lk.find_van_ban(self.luat, vt, nam)
            if not kq:
                return None, f"Kho không có văn bản «{vt}»" + (f" năm {nam}" if nam else "") + f". Hiện có: {self._mo_ta_kho(self.viet_tat_mac_dinh())}."
            if len(kq) > 1:
                if nam is None:          # nhiều bộ luật nối tiếp cùng tên viết tắt (BLHS 1999, BLHS 2015) mà không nêu năm: bộ đang áp dụng hôm nay
                    return lk.van_ban_hieu_luc_tai(self.luat, date.today().isoformat(), vt) or kq[-1], None
                return None, "Nhiều văn bản trùng tên viết tắt, hãy thêm năm: " + ", ".join(r["so_hieu"] for r in kq)
            return kq[0], None

    def nguon_doi_hieu_luc(self, van_ban_id: int) -> list[dict]:
        """Văn bản đã dời ngày bắt đầu hiệu lực của bộ luật (lệnh hoan_hieu_luc đã duyệt), vd Nghị quyết 41/2017/QH14."""
        with self._khoa:
            return [dict(r) for r in self.luat.execute(
                """SELECT DISTINCT s.so_hieu, s.ten_day_du, l.ngay_hieu_luc_moi, l.vi_tri_nguon, l.hieu_luc_tu FROM lenh_sua_doi l
                   JOIN van_ban s ON s.id = l.van_ban_nguon_id WHERE l.van_ban_dich_id = ? AND l.loai_thao_tac = 'hoan_hieu_luc'
                   AND l.trang_thai_duyet IN ('da_duyet', 'da_sua') ORDER BY l.hieu_luc_tu, s.so_hieu""", (van_ban_id,))]

    def thong_tin_kho(self) -> dict:
        """Kho gồm gì, nạp lúc nào (để hiển thị trên giao diện: kho chỉ đầy đủ đến mức đã nạp). `ten`, `so_dieu`, `sua_doi` nói về bộ luật
        đang áp dụng hôm nay; `cac_bo_luat` liệt kê mọi bộ luật đã nạp với thời gian hiệu lực; `chua_nap` là các thời kỳ đã biết mà kho chưa có."""
        with self._khoa:
            ds = self.danh_sach_van_ban()
            hom_nay = date.today().isoformat()
            if not ds:
                return {"ten": "(trống)", "so_hieu": "", "so_dieu": 0, "sua_doi": [], "ngay_nap": None, "ngay_duyet": None,
                        "hieu_dinh_cho_duyet": 0, "lenh_cho_duyet": 0, "cac_bo_luat": [], "chua_nap": [], "hieu_luc_theo": []}
            v = self.van_ban_hien_hanh()
            n = self.luat.execute(
                """SELECT COUNT(*) FROM don_vi_luat dv JOIN phien_ban_noi_dung pb ON pb.don_vi_id = dv.id
                   WHERE dv.van_ban_id = ? AND dv.loai = 'dieu' AND pb.hieu_luc_tu <= ? AND (pb.hieu_luc_den IS NULL OR ? < pb.hieu_luc_den)""",
                (v["id"], hom_nay, hom_nay)).fetchone()[0]
            def luat_sua_doi(van_ban_id: int) -> list[dict]:
                return [dict(r) for r in self.luat.execute(
                    """SELECT DISTINCT s.so_hieu, s.ten_day_du, s.ngay_ban_hanh, s.ngay_hieu_luc FROM quan_he_van_ban q
                       JOIN van_ban s ON s.id = q.van_ban_a_id WHERE q.van_ban_b_id = ? AND q.loai_quan_he = 'sua_doi'
                       ORDER BY s.ngay_hieu_luc, s.so_hieu""", (van_ban_id,))]
            sd = luat_sua_doi(v["id"])
            nap = self.luat.execute("SELECT MAX(ngay_nap) FROM van_ban").fetchone()[0]
            duyet = self.luat.execute("SELECT MAX(ngay_duyet) FROM lenh_sua_doi WHERE trang_thai_duyet IN ('da_duyet', 'da_sua')").fetchone()[0]
            cac = [{"ten": self.ten_ngan(r), "so_hieu": r["so_hieu"], "ten_day_du": r["ten_day_du"], "hieu_luc_tu": r["ngay_hieu_luc"],
                    "hieu_luc_den": lk.ngay_cuoi_hieu_luc(r), "sua_doi": luat_sua_doi(r["id"])} for r in ds]
            chua = [{"ten": e["ten_ngan"], "ten_day_du": e["ten"], "tu": e["tu"],
                     "den": (date.fromisoformat(e["den"]) - timedelta(days=1)).isoformat()} for e in self.luat_chua_nap()
                    if e["viet_tat"].upper() == (v["ten_viet_tat"] or "").upper()]
            return {"ten": f"{v['ten_viet_tat']} ({v['so_hieu']})", "so_hieu": v["so_hieu"], "so_dieu": n, "sua_doi": sd,
                    "ngay_nap": (nap or "")[:10] or None, "ngay_duyet": (duyet or "")[:10] or None,
                    "hieu_dinh_cho_duyet": lk.so_hieu_dinh_cho_duyet(self.luat, v["id"]), "lenh_cho_duyet": lk.so_lenh_cho_duyet(self.luat, v["id"]),
                    "cac_bo_luat": cac, "chua_nap": chua, "hieu_luc_theo": self.nguon_doi_hieu_luc(v["id"])}

    def xem_dieu(self, van_ban_id: int, ky_hieu: str, ngay: str, nguyen_van: bool = False, goc: bool = False):
        """Điều tại `ngay`. goc=True: Điều NHƯ KHI QUỐC HỘI THÔNG QUA (bỏ qua mọi lệnh sửa đổi, kể cả luật sửa đổi có hiệu lực cùng ngày với bộ luật)."""
        with self._khoa:
            return lk.get_dieu(self.luat, van_ban_id, ky_hieu, ngay, nguyen_van, goc)

    def giai_thich_khong_co(self, van_ban_id: int, ky_hieu: str, ngay: str, goc: bool = False) -> str:
        with self._khoa:
            ly = lk.dieu_status(self.luat, van_ban_id, ky_hieu, ngay)
            return f"Điều {ky_hieu} không có trong bản gốc. {ly}" if goc else ly

    def lich_su(self, van_ban_id: int, ky_hieu: str):
        with self._khoa:
            return lk.lich_su_dieu(self.luat, van_ban_id, ky_hieu)

    def so_sanh(self, van_ban_id: int, ky_hieu: str, ngay_a: str, ngay_b: str, goc_a: bool = False) -> tuple[object, object]:
        """(Điều tại ngày a, Điều tại ngày b); mỗi phần có thể None. goc_a=True: bên a là bản gốc (như khi thông qua)."""
        with self._khoa:
            return lk.get_dieu(self.luat, van_ban_id, ky_hieu, ngay_a, goc=goc_a), lk.get_dieu(self.luat, van_ban_id, ky_hieu, ngay_b)

    def co_chi_muc_cho(self, van_ban_id: int) -> bool:
        """Chỉ mục tìm kiếm có đoạn nào của bộ luật này không (chỉ mục dựng cho bộ luật nào thì tìm được bộ luật đó)."""
        if self.chi_muc is None:
            return False
        with self._khoa:
            return self.chi_muc.execute("SELECT 1 FROM chunk WHERE van_ban_id = ? LIMIT 1", (van_ban_id,)).fetchone() is not None

    def canh_bao_kho(self, van_ban_id: int, co_ngay: bool) -> list[str]:
        """Những điều người dùng nên biết về độ đầy đủ của kho (lệnh sửa đổi chưa duyệt, ngày hiệu lực chưa đối chiếu…)."""
        with self._khoa:
            ra = []
            n = lk.so_lenh_cho_duyet(self.luat, van_ban_id)
            if n:
                ra.append(f"Còn {n} lệnh sửa đổi đã nạp nhưng CHƯA được duyệt nên chưa áp vào kết quả.")
            if co_ngay:
                ly = lk.luu_y_hieu_luc(self.luat, van_ban_id)
                if ly:
                    ly = ly.removeprefix("Lưu ý: ")
                    ra.append(ly[:1].upper() + ly[1:])
            return ra

    def hieu_dinh_cho_duyet(self, van_ban_id: int, ky_hieu: str) -> list[dict]:
        """Đề xuất hiệu đính kỹ thuật CHƯA duyệt thuộc Điều này (chưa áp vào chữ hiển thị)."""
        with self._khoa:
            return [dict(r) for r in lk.hieu_dinh_cho_duyet_dieu(self.luat, van_ban_id, ky_hieu)]

    def quan_he(self, van_ban_id: int) -> list[dict]:
        """Văn bản có quan hệ với văn bản này (sửa đổi, bổ sung, hoãn hiệu lực…), theo ngày hiệu lực."""
        with self._khoa:
            rows = self.luat.execute(
                """SELECT v.so_hieu, v.ten_day_du, v.loai, v.ngay_ban_hanh, v.ngay_hieu_luc, q.loai_quan_he, q.ghi_chu, 'tac_dong_len_vb' AS huong
                   FROM quan_he_van_ban q JOIN van_ban v ON v.id = q.van_ban_a_id WHERE q.van_ban_b_id = ?
                   UNION ALL
                   SELECT v.so_hieu, v.ten_day_du, v.loai, v.ngay_ban_hanh, v.ngay_hieu_luc, q.loai_quan_he, q.ghi_chu, 'vb_tac_dong_len' AS huong
                   FROM quan_he_van_ban q JOIN van_ban v ON v.id = q.van_ban_b_id WHERE q.van_ban_a_id = ?
                   ORDER BY 5, 1""", (van_ban_id, van_ban_id)).fetchall()
            return [dict(r) for r in rows]

    def chuyen_tiep(self, van_ban_id: int) -> list[dict]:
        with self._khoa:
            return [dict(r) for r in lk.dieu_khoan_lien_quan(self.luat, van_ban_id)]

    # ------------------------------------------------------------------ tìm theo mô tả

    def _lay_xep_lai(self, thong_bao: list[str], ky_thuat: list[str]):
        if self._xep_lai is None and self._loi_xep_lai is None:
            try:
                self._xep_lai = BgeReranker(ROOT / self.ch["mo_hinh_xep_lai"])
            except XepLaiError as e:
                self._loi_xep_lai = str(e)
        if self._xep_lai is None:
            thong_bao.append("Chưa dùng được bước xếp lại nên giữ nguyên thứ tự tìm kiếm.")
            ky_thuat.append(self._loi_xep_lai or "")
        return self._xep_lai

    def _chu_dieu(self) -> dict[str, str]:
        if self._van_ban_dieu is None:
            self._van_ban_dieu = {d: v["van_ban"] for d, v in gom_dieu(self.chi_muc).items()}
        return self._van_ban_dieu

    def tim_dieu(self, cau: str, ngay: str | None = None, k: int = 5, xep_lai: bool | None = None) -> tuple[list[DieuKetQua], list[str], list[str]]:
        """Tìm k Điều khớp nhất với `cau` theo bản có hiệu lực tại `ngay`. Trả (kết quả, thông báo cho người dùng, chi tiết kỹ thuật)."""
        ngay = ngay or date.today().isoformat()
        thong_bao: list[str] = []
        ky_thuat: list[str] = []
        if self.chi_muc is None:
            return [], ["Chưa dựng chỉ mục tìm kiếm nên chưa tìm theo mô tả được (python scripts/build_index.py)."], []
        top = int(self.ch["xep_lai_top"])
        with self._khoa:
            che_do = "vector" if self.embedder is not None else "fts"
            if che_do == "fts":
                thong_bao.append("Đang tìm theo từ khoá (không phải theo nghĩa) vì chưa kết nối được mô hình ngôn ngữ; với cách nói đời thường kết quả thường lệch nhiều. Hãy bật Ollama (mô hình bge-m3) để tìm theo nghĩa.")
            kq = None
            if che_do == "vector":
                try:
                    kq = tim(self.chi_muc, cau, embedder=self.embedder, ngay=ngay, k=2000, che_do="vector", n_ung_vien=300)
                    if not kq.hits:
                        raise EmbedError("không có vector nào cho mô hình này trong chỉ mục")
                except (EmbedError, ValueError) as e:
                    thong_bao.append("Không tìm theo nghĩa được nên chuyển sang tìm theo từ khoá; kết quả kém chính xác hơn.")
                    ky_thuat.append(str(e))
                    che_do, kq = "fts", None
            if kq is None:
                kq = tim(self.chi_muc, cau, embedder=self.embedder, ngay=ngay, k=2000, che_do="fts", n_ung_vien=300)
            ky_thuat += kq.canh_bao
            ds = gop_theo_dieu(kq.hits, max(k, top))
            dung_xl = self.xep_lai_mac_dinh if xep_lai is None else xep_lai
            if dung_xl and ds and che_do == "vector":
                may = self._lay_xep_lai(thong_bao, ky_thuat)
                if may is not None:
                    n = min(top, len(ds))
                    try:
                        chu = self._chu_dieu()
                        diem = may.cham(cau, [chu.get(d.dieu) or d.tot_nhat.text for d in ds[:n]])
                        thu_tu = xep_lai_top([{"dieu": d.dieu, "vec": float(d.tot_nhat.cosine or 0.0)} for d in ds], diem, float(self.ch["xep_lai_w"]), n)
                        theo = {d.dieu: d for d in ds}
                        ds = [theo[x] for x in thu_tu]
                    except (XepLaiError, RuntimeError, OSError, ValueError) as e:
                        thong_bao.append("Bước xếp lại gặp lỗi nên bị bỏ qua; giữ nguyên thứ tự tìm kiếm.")
                        ky_thuat.append(repr(e))
            ra = []
            for i, d in enumerate(ds[:k], 1):
                h = d.doan_noi_dung or d.tot_nhat
                ra.append(DieuKetQua(so_dieu(d.dieu), d.dieu, d.tieu_de, cat(h.noi_dung) if h.noi_dung else "", nhan_vi_tri(h.key) if h.noi_dung else "",
                                     i, d.tot_nhat.cosine))
            return ra, thong_bao, ky_thuat

    # ------------------------------------------------------------------ tách hành vi

    def tach(self, tinh_huong: str) -> tuple[list[str], list[str], list[str]]:
        """Tách tình huống thành các hành vi. Trả (hành vi, thông báo, chi tiết kỹ thuật). Không tách được → [cả tình huống] kèm thông báo."""
        if self.tach_llm is None:
            return [tinh_huong], ["Chưa kết nối được mô hình tách hành vi nên mình tìm theo cả tình huống như một câu hỏi; "
                                  "tình huống có nhiều việc thì có thể sót Điều."], []
        with self._khoa:
            try:
                r = tach_mot(self.tach_llm, tinh_huong, "thuan", (), False)
            except LLMError as e:
                return [tinh_huong], ["Không gọi được mô hình tách hành vi nên mình tìm theo cả tình huống như một câu hỏi."], [str(e)]
        if r["loi"]:
            return [tinh_huong], ["Mô hình tách hành vi trả lời không đúng định dạng nên mình tìm theo cả tình huống như một câu hỏi."], [r["loi"]]
        return r["hanh_vi"], [], []


def _kiem_tra_chi_muc_cu(luat: sqlite3.Connection, idx: sqlite3.Connection) -> list[str]:
    """Chỉ mục có còn khớp kho luật không (cùng kiểm tra của scripts/tim_kiem.py), theo đúng các bộ luật đã được dựng vào chỉ mục;
    và bộ luật nào của kho chưa có trong chỉ mục."""
    ra: list[str] = []
    try:
        ids = [r[0] for r in idx.execute("SELECT DISTINCT van_ban_id FROM chunk ORDER BY van_ban_id")]
        if ids:
            chunks = [c for i in ids for c in build_chunks(luat, i)]
            if van_tay(chunks) != van_tay_da_luu(idx):
                ra.append("Kho luật đã đổi so với lúc dựng chỉ mục tìm kiếm; kết quả tìm theo mô tả có thể chưa phản ánh bản mới nhất. "
                          "Chạy: python scripts/build_index.py")
        for r in lk.van_ban_goc(luat):
            if r["id"] not in ids and ids:
                ra.append(f"Chỉ mục tìm kiếm chưa có {r['ten_viet_tat']} số {r['so_hieu']}, nên tìm theo mô tả vào thời kỳ của bộ luật này chưa dùng được. "
                          "Chạy: python scripts/build_index.py --tat-ca")
    except sqlite3.Error:
        pass
    return ra
