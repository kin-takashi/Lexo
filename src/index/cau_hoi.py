"""Câu hỏi đời thường sinh sẵn cho từng Điều (doc2query): LLM local viết, bge-m3 nhúng, dùng để thu hẹp khoảng cách giữa
lời người dân ("không chịu đóng tiền nuôi con") và thuật ngữ luật ("nghĩa vụ cấp dưỡng").

Chỉ sinh cho bản đang có hiệu lực. Tách bạch với bộ câu hỏi kiểm tra (tập kiem_tra của eval/bo_cau_hoi.json): máy chỉ đọc chữ của luật,
không bao giờ nhìn thấy bộ kiểm tra."""
from __future__ import annotations

import json
import re
import sqlite3
import time
import unicodedata

import numpy as np
import urllib.error
import urllib.request

from src.index.chunks import hash_text

PHIEN_BAN_LENH = "v2"          # đổi khi sửa PROMPT: các Điều sẽ được sinh lại

PROMPT = """Bạn là một người dân bình thường, không biết luật. Dưới đây là một điều của Bộ luật hình sự Việt Nam.
Hãy viết {n} câu hỏi mà một người dân có thể gõ vào ô tìm kiếm khi gặp đúng tình huống mà điều luật này quy định.

Yêu cầu:
- Mỗi câu nêu một tình huống cụ thể giữa người với người: ai làm gì, với ai hoặc với cái gì, hậu quả ra sao.
- Chỉ dựa vào điều luật dưới đây. Tình huống phải là hành vi mà CHÍNH điều luật này quy định, không lấy chuyện khác.
- Dùng lời nói thường ngày. KHÔNG chép tên điều luật. KHÔNG dùng các từ: Điều, khoản, điểm, tội, Bộ luật, hình sự, truy cứu.
- Chỉ viết bằng tiếng Việt, không chèn chữ nước ngoài.
- Mỗi câu từ 6 đến 20 từ; các câu khác nhau về tình huống.
- Chỉ trả về JSON đúng dạng {{"cau_hoi": ["...", "..."]}}, không giải thích gì thêm.

ĐIỀU LUẬT:
{van_ban}
"""

CAM = ("điều", "khoản", "điểm", "tội", "bộ luật", "hình sự", "truy cứu")
CHU_NUOC_NGOAI = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af\u0400-\u04ff]")   # Hán, Nhật, Hàn, Kirin
UU_TIEN_MO_HINH = ("qwen3:8b", "qwen3:4b", "qwen2.5:7b", "qwen2.5:3b", "llama3.1:8b", "llama3.2:3b", "qwen2.5:1.5b")


class LLMError(RuntimeError):
    pass


def la_model_nghi(ten: str) -> bool:
    """Model có chế độ 'nghĩ' (thinking) cần tắt khi sinh JSON ngắn: họ Qwen3."""
    return "qwen3" in ten.lower()


_THINK = re.compile(r"<think>.*?</think>", re.S)


