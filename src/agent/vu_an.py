"""Chức năng 2: từ nội dung một vụ án, soạn BẢN TÓM TẮT KIỂU CÁO TRẠNG để tham khảo: ai, làm gì, có dấu hiệu phạm tội gì (Điều/khoản), vì sao.

Đường ống (bước nào thiếu thành phần thì hạ cấp CÓ thông báo, không im lặng):
  1. tìm Điều ứng viên: truy hồi trên cả sự việc và từng hành vi (nếu tách được), chỉ giữ Điều thuộc phần các tội phạm của BLHS;
  2. chọn Điều: mô hình chọn Điều đã tinh chỉnh (kế hoạch Kaggle V3) nếu Ollama có; không có thì giữ thứ hạng truy hồi;
  3. soạn: Qwen3 đọc sự việc + NGUYÊN VĂN các Điều đã chọn (lấy từ kho, mô hình không tự viết luật), trả JSON theo từng người;
  4. kiểm: Điều phải nằm trong danh sách đã đưa, khoản phải có thật, mỗi trích dẫn phải có nguyên văn trong sự việc; sai thì đánh dấu.
Không có mô hình soạn thì chỉ trả Điều gợi ý (che_do = 'chi_dieu'). Chỉ để tham khảo, KHÔNG phải kết luận của cơ quan tiến hành tố tụng.
Giao diện: src/ui/app_vu_an.py. Giao diện chỉ hiển thị KetQuaVuAn, không có logic nghiệp vụ.
"""
from __future__ import annotations

import json
import re
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from typing import Callable

from src.agent.agent import Agent, DieuDayDu
from src.agent.cong_cu import DieuKetQua, co_model, kiem_tra_ollama
from src.agent.trinh_bay import md_thoat
from src.ban_an import chon_dieu as cd
from src.config import load_config
from src.index.cau_hoi import LLMError, OllamaLLM, la_model_nghi

MAC_DINH_VU_AN = {
    "chon_model": ["qwen3-8b-lexo-chon-dieu-cbba-v1"],     # mô hình chọn Điều đã tinh chỉnh (tên trong Ollama sau khi gộp GGUF); chưa có thì bỏ qua bước chọn
    "soan_model": [],                              # rỗng = lấy llm_local.extract_model (qwen3:8b); cái đầu tiên Ollama đang có
    "so_ung_vien": 12,                             # số Điều ứng viên đưa cho bước chọn (K của kế hoạch V3 nằm trong 3–30)
    "so_dieu_soan": 6,                             # số Điều tối đa đưa vào bản soạn (6 = số Điều tối đa mô hình chọn Điều được phép chọn)
    "so_ky_tu_moi_dieu": 3500,                     # cắt nguyên văn mỗi Điều trong lời nhắc (người đọc vẫn xem được cả Điều)
    "tu_dau_soan": 2000, "tu_cuoi_soan": 500,      # sự việc dài hơn thì lược phần giữa khi soạn
    "num_ctx": 16384, "num_predict": 3000,
    "thoi_gian_chon": 180, "thoi_gian_soan": 600,
    "toi_da_nguoi": 10,
}

MIEN_TRU_VU_AN = ("Bản dự thảo này do máy soạn từ nội dung bạn nhập, chỉ để tham khảo. Đây không phải cáo trạng, không phải kết luận của cơ quan tiến hành "
                  "tố tụng và không phải tư vấn pháp lý. Máy chưa xét chứng cứ, tuổi và năng lực chịu trách nhiệm hình sự, tình tiết tăng nặng/giảm nhẹ, "
                  "mức hình phạt. Luôn đối chiếu nguyên văn Điều luật và sự việc gốc.")

