"""Xếp lại top-N Điều bằng một mô hình đọc (câu hỏi, chữ Điều) CÙNG LÚC (thí nghiệm, chưa nối vào tìm kiếm mặc định).

Vì sao: tìm bằng vector so câu hỏi với từng đoạn luật độc lập nên hay nhầm giữa các Điều anh em (130/131/155, 364/365...), nhưng
đáp án thường đã nằm trong top 5 (bộ dev: Hit@1 73%, Hit@3 89%, Hit@5 93%). Mô hình xếp lại đọc cả câu hỏi lẫn chữ Điều nên có
cơ hội phân biệt tốt hơn; cái giá là chậm hơn (chỉ chấm N Điều mỗi câu hỏi).

Hai cách chấm, cùng giao diện `cham(cau_hoi, van_ban) -> list[float]` (điểm cao = khớp hơn):
  - BgeReranker: bge-reranker-v2-m3 chạy bằng onnxruntime (cần `pip install onnxruntime tokenizers` và tải mô hình một lần: scripts/tai_xep_lai.py);
  - LLMXepLai: Qwen3 qua Ollama, cho điểm 0-10 từng Điều (chấm hai lượt, đảo thứ tự để giảm thiên lệch vị trí).
Điểm cuối cùng = z(điểm xếp lại) + w * z(điểm vector) trong tập N ứng viên (w = 0: chỉ tin mô hình xếp lại).
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path

NHIEU_HIT1 = 0.03          # chênh < 3 điểm phần trăm trên ~70 câu là trong mức nhiễu (2 câu)


class XepLaiError(Exception):
    pass


# ---------------------------------------------------------------- mô hình chấm

class BgeReranker:
    """bge-reranker-v2-m3 (ONNX). Thư mục chứa tokenizer.json và onnx/model.onnx (+ model.onnx_data)."""
    name = "bge-reranker-v2-m3"

    def __init__(self, thu_muc: str | Path, max_len: int = 512, so_luong: int = 4, so_luong_cpu: int | None = None):
        thu_muc = Path(thu_muc)
        mo_hinh, tokenizer = thu_muc / "onnx" / "model.onnx", thu_muc / "tokenizer.json"
        if not mo_hinh.exists() or not tokenizer.exists():
            raise XepLaiError(f"chưa có mô hình ở {thu_muc}. Chạy: python scripts/tai_xep_lai.py (tải ~2,3 GB một lần)")
        try:
            import onnxruntime as ort
            from tokenizers import Tokenizer
        except ImportError as e:
            raise XepLaiError("thiếu thư viện. Chạy: pip install onnxruntime tokenizers") from e
        self._np = __import__("numpy")
        self.tok = Tokenizer.from_file(str(tokenizer))
        self.tok.enable_truncation(max_length=max_len, strategy="only_second")          # cắt phần chữ Điều, giữ nguyên câu hỏi
        self.pad = self.tok.token_to_id("<pad>") or 1
        so = ort.SessionOptions()
        if so_luong_cpu:
            so.intra_op_num_threads = so_luong_cpu
        self.sess = ort.InferenceSession(str(mo_hinh), so, providers=["CPUExecutionProvider"])
        self.vao = {i.name for i in self.sess.get_inputs()}
        self.bs = so_luong

    def cham(self, cau_hoi: str, van_ban: list[str]) -> list[float]:
        np = self._np
        out: list[float] = []
        for i in range(0, len(van_ban), self.bs):
            enc = self.tok.encode_batch([(cau_hoi, v) for v in van_ban[i:i + self.bs]])
            L = max(len(e.ids) for e in enc)
            ids = np.full((len(enc), L), self.pad, dtype=np.int64)
            att = np.zeros((len(enc), L), dtype=np.int64)
            for j, e in enumerate(enc):
                ids[j, :len(e.ids)] = e.ids
                att[j, :len(e.ids)] = 1
            feed = {k: v for k, v in (("input_ids", ids), ("attention_mask", att)) if k in self.vao}
            out.extend(float(x) for x in self.sess.run(None, feed)[0].reshape(len(enc), -1)[:, 0])
        return out


def rut_gon(van_ban: str, toi_da: int = 600) -> str:
    """Tiêu đề + Khoản 1 (cắt trước 'Khoản 2'), tối đa `toi_da` ký tự: đủ để biết Điều quy định hành vi gì mà không tràn ngữ cảnh LLM."""
    m = re.search(r"\nKhoản 2", van_ban)
    s = van_ban[:m.start()] if m else van_ban
    return s[:toi_da].rstrip()


PROMPT_CHAM = """Bạn chấm mức khớp giữa MỘT câu hỏi của người dân và các Điều luật hình sự Việt Nam.

Câu hỏi: «{cau_hoi}»

Các Điều:
{ds}