class OllamaLLM:
    """Gọi Ollama /api/chat, ép đầu ra JSON. Với Qwen3 luôn TẮT chế độ nghĩ (nếu không sẽ chậm gấp nhiều lần và dễ hỏng JSON):
      1) gửi "think": false (Ollama >= 0.9);
      2) dự phòng cho bản Ollama cũ bỏ qua tham số đó: thêm "/no_think" cuối lời nhắc, và gỡ khối <think>...</think> khỏi kết quả.
    `da_thay_think` bật lên nếu vẫn thấy model nghĩ (nên cập nhật Ollama)."""

    def __init__(self, model: str, endpoint: str = "http://localhost:11434", timeout: int = 900, retries: int = 2, think: bool = False,
                 nhiet_do: float | None = None):
        self.model, self.endpoint, self.timeout, self.retries, self.think = model, endpoint.rstrip("/"), timeout, retries, think
        self.nhiet_do = nhiet_do                           # None = mặc định để sinh câu hỏi (đa dạng); 0 = xác định, dùng khi chấm điểm
        self.da_thay_think = False

    @property
    def name(self) -> str:
        return f"ollama:{self.model}"

    def _body(self, prompt: str) -> dict:
        opts = {"temperature": 0.5, "num_ctx": 4096}
        body = {"model": self.model, "stream": False, "format": "json", "keep_alive": "30m", "options": opts}
        if la_model_nghi(self.model):
            body["think"] = bool(self.think)
            opts.update({"temperature": 0.7, "top_p": 0.8, "top_k": 20})            # thông số khuyến nghị của Qwen3 ở chế độ không nghĩ
            if not self.think:
                prompt = prompt.rstrip() + "\n/no_think"
        if self.nhiet_do is not None:
            opts.update({"temperature": self.nhiet_do, "seed": 0})
        body["messages"] = [{"role": "user", "content": prompt}]
        return body

    def hoi(self, prompt: str) -> str:
        data = json.dumps(self._body(prompt)).encode("utf-8")
        loi: Exception | None = None
        for lan in range(self.retries):
            req = urllib.request.Request(self.endpoint + "/api/chat", data=data, headers={"Content-Type": "application/json"})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    msg = json.loads(resp.read().decode("utf-8"))["message"]
                noi_dung = msg.get("content") or ""
                if (msg.get("thinking") or "<think>" in noi_dung) and la_model_nghi(self.model) and not self.think:
                    self.da_thay_think = True
                return _THINK.sub("", noi_dung).strip()
            except urllib.error.HTTPError as e:
                ct = e.read().decode("utf-8", "replace")[:300]
                if e.code == 404:
                    raise LLMError(f"Ollama chưa có model '{self.model}'. Chạy: ollama pull {self.model} ({ct})") from e
                loi = LLMError(f"Ollama báo lỗi HTTP {e.code}: {ct}")
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                loi = LLMError(f"không kết nối được Ollama ở {self.endpoint} ({getattr(e, 'reason', e)})")
            if lan < self.retries - 1:
                time.sleep(2)
        raise loi  # type: ignore[misc]


class LLMGia:
    """LLM giả cho kiểm thử: trả câu hỏi cố định dựng từ tên Điều (không phản ánh chất lượng thật)."""
    name = "gia"

    def __init__(self):
        self.so_lan = 0

    def hoi(self, prompt: str) -> str:
        self.so_lan += 1
        tieu_de = re.search(r"Điều \d+\w*\. (.+)", prompt).group(1)
        goc = tieu_de.lower().replace("tội ", "").split()[0]          # chỉ lấy một từ để không chép nguyên tên Điều
        return json.dumps({"cau_hoi": [f"nếu mình lỡ dính vào chuyện {goc} thì sao nhỉ {i}" for i in range(1, 6)]}, ensure_ascii=False)


def chon_mo_hinh(endpoint: str = "http://localhost:11434") -> tuple[str, list[str]]:
    """Chọn model theo thứ ưu tiên trong số đã cài. Trả (tên, danh sách đã cài)."""
    try:
        with urllib.request.urlopen(endpoint.rstrip("/") + "/api/tags", timeout=10) as r:
            ten = [m["name"] for m in json.loads(r.read().decode("utf-8"))["models"]]
    except (urllib.error.URLError, TimeoutError, ConnectionError, KeyError) as e:
        raise LLMError(f"không đọc được danh sách model từ Ollama ({e})") from e
    for pref in UU_TIEN_MO_HINH:
        for t in ten:
            if t == pref or t.startswith(pref + "-") or (":" not in pref and t.startswith(pref + ":")):
                return t, ten
    raise LLMError("chưa thấy model sinh chữ nào phù hợp. Cài một cái, ví dụ: ollama pull qwen3:8b (hoặc truyền --llm). Đã cài: " + ", ".join(ten))