HE_THONG_SOAN = (
    "Bạn là trợ lý soạn bản TÓM TẮT KIỂU CÁO TRẠNG của Việt Nam để người học luật tham khảo. Bạn nhận một sự việc vụ án hình sự và nguyên văn "
    "các Điều của Bộ luật Hình sự có thể liên quan. Trả về đúng một JSON gồm:\n"
    "- tom_tat: 1 đến 3 câu tóm tắt vụ việc.\n"
    "- nguoi: mỗi người có hành vi vi phạm là một mục gồm: ten (đúng như trong sự việc); vai_tro (ví dụ: người thực hành, chủ mưu, giúp sức, "
    "xúi giục, người mua tài sản; để trống nếu sự việc không cho biết); hanh_vi (danh sách; mỗi mục có mo_ta ngắn và trich là đoạn chép "
    "NGUYÊN VĂN từ sự việc); toi (danh sách tội người đó có dấu hiệu phạm).\n"
    "- mỗi tội gồm: dieu (chỉ số Điều, PHẢI nằm trong danh sách Điều đã cho); khoan (số khoản nếu xác định được, không thì để trống); "
    "ly_do (vì sao: đối chiếu hành vi với từng dấu hiệu của Điều/khoản đó); trich (các đoạn chép NGUYÊN VĂN từ sự việc làm căn cứ).\n"
    "Quy tắc: chỉ dùng thông tin có trong sự việc, không bịa tên, số liệu hay tình tiết; đoạn trích phải chép đúng từng chữ; không nêu mức hình phạt; "
    "người không có hành vi vi phạm thì không đưa vào; nếu không Điều nào khớp thì để nguoi là danh sách rỗng."
)

_THINK = re.compile(r"<think>.*?</think>", re.S)


class SoanLoi(ValueError):
    """Mô hình soạn trả lời không dùng được."""


def cau_hinh_vu_an(cfg: dict | None = None) -> dict:
    ch = dict(MAC_DINH_VU_AN)
    ch.update((cfg or {}).get("vu_an") or {})
    for k in ("chon_model", "soan_model"):
        if isinstance(ch[k], str):
            ch[k] = [ch[k]]
    return ch


# ------------------------------------------------------------------------------------------------------------------ kết quả

@dataclass
class Trich:
    chu: str
    khop: bool                       # có nguyên văn trong sự việc không


@dataclass
class HanhViBiCao:
    mo_ta: str
    trich: Trich | None = None


@dataclass
class Toi:
    dieu: str                        # '173'
    ten_toi: str                     # 'Tội trộm cắp tài sản' (lấy từ tiêu đề Điều trong kho)
    khoan: str = ""                  # '' nếu không xác định được
    ly_do: str = ""
    can_cu: list[Trich] = field(default_factory=list)


@dataclass
class NguoiBiCao:
    ten: str
    vai_tro: str = ""
    ten_khop: bool = True            # tên có xuất hiện trong sự việc không
    hanh_vi: list[HanhViBiCao] = field(default_factory=list)
    toi: list[Toi] = field(default_factory=list)


@dataclass
class KetQuaVuAn:
    su_viec: str
    ngay: str | None
    che_do: str                                            # 'day_du' (đã soạn) | 'chi_dieu' (chỉ gợi ý Điều)
    tom_tat: str = ""
    nguoi: list[NguoiBiCao] = field(default_factory=list)
    dieu: list[DieuDayDu] = field(default_factory=list)    # Điều đã đưa vào bản soạn, nguyên văn
    ung_vien: list[DieuKetQua] = field(default_factory=list)
    da_chon: list[str] = field(default_factory=list)       # số Điều sau bước chọn
    thong_bao: list[str] = field(default_factory=list)
    ky_thuat: list[str] = field(default_factory=list)
    nghiem_trong: bool = False
    giay: float = 0.0
    mien_tru: str = MIEN_TRU_VU_AN

    @property
    def so_toi(self) -> int:
        return sum(len(n.toi) for n in self.nguoi)

    @property
    def so_trich_sai(self) -> int:
        return sum(not t.khop for n in self.nguoi for t in [*(h.trich for h in n.hanh_vi if h.trich), *(c for o in n.toi for c in o.can_cu)])

    def to_dict(self) -> dict:
        return asdict(self)


# ------------------------------------------------------------------------------------------------------------------ gọi mô hình