Với từng Điều, cho điểm nguyên từ 0 đến 10: Điều đó có quy định đúng HÀNH VI mà câu hỏi mô tả không? (10 = đúng hoàn toàn, 0 = không liên quan).
Nhiều Điều có chủ đề gần nhau: chỉ cho điểm cao nhất cho Điều khớp nhất, các Điều còn lại thấp hơn.
Chỉ trả JSON: {{"diem": [điểm của [1], điểm của [2], ...]}} (đúng {n} số, theo thứ tự trên)."""


class LLMXepLai:
    """Qwen3 qua Ollama (đối tượng có `.hoi(prompt) -> str`, vd OllamaLLM). Mỗi câu hỏi 2 lần gọi: thứ tự gốc và thứ tự đảo, lấy trung bình."""

    def __init__(self, llm, toi_da_ky_tu: int = 600):
        self.llm, self.toi_da = llm, toi_da_ky_tu
        self.name = f"llm:{getattr(llm, 'model', getattr(llm, 'name', '?'))}"
        self.loi = 0

    def _mot_luot(self, cau_hoi: str, van_ban: list[str]) -> list[float]:
        ds = "\n\n".join(f"[{i}] {rut_gon(v, self.toi_da)}" for i, v in enumerate(van_ban, 1))
        tho = self.llm.hoi(PROMPT_CHAM.format(cau_hoi=cau_hoi, ds=ds, n=len(van_ban)))
        try:
            d = json.loads(tho)["diem"]
            if len(d) != len(van_ban):
                raise ValueError("sai số lượng")
            return [float(x) for x in d]
        except (ValueError, KeyError, TypeError, json.JSONDecodeError) as e:
            raise XepLaiError(f"LLM trả kết quả không đọc được ({e}): {tho[:200]!r}") from e

    def cham(self, cau_hoi: str, van_ban: list[str]) -> list[float]:
        thuan = self._mot_luot(cau_hoi, van_ban)
        dao = self._mot_luot(cau_hoi, van_ban[::-1])[::-1]
        return [(a + b) / 2 for a, b in zip(thuan, dao)]


# ---------------------------------------------------------------- trộn điểm và đo

def z(a: list[float]) -> list[float]:
    n = len(a)
    if n == 0:
        return []
    m = sum(a) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in a) / n)
    return [(x - m) / sd if sd > 1e-9 else 0.0 for x in a]


def xep_lai_top(cand: list[dict], diem_xl: list[float], w: float, top: int | None = None) -> list[str]:
    """cand: [{'dieu', 'vec'}] đã xếp theo vector giảm dần; diem_xl: điểm xếp lại của `top` Điều đầu. Trả thứ tự Điều mới
    (phần ngoài top giữ nguyên thứ tự cũ). Hoà điểm giữ thứ tự vector."""
    top = len(diem_xl) if top is None else top
    dau, duoi = cand[:top], [c["dieu"] for c in cand[top:]]
    s = [a + w * b for a, b in zip(z(diem_xl[:top]), z([c["vec"] for c in dau]))]
    thu_tu = sorted(range(len(dau)), key=lambda i: (-s[i], i))
    return [dau[i]["dieu"] for i in thu_tu] + duoi


def hang_dap_an(thu_tu: list[str], dap_an) -> int | None:
    return next((i for i, d in enumerate(thu_tu, 1) if d in dap_an), None)


def chi_so(hang: list[int | None]) -> dict:
    n = len(hang)
    return {"hit1": sum(1 for r in hang if r == 1) / n, "hit3": sum(1 for r in hang if r and r <= 3) / n,
            "hit5": sum(1 for r in hang if r and r <= 5) / n, "mrr": sum(1 / r for r in hang if r and r <= 10) / n}


def kiem_dinh_dau(cuu: int, pha: int) -> float:
    """Kiểm định dấu hai phía (nhị thức, p = 0,5) cho số câu được cứu / bị phá: xác suất thấy chênh lệch lớn như vậy do ngẫu nhiên."""
    n = cuu + pha
    if n == 0:
        return 1.0
    k = max(cuu, pha)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n)


def quet_w(items: list[dict], ws, top: int) -> tuple[dict, list[dict]]:
    """items: [{'dap_an', 'cand': [{'dieu','vec'}...], 'diem_xl': [...]}]. Trả (baseline, [dòng cho từng w])."""
    goc = [hang_dap_an([c["dieu"] for c in it["cand"]], it["dap_an"]) for it in items]
    base = chi_so(goc)
    dong = []
    for w in ws:
        hang = [hang_dap_an(xep_lai_top(it["cand"], it["diem_xl"][:top], w, top), it["dap_an"]) for it in items]
        cuu = sum(1 for a, b in zip(goc, hang) if a != 1 and b == 1)
        pha = sum(1 for a, b in zip(goc, hang) if a == 1 and b != 1)
        dong.append({"w": w, **chi_so(hang), "cuu": cuu, "pha": pha, "p": kiem_dinh_dau(cuu, pha)})
    return base, dong


def ket_luan_xep_lai(base: dict, dong: list[dict], nhieu: float = NHIEU_HIT1) -> tuple[bool, str]:
    """Có lợi chỉ khi có ÍT NHẤT 2 giá trị w LIỀN KỀ cùng hơn baseline >= `nhieu` (Hit@1 hoặc MRR) và không w nào trong dải đó tệ hơn
    baseline quá nửa mức nhiễu. Quy tắc 'dải ổn định, đừng chọn ô cao nhất' như quét hệ số câu hỏi sinh sẵn."""
    dong = sorted(dong, key=lambda d: d["w"])
    tot = [d["hit1"] - base["hit1"] >= nhieu or d["mrr"] - base["mrr"] >= nhieu for d in dong]
    te = [d["hit1"] - base["hit1"] < -nhieu / 2 or d["mrr"] - base["mrr"] < -nhieu / 2 for d in dong]
    for i in range(len(dong) - 1):
        if tot[i] and tot[i + 1] and not te[i] and not te[i + 1]:
            return True, (f"w = {dong[i]['w']}–{dong[i + 1]['w']} cùng hơn baseline (Hit@1 {dong[i]['hit1']:.1%} / {dong[i + 1]['hit1']:.1%} "
                          f"so với {base['hit1']:.1%})")
    return False, "không có dải ≥ 2 giá trị w liền kề nào hơn baseline vượt mức nhiễu"