def _fold(s: str) -> str:
    return unicodedata.normalize("NFC", s).lower().strip()


def doc_ket_qua(raw: str) -> list[str]:
    """Rút danh sách câu hỏi từ đầu ra của LLM (JSON; nếu hỏng thì lấy từng dòng)."""
    m = re.search(r"\{.*\}", raw, re.S)
    if m:
        try:
            v = json.loads(m.group(0)).get("cau_hoi")
            if isinstance(v, list):
                return [str(x) for x in v if isinstance(x, (str, int, float))]
        except (json.JSONDecodeError, AttributeError):
            pass
    return [re.sub(r'^\s*(?:[-*•]|\d+[.)])\s*', "", ln).strip(' "') for ln in raw.splitlines() if len(ln.split()) >= 4]


def loc_cau_hoi(ds: list[str], tieu_de: str) -> list[str]:
    """Bỏ câu quá ngắn/dài, câu chứa từ cấm hoặc chép nguyên tên Điều, câu trùng. Giữ thứ tự."""
    ten = _fold(re.sub(r"^Điều \d+\w*\.\s*", "", tieu_de))
    ten = re.sub(r"^tội\s+", "", ten)
    ra, thay = [], set()
    for c in ds:
        c = " ".join(c.split()).strip(' "')
        f = _fold(c)
        if not 4 <= len(c.split()) <= 28 or CHU_NUOC_NGOAI.search(c):
            continue
        if any(re.search(rf"(?<!\w){re.escape(t)}(?!\w)", f) for t in CAM):
            continue
        if len(ten.split()) >= 3 and ten in f:
            continue
        if f in thay:
            continue
        thay.add(f)
        ra.append(c)
    return ra


def gom_dieu(idx: sqlite3.Connection, toi_da_ky_tu: int = 3500) -> dict[str, dict]:
    """Chữ đầy đủ của từng Điều đang có hiệu lực, ghép từ các đoạn: {dieu: {tieu_de, van_ban, hash}}.
    Bỏ Điều không có chữ riêng (chỉ có tiêu đề), vì không có gì để hỏi."""
    cs: dict[str, list] = {}
    for r in idx.execute("SELECT key, loai, text, noi_dung FROM chunk WHERE hieu_luc_den IS NULL ORDER BY phien_ban_id"):
        cs.setdefault(r["key"].split("/")[0], []).append(r)
    out = {}
    for d, rs in cs.items():
        tieu_de = rs[0]["text"].split("\n", 1)[0]
        dong = [tieu_de]
        for r in rs:
            ls = r["text"].split("\n")
            if r["loai"] == "diem":
                dong.append(ls[-1])
            else:
                dong += ls[1:]
        if len(" ".join(dong[1:])) < 40:
            continue
        vb = "\n".join(dong)
        if len(vb) > toi_da_ky_tu:
            vb = vb[:toi_da_ky_tu].rsplit("\n", 1)[0] + "\n…"
        out[d] = {"tieu_de": tieu_de, "van_ban": vb, "hash": hash_text(PHIEN_BAN_LENH + "\n" + vb)}
    return out


_TIEU_DE_TOI = re.compile(r"^Điều\s+\S+\.\s*Tội\b")


def loc_dieu_toi_pham(dieu: dict[str, dict]) -> dict[str, dict]:
    """Chỉ giữ Điều có tiêu đề 'Tội ...' (điều về một tội phạm cụ thể). Điều thuộc Phần chung (nguyên tắc, tuổi, ý thức lỗi, hiệu lực…)
    không quy định một hành vi nên LLM chỉ bịa tình huống phạm tội chung chung ("Tôi đánh nhau…" cho cả Điều 1 'Nhiệm vụ của Bộ luật'),
    làm câu sinh vừa sai vừa trùng nhau giữa các Điều (đo được: khứ hồi hạng 1 chỉ 15% trên Điều 1–41)."""
    return {d: v for d, v in dieu.items() if _TIEU_DE_TOI.match(v["tieu_de"])}