class LLMSchema(OllamaLLM):
    """Ollama /api/chat: gửi cả hội thoại, ép đầu ra theo `schema`, xác định (nhiệt độ 0). Qwen3 luôn tắt chế độ nghĩ.
    no_think_mem=False cho mô hình đã tinh chỉnh: lời nhắc lúc chạy phải giống lúc học (dữ liệu học không có «/no_think»)."""

    def __init__(self, model: str, endpoint: str, schema: dict, *, num_ctx: int, num_predict: int, no_think_mem: bool = True, **kw):
        super().__init__(model, endpoint, **kw)
        self.schema, self.num_ctx, self.num_predict, self.no_think_mem, self.seed = schema, num_ctx, num_predict, no_think_mem, 0

    def _body(self, messages):                                      # type: ignore[override]
        body = {"model": self.model, "stream": False, "format": self.schema, "keep_alive": "30m",
                "options": {"temperature": 0.0, "seed": self.seed, "num_ctx": self.num_ctx, "num_predict": self.num_predict}}
        tn = [dict(m) for m in messages]
        if la_model_nghi(self.model):
            body["think"] = False
            if self.no_think_mem:
                tn[-1]["content"] = tn[-1]["content"].rstrip() + "\n/no_think"
        body["messages"] = tn
        return body


class LLMGiaSoan:
    """LLM giả cho thử giao diện/kiểm thử: mỗi câu đầu của sự việc thành một «Người 1» với Điều đầu tiên trong danh sách. KHÔNG có nghĩa pháp lý."""
    name = "gia"
    schema: dict = {}

    def hoi(self, messages) -> str:
        nd = messages[-1]["content"]
        su_viec = nd.split("\n\nCác Điều có thể liên quan", 1)[0].removeprefix("Sự việc:\n").strip()
        cau = next((s.strip() for s in re.split(r"(?<=[.!?])\s+", su_viec) if s.strip()), su_viec)
        dieu = re.search(r"### Điều (\S+?)\.", nd)
        toi = [{"dieu": dieu.group(1), "khoan": "1", "ly_do": "(dữ liệu giả để thử giao diện) hành vi nêu trên khớp với Điều này.", "trich": [cau]}] if dieu else []
        return json.dumps({"tom_tat": cau, "nguoi": [{"ten": "Người 1", "vai_tro": "", "hanh_vi": [{"mo_ta": cau, "trich": cau}], "toi": toi}]}, ensure_ascii=False)


def schema_soan(dieu: list[str]) -> dict:
    s = {"type": "string"}
    return {"type": "object", "required": ["tom_tat", "nguoi"], "properties": {
        "tom_tat": s,
        "nguoi": {"type": "array", "maxItems": 10, "items": {"type": "object", "required": ["ten", "hanh_vi", "toi"], "properties": {
            "ten": s, "vai_tro": s,
            "hanh_vi": {"type": "array", "maxItems": 6, "items": {"type": "object", "required": ["mo_ta", "trich"], "properties": {"mo_ta": s, "trich": s}}},
            "toi": {"type": "array", "maxItems": 5, "items": {"type": "object", "required": ["dieu", "ly_do", "trich"], "properties": {
                "dieu": {"type": "string", "enum": list(dieu)}, "khoan": s, "ly_do": s, "trich": {"type": "array", "maxItems": 4, "items": s}}}}}}}}}


# ------------------------------------------------------------------------------------------------------------------ hàm thuần

