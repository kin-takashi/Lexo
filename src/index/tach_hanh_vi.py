"""Tách một tình huống thành các hành vi bằng LLM local (qwen3:4b qua Ollama), CHỈ bằng lời nhắc: chưa tinh chỉnh.

Đây là bản thử (prototype) cho bước «tách» của đường ống: tình huống → các hành vi → (mỗi hành vi) tìm Điều → gợi ý «hành vi → 2–3 Điều».
Mục đích: biết qwen3:4b chưa tinh chỉnh tách đạt tới đâu so với mốc «không tách» và mức trần «tách lý tưởng» (scripts/danh_gia_nhieu.py),
trước khi quyết định có đáng tinh chỉnh LoRA hay không.

Lời nhắc hệ thống DÙNG LẠI HE_THONG của tập train (src/index/tap_train.py), đúng chữ mà mô hình tinh chỉnh sau này sẽ học, để so sánh
«chỉ lời nhắc» với «tinh chỉnh» là so sánh công bằng. Hai kiểu viết hành vi, để đo tiền tố tên tội:
  thuan    giữ nguyên HE_THONG; ví dụ mẫu (nếu có) bỏ tiền tố tên tội.
  ten_toi  thêm yêu cầu mở đầu mỗi hành vi bằng tên tội «Hiếp dâm: ...»; ví dụ mẫu giữ tiền tố.
Ví dụ mẫu (few-shot) lấy từ train/tinh_huong.json, chỉ từ phần train (không lấy phần val), và KHÔNG chọn mẫu nào có Điều trùng với
đáp án của bất kỳ câu nhieu_dieu nào trong bộ đo, nên mô hình không thấy sẵn cách viết của các Điều cần tìm.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Iterable, Sequence

from src.index.cau_hoi import LLMError, OllamaLLM, la_model_nghi
from src.index.tap_train import HE_THONG, tap_cua

KIEU = ("thuan", "ten_toi")
TOI_DA_HANH_VI = 8

NHAC_TEN_TOI = (" Mỗi hành vi mở đầu bằng tên tội theo cách gọi thông thường rồi dấu hai chấm, theo mẫu "
                "«Hiếp dâm: dùng vũ lực ép nạn nhân quan hệ tình dục».")
QUY_TAC = (" Quy tắc tách: mỗi tội khác nhau là một hành vi riêng (kể cả khi do những người khác nhau phạm); nhiều lần hoặc nhiều nạn nhân của "
           "cùng một tội thì gộp thành một hành vi; tình tiết tăng nặng của cùng một hành vi (dùng dao, nhiều người, gây thương tích khi cướp) không tách riêng.")

SCHEMA = {"type": "object", "properties": {"hanh_vi": {"type": "array", "items": {"type": "string"}, "minItems": 1, "maxItems": TOI_DA_HANH_VI}},
          "required": ["hanh_vi"]}

_TIEN_TO = re.compile(r"^([^:：]{3,120}):\s+(\S.*)$", re.S)
_THINK = re.compile(r"<think>.*?</think>", re.S)


class TachError(RuntimeError):
    pass


def tach_tien_to(mo_ta: str) -> tuple[str | None, str]:
    """'Hiếp dâm: dùng vũ lực...' -> ('Hiếp dâm', 'dùng vũ lực...'). Không có tiền tố -> (None, mo_ta). Tiền tố tối đa 20 từ
    (khớp cách đếm 420/894 hành vi có tiền tố của tập train)."""
    m = _TIEN_TO.match(mo_ta.strip())
    if m and len(m.group(1).split()) <= 20:
        return m.group(1).strip(), m.group(2).strip()
    return None, mo_ta.strip()


def bo_tien_to(mo_ta: str) -> str:
    """Bỏ tiền tố tên tội, viết hoa chữ đầu phần còn lại."""
    tt, con = tach_tien_to(mo_ta)
    return (con[:1].upper() + con[1:]) if tt else con


def he_thong(kieu: str, quy_tac: bool = False) -> str:
    if kieu not in KIEU:
        raise ValueError(f"kiểu phải là một trong {KIEU}")
    return HE_THONG + (NHAC_TEN_TOI if kieu == "ten_toi" else "") + (QUY_TAC if quy_tac else "")


def _bam(id_: str) -> str:
    return hashlib.sha1(id_.encode("utf-8")).hexdigest()


def chon_vi_du(mau: Sequence[dict], n: int, loai_tru_dieu: Iterable[str], kieu: str) -> list[dict]:
    """Chọn n mẫu làm ví dụ, xác định theo băm id: mẫu thứ hai là mẫu MỘT hành vi (dạy mô hình đừng tách thừa), còn lại là mẫu nhiều hành vi.
    Chỉ lấy mẫu thuộc phần train (không phải val), 2–3 hành vi (hoặc đúng 1), không có Điều nào thuộc `loai_tru_dieu`, các ví dụ đôi một
    không chung Điều; kiểu ten_toi chỉ lấy mẫu mà MỌI hành vi có tiền tố tên tội."""
    cam = set(loai_tru_dieu)

    def hop(x: dict) -> bool:
        if tap_cua(x["id"]) != "train":
            return False
        ds = {d for h in x["hanh_vi"] for d in h["dieu"]}
        if ds & cam:
            return False
        return kieu != "ten_toi" or all(tach_tien_to(h["mo_ta"])[0] for h in x["hanh_vi"])

    nhieu = sorted((x for x in mau if x.get("loai") == "nhieu" and 2 <= len(x["hanh_vi"]) <= 3 and hop(x)), key=lambda x: _bam(x["id"]))
    don = sorted((x for x in mau if x.get("loai") == "don" and len(x["hanh_vi"]) == 1 and hop(x)), key=lambda x: _bam(x["id"]))
    thu_tu = ["nhieu", "don"] + ["nhieu"] * max(0, n - 2)
    nguon = {"nhieu": nhieu, "don": don}
    chon: list[dict] = []
    da_dung: set[str] = set()
    for loai in thu_tu[:n]:
        for x in nguon[loai]:
            ds = {d for h in x["hanh_vi"] for d in h["dieu"]}
            if x not in chon and not (ds & da_dung):
                chon.append(x)
                da_dung |= ds
                break
    return chon


def dong_ra(x: dict, kieu: str) -> str:
    """Câu trả lời mẫu của một mẫu train, theo kiểu đã chọn."""
    ds = [h["mo_ta"] if kieu == "ten_toi" else bo_tien_to(h["mo_ta"]) for h in x["hanh_vi"]]
    return json.dumps({"hanh_vi": ds}, ensure_ascii=False)


def dung_tin_nhan(tinh_huong: str, kieu: str, vi_du: Sequence[dict] = (), quy_tac: bool = False) -> list[dict]:
    tn = [{"role": "system", "content": he_thong(kieu, quy_tac)}]
    for x in vi_du:
        tn += [{"role": "user", "content": x["tinh_huong"]}, {"role": "assistant", "content": dong_ra(x, kieu)}]
    tn.append({"role": "user", "content": tinh_huong})
    return tn


def doc_hanh_vi(chu: str) -> list[str]:
    """Đọc câu trả lời của mô hình thành danh sách hành vi. Chịu được khối <think>, rào ```json, chữ thừa quanh JSON."""
    chu = _THINK.sub("", chu or "").strip()
    chu = re.sub(r"^```(?:json)?\s*|\s*```$", "", chu).strip()
    obj = None
    for cand in (chu, *(m.group(0) for m in re.finditer(r"\{.*\}", chu, re.S))):
        try:
            obj = json.loads(cand)
            break
        except ValueError:
            continue
    if not isinstance(obj, dict) or not isinstance(obj.get("hanh_vi"), list):
        raise TachError(f"không đọc được JSON có khóa hanh_vi: {chu[:160]!r}")
    ra: list[str] = []
    for s in obj["hanh_vi"]:
        if isinstance(s, str) and s.strip() and s.strip() not in ra:
            ra.append(s.strip())
    if not ra:
        raise TachError("danh sách hành vi rỗng")
    return ra[:TOI_DA_HANH_VI]


class TachLLM(OllamaLLM):
    """OllamaLLM nhưng gửi cả hội thoại (system + ví dụ + câu hỏi), ép đầu ra theo SCHEMA, xác định (nhiệt độ 0, seed cố định).
    Kế thừa phần gọi mạng, thử lại và xử lý chế độ nghĩ của Qwen3 từ OllamaLLM.
    no_think_mem=False: chỉ gửi think=false, KHÔNG thêm «/no_think» vào câu hỏi. Dùng khi đo mô hình đã tinh chỉnh (dữ liệu học không có
    «/no_think»: lời nhắc lúc chạy phải giống lúc học); cần Ollama >= 0.9 để think=false có tác dụng."""

    def __init__(self, model: str = "qwen3:4b", endpoint: str = "http://localhost:11434", dinh_dang: str = "schema",
                 no_think_mem: bool = True, **kw):
        super().__init__(model, endpoint, **kw)
        self.dinh_dang, self.seed, self.nhiet = dinh_dang, 0, 0.0
        self.no_think_mem = no_think_mem

    def _body(self, messages):                      # type: ignore[override]
        opts = {"temperature": self.nhiet, "seed": self.seed, "num_ctx": 4096, "num_predict": 700}
        body = {"model": self.model, "stream": False, "format": SCHEMA if self.dinh_dang == "schema" else "json",
                "keep_alive": "30m", "options": opts}
        tn = [dict(m) for m in messages]
        if la_model_nghi(self.model):
            body["think"] = bool(self.think)
            if not self.think and self.no_think_mem:  # dự phòng cho Ollama cũ bỏ qua "think": công tắc mềm của Qwen3
                tn[-1]["content"] = tn[-1]["content"].rstrip() + "\n/no_think"
        body["messages"] = tn
        return body


class LLMGiaTach:
    """LLM giả cho kiểm thử đường ống: mỗi câu của tình huống là một hành vi. KHÔNG phản ánh chất lượng thật."""
    name = "gia"
    da_thay_think = False
    seed = 0
    nhiet = 0.0

    def hoi(self, messages) -> str:
        chu = messages[-1]["content"]
        cau = [s.strip() for s in re.split(r"(?<=[.!?])\s+", chu) if s.strip()]
        return json.dumps({"hanh_vi": cau or [chu]}, ensure_ascii=False)


def tach_mot(llm, tinh_huong: str, kieu: str, vi_du: Sequence[dict] = (), quy_tac: bool = False, so_lan: int = 3) -> dict:
    """Tách một tình huống. Trả {'hanh_vi', 'tho', 'so_lan', 'loi', 'giay'}. Nếu cả so_lan lần đều hỏng: hanh_vi = [cả tình huống] (tức không tách)
    và `loi` ghi lý do, để bảng điểm vẫn tính đủ và không giấu lỗi."""
    tn = dung_tin_nhan(tinh_huong, kieu, vi_du, quy_tac)
    t0, tho, loi = time.time(), "", None
    for lan in range(so_lan):
        llm.seed, llm.nhiet = lan, (0.0 if lan == 0 else 0.3)           # lần sau đổi seed và thêm chút ngẫu nhiên, không thì ra y như cũ
        try:
            tho = llm.hoi(tn)
            return {"hanh_vi": doc_hanh_vi(tho), "tho": tho, "so_lan": lan + 1, "loi": None, "giay": round(time.time() - t0, 2)}
        except TachError as e:
            loi = str(e)
        except LLMError:
            llm.seed, llm.nhiet = 0, 0.0
            raise
    llm.seed, llm.nhiet = 0, 0.0
    return {"hanh_vi": [tinh_huong], "tho": tho, "so_lan": so_lan, "loi": loi, "giay": round(time.time() - t0, 2)}