def can_sinh(idx: sqlite3.Connection, dieu: dict[str, dict], mo_hinh: str) -> list[str]:
    """Điều chưa có câu hỏi, hoặc đã có nhưng chữ Điều đã đổi, theo thứ tự xuất hiện."""
    da = {r["dieu"]: r["hash_dieu"] for r in idx.execute("SELECT DISTINCT dieu, hash_dieu FROM cau_hoi_sinh WHERE mo_hinh = ?", (mo_hinh,))}
    return [d for d, v in dieu.items() if da.get(d) != v["hash"]]


def luu_cau_hoi(idx: sqlite3.Connection, d: str, hash_dieu: str, mo_hinh: str, cau_hoi: list[str]) -> None:
    with idx:
        idx.execute("DELETE FROM cau_hoi_sinh WHERE dieu = ? AND mo_hinh = ?", (d, mo_hinh))
        idx.executemany("INSERT INTO cau_hoi_sinh (dieu, hash_dieu, mo_hinh, stt, cau_hoi, hash) VALUES (?,?,?,?,?,?)",
                        [(d, hash_dieu, mo_hinh, i, c, hash_text(c)) for i, c in enumerate(cau_hoi, 1)])


def don_cau_hoi_mo_coi(idx: sqlite3.Connection, dieu: dict[str, dict]) -> int:
    """Xoá câu hỏi của Điều không còn trong bản hiện hành."""
    con = tuple(dieu)
    if not con:
        return 0
    with idx:
        cur = idx.execute(f"DELETE FROM cau_hoi_sinh WHERE dieu NOT IN ({','.join('?' * len(con))})", con)
    return cur.rowcount


def sinh_mot(llm, d: dict, so_cau: int = 5) -> list[str]:
    """Sinh câu hỏi cho một Điều (thử lại một lần nếu lọc xong còn < 3 câu). Trả danh sách đã lọc (có thể rỗng)."""
    prompt = PROMPT.format(n=so_cau, van_ban=d["van_ban"])
    tot: list[str] = []
    for _ in range(2):
        tot = loc_cau_hoi(tot + doc_ket_qua(llm.hoi(prompt)), d["tieu_de"])
        if len(tot) >= 3:
            break
    return tot[: so_cau + 2]


def _hang_dieu(idx: sqlite3.Connection, model: str, Q: np.ndarray, dieu_dung: list[str]) -> list[int | None]:
    """Hạng của Điều đúng (theo cosine lớn nhất với các đoạn đang hiệu lực) cho từng vector câu hỏi Q (đã chuẩn hoá).
    None nếu Điều đó không có đoạn nào có vector."""
    ch = idx.execute("""SELECT c.key AS key, v.vec AS vec FROM chunk c JOIN vec_cache v ON v.hash = c.hash AND v.model = ?
                        WHERE c.hieu_luc_den IS NULL""", (model,)).fetchall()
    if not ch or not len(Q):
        return [None] * len(dieu_dung)
    M = np.vstack([np.frombuffer(r["vec"], dtype="<f4") for r in ch])
    ten = sorted({r["key"].split("/")[0] for r in ch})
    vt = {t: i for i, t in enumerate(ten)}
    col = np.array([vt[r["key"].split("/")[0]] for r in ch])
    order = np.argsort(col, kind="stable")
    S = (Q @ M.T)[:, order]
    cs = col[order]
    dau = np.flatnonzero(np.r_[True, cs[1:] != cs[:-1]])
    tot = np.maximum.reduceat(S, dau, axis=1)               # (số câu, số Điều), cột theo thứ tự ten
    ra: list[int | None] = []
    for i, d in enumerate(dieu_dung):
        ra.append(None if d not in vt else 1 + int((tot[i] > tot[i, vt[d]]).sum()))
    return ra