def _chuan(s: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFC", s or "")).strip().casefold()


def trich_khop(trich: str, su_viec_chuan: str) -> bool:
    """Đoạn trích có nguyên văn trong sự việc (đã chuẩn hoá khoảng trắng, hoa/thường). «…» và «[…]» tách đoạn trích thành các mảnh, mỗi mảnh phải có mặt."""
    manh = [m.strip(" \"'“”‘’.,;:") for m in re.split(r"\[…\]|…|\.{3}", _chuan(trich))]
    manh = [m for m in manh if len(m) >= 4]
    return bool(manh) and all(m in su_viec_chuan for m in manh)


def ten_toi(tieu_de: str) -> str:
    """'Điều 173. Tội trộm cắp tài sản' → 'Tội trộm cắp tài sản'."""
    return re.sub(r"^Điều\s+\S+?\.\s*", "", tieu_de or "").strip()


def chu_sach(md: str) -> str:
    """Markdown của Điều (xem trinh_bay.markdown_dieu) → chữ thuần cho lời nhắc: bỏ ghi chú nguồn sửa đổi, bỏ ký tự thoát và dấu đậm."""
    md = re.sub(r"\s*:gray\[\*\(.*?\)\*\]", "", md, flags=re.S)
    md = md.replace("**", "")                                  # dấu đậm thật (ký tự «*» của luật đã được thoát thành «\\*», không dính vào đây)
    return re.sub(r"\\([\\$*_`<>\[\]|#+\-])", r"\1", md)


def _co_khoan(md: str, khoan: str) -> bool:
    return bool(re.search(rf"(?m)^\*\*{re.escape(khoan)}\.\*\*", md))


def _json(chu: str) -> dict:
    chu = re.sub(r"^```(?:json)?\s*|\s*```$", "", _THINK.sub("", chu or "").strip()).strip()
    for cand in (chu, chu[chu.find("{"): chu.rfind("}") + 1] if "{" in chu else ""):
        try:
            obj = json.loads(cand)
        except ValueError:
            continue
        if isinstance(obj, dict):
            return obj
    raise SoanLoi(f"không đọc được JSON: {chu[:160]!r}")


def _so_dieu(x) -> str:
    return re.sub(r"(?i)^\s*điều\s*", "", str(x or "")).strip().lower()


def _s(x) -> str:
    return str(x).strip() if isinstance(x, (str, int, float)) else ""


def doc_soan(chu: str, dieu_dd: dict[str, DieuDayDu], su_viec: str, toi_da_nguoi: int = 10) -> tuple[str, list[NguoiBiCao], list[str]]:
    """Đọc JSON của mô hình soạn và KIỂM: trả (tóm tắt, những người, lưu ý kỹ thuật). Bỏ tội có Điều ngoài danh sách đã đưa; bỏ khoản không có thật;
    đánh dấu trích dẫn không có nguyên văn trong sự việc. Người không còn tội nào thì bỏ."""
    obj = _json(chu)
    goc, luu_y, nguoi = _chuan(su_viec), [], []
    if not isinstance(obj.get("nguoi"), list):
        raise SoanLoi("thiếu danh sách «nguoi»")

    def trich(t) -> Trich | None:
        t = _s(t)
        return Trich(t, trich_khop(t, goc)) if t else None

    for p in obj["nguoi"][:toi_da_nguoi]:
        if not isinstance(p, dict) or not _s(p.get("ten")):
            continue
        ten = _s(p["ten"])
        nb = NguoiBiCao(ten, _s(p.get("vai_tro")), _chuan(ten) in goc)
        for h in p.get("hanh_vi") or []:
            h = h if isinstance(h, dict) else {"mo_ta": h}
            if _s(h.get("mo_ta")):
                nb.hanh_vi.append(HanhViBiCao(_s(h["mo_ta"]), trich(h.get("trich"))))
        for o in p.get("toi") or []:
            if not isinstance(o, dict):
                continue
            so = _so_dieu(o.get("dieu"))
            if so not in dieu_dd:
                luu_y.append(f"Bỏ một tội của {ten}: Điều {so or '?'} không nằm trong danh sách Điều đã đưa cho mô hình.")
                continue
            khoan = _s(o.get("khoan")).lower().removeprefix("khoản").strip()
            if khoan and not _co_khoan(dieu_dd[so].markdown_ca_dieu or dieu_dd[so].markdown, khoan):
                luu_y.append(f"Bỏ số khoản «{khoan}» của {ten} (Điều {so}): Điều này không có khoản đó tại ngày đã chọn.")
                khoan = ""
            tr = o.get("trich")
            ds = [trich(x) for x in (tr if isinstance(tr, list) else [tr])]
            nb.toi.append(Toi(so, ten_toi(dieu_dd[so].tieu_de), khoan, _s(o.get("ly_do")), [t for t in ds if t]))
        if nb.toi:
            nguoi.append(nb)
        else:
            luu_y.append(f"Bỏ {ten}: mô hình không nêu được tội hợp lệ nào cho người này.")
    return _s(obj.get("tom_tat")), nguoi, luu_y


def thanh_cao_trang(kq: KetQuaVuAn, *, md: bool = False) -> str:
    """Bản văn xuôi kiểu cáo trạng dựng bằng CODE từ các trường đã kiểm (không do mô hình viết lại). md=True: đánh dấu Markdown, thoát ký tự lạ."""
    e = md_thoat if md else (lambda s: s)
    b = (lambda s: f"**{md_thoat(s)}**") if md else (lambda s: s)
    vb = {d.so: d.van_ban.split(" (")[0] for d in kq.dieu}
    ra = ["BẢN TÓM TẮT KIỂU CÁO TRẠNG (THAM KHẢO, DO MÁY SOẠN)" if not md else "### Bản tóm tắt kiểu cáo trạng (tham khảo, do máy soạn)", ""]
    if kq.tom_tat:
        ra += [f"{b('Tóm tắt vụ việc.')} {e(kq.tom_tat)}", ""]
    for i, n in enumerate(kq.nguoi, 1):
        ra.append(f"{i}. {b(n.ten)}" + (f" ({e(n.vai_tro)})" if n.vai_tro else ""))
        if n.hanh_vi:
            ra.append("   Hành vi: " + "; ".join(e(h.mo_ta.rstrip('.;')) for h in n.hanh_vi) + ".")
        for o in n.toi:
            vi_tri = (f"khoản {o.khoan} " if o.khoan else "") + f"Điều {o.dieu} {vb.get(o.dieu, 'Bộ luật Hình sự')}"
            ra.append(f"   Hành vi nêu trên có dấu hiệu của {b('«' + o.ten_toi + '»')}, quy định tại {e(vi_tri)}.")
            if o.ly_do:
                ra.append(f"   Vì: {e(o.ly_do)}")
        ra.append("")
    if not kq.nguoi:
        ra += ["(Chưa soạn được nội dung theo từng người.)", ""]
    if not md:                                               # bản Markdown hiển thị trong trang đã có lời nhắc ở chân trang; bản tải về thì phải mang theo
        ra.append(kq.mien_tru)
    return "\n".join(l + "  " if md and l.strip() and not l.startswith("###") else l for l in ra)         # md: hai dấu cách cuối dòng = xuống dòng cứng


# ------------------------------------------------------------------------------------------------------------------ đường ống

class PhanTichVuAn:
    def __init__(self, agent: Agent, *, chon_llm=None, soan_llm=None, chon_ten: str | None = None, soan_ten: str | None = None,
                 cau_hinh: dict | None = None, loc_toi_pham: Callable[[str], bool] | None = None):
        self.ag, self.cc = agent, agent.cc
        self.ch = cau_hinh_vu_an({"vu_an": cau_hinh} if cau_hinh else None)
        self.chon_llm, self.soan_llm, self.chon_ten, self.soan_ten = chon_llm, soan_llm, chon_ten, soan_ten
        self._tiem = {"chon": chon_llm is not None, "soan": soan_llm is not None}              # đã truyền vào (giả/thử): làm_mới không ghi đè
        self._loc = loc_toi_pham
        self._ollama: tuple[bool, list[str]] = (False, [])

    @classmethod
    def mo(cls, agent: Agent, *, gia: bool = False) -> PhanTichVuAn:
        cfg = load_config()
        ch = cfg.get("vu_an") or {}
        if not ch.get("soan_model"):
            ch = {**ch, "soan_model": [(cfg.get("llm_local") or {}).get("extract_model") or "qwen3:8b"]}
        pv = cls(agent, cau_hinh=ch, soan_llm=LLMGiaSoan() if gia else None, soan_ten="gia" if gia else None)
        if not gia:
            pv.lam_moi()
        return pv

    def lam_moi(self) -> None:
        """Hỏi lại Ollama đang có mô hình nào (bấm «Kiểm tra lại» sau khi bật Ollama). Không đụng tới thành phần được truyền sẵn."""
        ok, models = kiem_tra_ollama(self.cc.endpoint, float(self.cc.ch["thoi_gian_cho_ollama"]))
        self._ollama = (ok, models)
        ch = self.ch

        def tim(khoa: str, schema: dict, **kw):
            if self._tiem[khoa]:
                return
            setattr(self, f"{khoa}_llm", None)
            setattr(self, f"{khoa}_ten", None)
            for ten in ch[f"{khoa}_model"]:
                if ok and co_model(ten, models):
                    setattr(self, f"{khoa}_ten", ten)
                    setattr(self, f"{khoa}_llm", LLMSchema(ten, self.cc.endpoint, schema, retries=1, **kw))
                    return

        tim("chon", {}, num_ctx=6144, num_predict=160, no_think_mem=False, timeout=int(ch["thoi_gian_chon"]))
        tim("soan", {}, num_ctx=int(ch["num_ctx"]), num_predict=int(ch["num_predict"]), timeout=int(ch["thoi_gian_soan"]))

    def trang_thai(self) -> list[dict]:
        ok = self._ollama[0] or self.soan_ten == "gia"
        return [
            {"ten": "Tìm Điều ứng viên", "ok": self.cc.chi_muc is not None,
             "mo_ta": ("tìm theo nghĩa (bge-m3)" if self.cc.co_vector else "chỉ tìm theo từ khoá") if self.cc.chi_muc is not None else "chưa dựng chỉ mục (scripts/build_index.py)"},
            {"ten": "Chọn Điều", "ok": self.chon_llm is not None,
             "mo_ta": f"mô hình {self.chon_ten}" if self.chon_llm else "chưa có mô hình chọn Điều đã tinh chỉnh; dùng thứ hạng tìm kiếm"},
            {"ten": "Soạn bản cáo buộc", "ok": self.soan_llm is not None,
             "mo_ta": f"mô hình {self.soan_ten}" if self.soan_llm else ("chưa có mô hình soạn: " + ("Ollama chưa có " + ", ".join(self.ch["soan_model"]) if ok else "chưa kết nối được Ollama") + "; chỉ gợi ý được Điều")},
        ]

    # ------------------------------------------------------------------ các bước

    def _la_toi(self, so: str) -> bool:
        return (self._loc or cd.la_dieu_toi_pham)(so)

    def _ung_vien(self, chu: str, ngay: str | None, kq: KetQuaVuAn) -> list[DieuKetQua]:
        """Truy hồi trên cả sự việc và từng hành vi, gộp bằng RRF (Điều xuất hiện ở nhiều danh sách thì lên cao), giữ Điều thuộc phần các tội phạm."""
        n = int(self.ch["so_ung_vien"])
        ds, tb, kt = self.cc.tim_dieu(chu, ngay, k=n)
        kq.thong_bao += tb
        kq.ky_thuat += kt
        theo_so = {d.so: d for d in ds}
        danh_sach = [[d.so for d in ds]]
        if self.cc.co_tach:
            hv, tb, kt = self.cc.tach(chu)
            kq.thong_bao += tb
            kq.ky_thuat += kt
            for h in hv[:cd.TOI_DA_CHON + 2] if len(hv) > 1 else []:
                dh, tb, kt = self.cc.tim_dieu(h, ngay, k=3)
                kq.ky_thuat += kt
                danh_sach.append([d.so for d in dh])
                for d in dh:
                    theo_so.setdefault(d.so, d)
        gop = [s for s in cd.gop_rrf(danh_sach) if self._la_toi(s)][:n]
        return [DieuKetQua(d.so, d.khoa, d.tieu_de, d.trich, d.vi_tri, i, d.cosine) for i, d in enumerate((theo_so[s] for s in gop), 1)]

    def _chon(self, su_viec_cat: str, uv: list[DieuKetQua], kq: KetQuaVuAn) -> list[str]:
        so = [d.so for d in uv]
        if self.chon_llm is None or len(so) < 2:
            return so
        self.chon_llm.schema = cd.schema_chon(so)
        try:
            return cd.doc_chon(self.chon_llm.hoi(cd.dung_tin_nhan(su_viec_cat, so, {d.so: d.tieu_de for d in uv})), so)
        except (LLMError, cd.ChonError) as e:
            kq.thong_bao.append("Mô hình chọn Điều gặp lỗi nên mình dùng thứ hạng của bước tìm kiếm.")
            kq.ky_thuat.append(f"chọn Điều: {e}")
            return so

    def _soan(self, su_viec: str, dieu_dd: dict[str, DieuDayDu], kq: KetQuaVuAn) -> None:
        cat, da_cat = cd.cat_su_viec(su_viec, int(self.ch["tu_dau_soan"]), int(self.ch["tu_cuoi_soan"]))
        if da_cat:
            kq.thong_bao.append("Sự việc dài nên khi soạn mình lược phần giữa; các Điều và trích dẫn có thể thiếu so với phần đã lược.")
        cat_dieu = int(self.ch["so_ky_tu_moi_dieu"])
        khoi = []
        for so, dd in dieu_dd.items():
            chu = chu_sach(dd.markdown_ca_dieu or dd.markdown)
            khoi.append(f"### {dd.tieu_de}\n{chu[:cat_dieu]}" + (" […]" if len(chu) > cat_dieu else ""))
        nd = f"Sự việc:\n{cat}\n\nCác Điều có thể liên quan (nguyên văn):\n\n" + "\n\n".join(khoi)
        self.soan_llm.schema = schema_soan(list(dieu_dd))
        loi = False
        try:
            tho = self.soan_llm.hoi([{"role": "system", "content": HE_THONG_SOAN}, {"role": "user", "content": nd}])
            kq.tom_tat, kq.nguoi, luu_y = doc_soan(tho, dieu_dd, su_viec, int(self.ch["toi_da_nguoi"]))
            kq.ky_thuat += luu_y
        except LLMError as e:
            loi = True
            kq.thong_bao.append("Không gọi được mô hình soạn nên mình chỉ gợi ý các Điều liên quan.")
            kq.ky_thuat.append(f"soạn: {e}")
        except SoanLoi as e:
            loi = True
            kq.thong_bao.append("Mô hình soạn trả lời không đúng định dạng nên mình chỉ gợi ý các Điều liên quan. Thử lại, hoặc chia vụ án ngắn hơn.")
            kq.ky_thuat.append(f"soạn: {e}")
        if kq.nguoi:
            kq.che_do = "day_du"
            if kq.so_trich_sai:
                kq.thong_bao.append(f"Có {kq.so_trich_sai} đoạn trích dẫn mô hình đưa ra KHÔNG có nguyên văn trong sự việc (đánh dấu ⚠). Đừng tin các đoạn đó khi chưa đối chiếu.")
                kq.nghiem_trong = True
            if any(not n.ten_khop for n in kq.nguoi):
                kq.thong_bao.append("Có tên người không xuất hiện trong sự việc (đánh dấu ⚠); kiểm tra lại.")
        elif not loi:
            kq.thong_bao.append("Mô hình soạn không nêu được người nào có dấu hiệu phạm tội trong các Điều đã chọn; xem danh sách Điều gợi ý.")

    def phan_tich(self, su_viec: str, *, ngay: str | None = None, so_dieu: int | None = None,
                  bao: Callable[[str], None] = lambda s: None) -> KetQuaVuAn:
        """`ngay`: ngày xảy ra hành vi (ISO) để lấy đúng bản luật; None = hôm nay. `so_dieu`: số Điều tối đa đưa vào bản soạn. `bao`: báo tiến độ."""
        t0 = time.time()
        su_viec = (su_viec or "").strip()
        kq = KetQuaVuAn(su_viec, ngay, "chi_dieu")
        if len(su_viec.split()) < 15:
            kq.thong_bao.append("Nội dung quá ngắn để phân tích: hãy nhập diễn biến vụ án (ai làm gì, khi nào, thiệt hại ra sao), từ vài câu trở lên.")
            kq.nghiem_trong = True
            return kq
        cat, _ = cd.cat_su_viec(su_viec)
        bao("Tìm các Điều có thể liên quan…")
        kq.ung_vien = self._ung_vien(cat, ngay, kq)
        if not kq.ung_vien:
            kq.thong_bao.append("Không tìm thấy Điều nào về tội phạm khớp với nội dung này.")
            kq.nghiem_trong = True
            return kq
        bao("Chọn Điều…" if self.chon_llm else "Lấy các Điều xếp hạng cao nhất…")
        kq.da_chon = self._chon(cat, kq.ung_vien, kq)[:max(1, int(so_dieu or self.ch["so_dieu_soan"]))]
        dieu_dd = {}
        for so in kq.da_chon:
            dd = self.ag.lay_dieu(so, ngay)
            if dd is not None:
                dieu_dd[so] = dd
        kq.dieu = list(dieu_dd.values())
        if not dieu_dd:
            kq.thong_bao.append("Các Điều tìm được không có hiệu lực tại ngày đã chọn.")
        elif self.soan_llm is None:
            kq.thong_bao.append("Chưa có mô hình soạn (cần Ollama và mô hình " + " hoặc ".join(self.ch["soan_model"]) + ") nên mình chỉ gợi ý các Điều liên quan. "
                                "Bật Ollama rồi bấm «Kiểm tra lại kết nối» ở thanh bên.")
        else:
            bao("Soạn bản cáo buộc theo từng người (có thể mất vài chục giây)…")
            self._soan(su_viec, dieu_dd, kq)
        kq.giay = round(time.time() - t0, 1)
        return kq