def hang_dieu_cua_cau_hoi(idx: sqlite3.Connection, emb, dieu_dung: list[str], cau_hoi: list[str]) -> list[int | None]:
    """Nhúng các câu hỏi rồi cho biết Điều đúng của từng câu đứng hạng mấy (1 = tìm ra ngay). Không cần bộ câu hỏi kiểm tra."""
    from src.index.store import chuan_hoa
    return _hang_dieu(idx, emb.name, chuan_hoa(emb.embed(cau_hoi)), dieu_dung)


def loc_vong(idx: sqlite3.Connection, model: str, top: int = 3) -> dict:
    """Lọc vòng (round-trip): giữ câu hỏi sinh sẵn chỉ khi Điều nguồn của nó đứng trong `top` hạng đầu khi tìm bằng chính câu đó.
    Loại câu lạc đề/ảo giác của LLM nhỏ mà không cần bộ kiểm tra. top = 0: giữ tất cả."""
    qs = idx.execute("""SELECT s.rowid AS rid, s.dieu AS dieu, v.vec AS vec FROM cau_hoi_sinh s
                        JOIN vec_cache v ON v.hash = s.hash AND v.model = ?""", (model,)).fetchall()
    if not qs:
        return {"so_cau": 0, "giu": 0, "hang1": 0}
    if top <= 0:
        with idx:
            idx.execute("UPDATE cau_hoi_sinh SET giu = 1")
        return {"so_cau": len(qs), "giu": len(qs), "hang1": 0}
    Q = np.vstack([np.frombuffer(r["vec"], dtype="<f4") for r in qs])
    ra = _hang_dieu(idx, model, Q, [r["dieu"] for r in qs])
    giu = [1 if (h is not None and h <= top) else 0 for h in ra]
    with idx:
        idx.execute("UPDATE cau_hoi_sinh SET giu = 0")
        idx.executemany("UPDATE cau_hoi_sinh SET giu = ? WHERE rowid = ?", [(g, r["rid"]) for g, r in zip(giu, qs)])
    return {"so_cau": len(qs), "giu": sum(giu), "hang1": sum(1 for h in ra if h == 1)}


def chon_trai_deu(ds: list[str], n: int) -> list[str]:
    """n phần tử cách đều nhau trong ds (giữ thứ tự). Dùng để lấy mẫu thử đại diện toàn bộ luật thay vì n Điều đầu (toàn Phần chung)."""
    if n <= 0 or not ds:
        return []
    n = min(n, len(ds))
    buoc = len(ds) / n
    return [ds[int(i * buoc)] for i in range(n)]


def dieu_dap_an(bo: list[dict]) -> set[str]:
    """Khoá Điều ('dieu 173') là đáp án của một bộ câu hỏi. CHỈ lấy số Điều; chữ câu hỏi không bao giờ đi vào lời nhắc."""
    return {f"dieu {d}" for c in bo for d in c["dieu"]}


def lam_moi_theo_phien_ban_lenh(idx: sqlite3.Connection) -> int:
    """Nếu lời nhắc đã đổi phiên bản kể từ lần sinh trước: xoá hết câu hỏi cũ (chúng được viết theo lời nhắc khác). Trả số dòng xoá."""
    r = idx.execute("SELECT v FROM meta WHERE k = 'cau_hoi_lenh'").fetchone()
    xoa = 0
    with idx:
        if r is not None and r["v"] != PHIEN_BAN_LENH:
            xoa = idx.execute("DELETE FROM cau_hoi_sinh").rowcount
        elif r is None:
            xoa = idx.execute("DELETE FROM cau_hoi_sinh").rowcount          # bản sinh trước khi có ghi phiên bản: lời nhắc v1, bỏ
        idx.execute("INSERT OR REPLACE INTO meta (k, v) VALUES ('cau_hoi_lenh', ?)", (PHIEN_BAN_LENH,))
    return xoa
