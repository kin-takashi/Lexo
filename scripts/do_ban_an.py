"""Đo trên bộ bản án (gói lexo_do_ban_an): Vòng 1, cổng G3/G4 của LoRA chọn Điều, và lượt test cuối. Chạy trên Kaggle (Ollama + GPU).

  python scripts/do_ban_an.py --tap train90                                  # Vòng 1: A, B0, B1, C0 trên 90 vụ train
  python scripts/do_ban_an.py --tap dev --cau-hinh C0,L --mo-hinh-chon qwen3-8b-lexo-chon-dieu-v1   # G3/G4 của LoRA trên 20 vụ dev
  python scripts/do_ban_an.py --tap test --da-chot --chot cau_hinh_chot.json # lượt test: đúng một lần, cấu hình lấy từ file chốt
  python scripts/do_ban_an.py --tap dev --cau-hinh C0,L,HOP,LOC,LOC0         # kết hợp C0 và L từ kết quả đã có (không gọi lại mô hình)
  python scripts/do_ban_an.py --gia --tap dev                                # LLM + vector giả: chỉ thử đường ống

Cấu hình (--cau-hinh, cách nhau dấu phẩy):
  A    truy hồi thẳng: ứng viên đã xếp hạng trong gói, hiển thị top 3 (A3) và top 5 (A5); kèm bảng Recall@K
  B0   tách hành vi bằng mô hình gốc rồi mỗi hành vi tìm 3 Điều (cờ như dev 34: kiểu thuan, 0 ví dụ, không thêm /no_think)
  B1   như B0 nhưng mô hình tách n368
  C0   mô hình gốc chọn Điều từ K ứng viên (chưa học), cùng lời nhắc với LoRA
  L    LoRA chọn Điều (Vòng 2)
  HOP  hợp C0 ∪ L                                       } tính lại từ C0.jsonl và L.jsonl trên cùng vụ (cần cả C0 và L;
  LOC  C0 làm nền, L lọc: C0 ∩ L, giao rỗng thì giữ L  } vụ nào chưa có thì C0/L được chạy như thường).
  LOC0 như LOC nhưng giao rỗng thì giữ nguyên C0      } Xem chon_dieu.ket_hop.
Mọi mô hình gọi qua Ollama với num_ctx cố định (mặc định 8192) và ghi prompt_eval_count từng vụ; vụ có prompt_eval_count sát num_ctx
bị đánh dấu «có thể bị cắt» (Ollama cắt ngầm khi ngữ cảnh quá nhỏ). Chỉ chấm Điều 108–425 (nhãn của tòa chỉ gồm Điều tội phạm).
Kết quả: <ra>/<cấu hình>.jsonl (một dòng một vụ; chạy lại thì làm tiếp các vụ còn thiếu, không ghi đè) và <ra>/bao_cao.md.
Cấu hình đã đủ mọi vụ trong <ra> thì không gọi Ollama (không cần mô hình đó có sẵn). HOP/LOC/LOC0.jsonl được ghi lại mỗi lượt.
Tập test: chỉ chạy với --da-chot và file chốt; mô hình, K, chế độ ứng viên, num_ctx đều lấy từ file chốt, không nhận tham số khác.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ban_an import chon_dieu as cd  # noqa: E402
from src.index.tach_hanh_vi import SCHEMA as SCHEMA_TACH, TachError, doc_hanh_vi, dung_tin_nhan as tin_nhan_tach  # noqa: E402

KET_HOP = {"HOP": "hop", "LOC": "loc_l", "LOC0": "loc_c0"}
CAU_HINH = ("A", "B0", "B1", "C0", "L", *KET_HOP)
TAP_CHON = ("train90", "hoc", "dev", "test")
CO_LLM = {"B0": "goc", "B1": "tach", "C0": "goc", "L": "chon"}
SO_LAN = 3
NUM_PREDICT = {"tach": 700, "chon": 200}
CAP_SO_SANH = (("B1", "B0", "lợi ích của n368 có còn trên bản án thật"), ("L", "C0", "việc học có giúp"),
               ("HOP", "C0", "thêm L vào C0 có tìm đủ thêm vụ nào"), ("LOC", "C0", "để L lọc C0 có làm mất vụ tìm đủ"),
               ("LOC0", "C0", "để L lọc C0 (giao rỗng giữ C0) có làm mất vụ tìm đủ"))


class DoError(RuntimeError):
    pass


class QuaGio(DoError):
    """Một lần gọi quá thời gian chờ: ghi lỗi cho vụ đó rồi đi tiếp (không thử lại, không dừng cả lượt)."""


# --------------------------------------------------------------------------------------------------------------------
# Ollama
# --------------------------------------------------------------------------------------------------------------------


class Ollama:
    """Gọi /api/chat, không stream, nhiệt độ 0 (lần thử lại đổi seed và 0,3 như src/index/tach_hanh_vi.tach_mot), tắt chế độ nghĩ.
    Không thêm «/no_think» vào lời nhắc: dữ liệu học không có nó. Trả (chữ, thông tin đếm token)."""

    def __init__(self, endpoint: str, num_ctx: int, timeout: int = 900):
        self.endpoint, self.num_ctx, self.timeout = endpoint.rstrip("/"), num_ctx, timeout

    def co_san(self) -> set[str]:
        with urllib.request.urlopen(self.endpoint + "/api/tags", timeout=30) as r:
            ten = [m["name"] for m in json.loads(r.read().decode("utf-8")).get("models", [])]
        return set(ten) | {t[:-len(":latest")] for t in ten if t.endswith(":latest")}

    def chat(self, model: str, messages: list[dict], fmt, num_predict: int, seed: int, nhiet: float) -> tuple[str, dict]:
        body = {"model": model, "stream": False, "format": fmt, "keep_alive": "30m", "messages": messages, "think": False,
                "options": {"temperature": nhiet, "seed": seed, "num_ctx": self.num_ctx, "num_predict": num_predict}}
        req = urllib.request.Request(self.endpoint + "/api/chat", data=json.dumps(body).encode("utf-8"),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                out = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            raise DoError(f"Ollama báo lỗi HTTP {e.code} với {model}: {e.read().decode('utf-8', 'replace')[:300]}") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if isinstance(e, TimeoutError) or isinstance(getattr(e, "reason", None), TimeoutError):
                raise QuaGio(f"quá {self.timeout}s chờ {model}") from e
            raise DoError(f"không gọi được Ollama ở {self.endpoint}: {getattr(e, 'reason', e)}") from e
        msg = out.get("message") or {}
        info = {"prompt_eval_count": out.get("prompt_eval_count"), "eval_count": out.get("eval_count"),
                "co_think": bool(msg.get("thinking") or "<think>" in (msg.get("content") or ""))}
        return msg.get("content") or "", info


class OllamaGia:
    """Thay Ollama khi --gia: tách theo câu, chọn ứng viên đầu tiên. KHÔNG phản ánh chất lượng thật."""

    def __init__(self, num_ctx: int):
        self.num_ctx = num_ctx

    def co_san(self) -> set[str]:
        return {"*"}

    def chat(self, model, messages, fmt, num_predict, seed, nhiet):
        chu = messages[-1]["content"]
        info = {"prompt_eval_count": len(chu.split()), "eval_count": 5, "co_think": False}
        if "hanh_vi" in json.dumps(fmt, ensure_ascii=False):
            cau = [s.strip() for s in re.split(r"(?<=[.!?])\s+", chu) if s.strip()][:3]
            return json.dumps({"hanh_vi": cau or [chu[:200]]}, ensure_ascii=False), info
        return json.dumps({"dieu": fmt["properties"]["dieu"]["items"]["enum"][:1]}, ensure_ascii=False), info


def hoi_lap(llm, model: str, messages: list[dict], fmt, num_predict: int, doc) -> dict:
    """Hỏi tới SO_LAN lần tới khi đọc được. Trả {'ket_qua', 'loi', 'so_lan', 'giay', 'prompt_eval_count', 'eval_count', 'co_think', 'tho'}.
    Quá giờ thì dừng ngay ở vụ đó (ket_qua None, loi ghi «quá …s»)."""
    t0, loi, tho, info = time.time(), None, "", {}
    for lan in range(SO_LAN):
        try:
            tho, info = llm.chat(model, messages, fmt, num_predict, seed=lan, nhiet=0.0 if lan == 0 else 0.3)
        except QuaGio as e:
            return {"ket_qua": None, "loi": str(e), "so_lan": lan + 1, "giay": round(time.time() - t0, 2), **info, "tho": tho[:600]}
        try:
            return {"ket_qua": doc(tho), "loi": None, "so_lan": lan + 1, "giay": round(time.time() - t0, 2), **info, "tho": tho[:600]}
        except (cd.ChonError, TachError) as e:
            loi = str(e)
    return {"ket_qua": None, "loi": loi, "so_lan": SO_LAN, "giay": round(time.time() - t0, 2), **info, "tho": tho[:600]}


# --------------------------------------------------------------------------------------------------------------------
# Chấm
# --------------------------------------------------------------------------------------------------------------------


def binom_hai_phia(thang: int, n: int) -> float:
    """p chính xác hai phía của kiểm cặp McNemar: thang trên n cặp khác nhau, giả thuyết 0 là 1/2."""
    if n == 0:
        return 1.0
    k = max(thang, n - thang)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k, n + 1)) / 2 ** n)


def tong_hop(dong: list[dict]) -> dict:
    n = len(dong)
    if not n:
        return {}
    tb = {t: sum(r["cham"][t] for r in dong) / n for t in ("tim_du", "bao_phu", "chinh_xac", "khop_dung", "so_hien_thi")}
    tb.update({"n": n, "so_tim_du": int(sum(r["cham"]["tim_du"] for r in dong)), "loi": sum(1 for r in dong if r.get("loi")),
               "co_the_bi_cat": sum(1 for r in dong if r.get("co_the_bi_cat")), "co_think": sum(1 for r in dong if r.get("co_think")),
               "giay": sum(r.get("giay") or 0 for r in dong) / n})
    if any("lui" in r for r in dong):
        tb["lui"] = sum(1 for r in dong if r.get("lui"))
    if any("hanh_vi" in r for r in dong):
        tb["so_hanh_vi"] = sum(len(r.get("hanh_vi") or []) for r in dong) / n
        tb["dung_so_hanh_vi"] = sum(len(r.get("hanh_vi") or []) == len(r["dieu"]) for r in dong) / n
    return tb


def dong_bang(ten: str, tb: dict) -> str:
    hv = f"{tb['so_hanh_vi']:.1f} | {tb['dung_so_hanh_vi']:.0%}" if "so_hanh_vi" in tb else "– | –"
    return (f"| {ten} | {tb['so_tim_du']}/{tb['n']} ({tb['tim_du']:.0%}) | {tb['bao_phu']:.0%} | {tb['chinh_xac']:.0%} | {tb['khop_dung']:.0%} | "
            f"{tb['so_hien_thi']:.1f} | {hv} | {tb['loi']} | {tb['co_the_bi_cat']} | {tb['giay']:.1f} |")


def so_cap(a: list[dict], b: list[dict]) -> tuple[int, int, int, float]:
    """(n cặp khác nhau, a thắng, b thắng, p) trên «tìm đủ» của các vụ chung."""
    ta = {r["id"]: r["cham"]["tim_du"] for r in a}
    tb = {r["id"]: r["cham"]["tim_du"] for r in b}
    chung = ta.keys() & tb.keys()
    a_thang = sum(1 for i in chung if ta[i] > tb[i])
    b_thang = sum(1 for i in chung if tb[i] > ta[i])
    return a_thang + b_thang, a_thang, b_thang, binom_hai_phia(a_thang, a_thang + b_thang)


# --------------------------------------------------------------------------------------------------------------------
# Chạy từng cấu hình
# --------------------------------------------------------------------------------------------------------------------


def chay_A(mau: list[dict], che_do: str) -> dict[str, list[dict]]:
    ra = {}
    for k in (3, 5):
        ra[f"A{k}"] = [{"id": x["id"], "dieu": x["dieu"], "hien_thi": x["xep_hang"][che_do][:k],
                        "cham": cd.cham_chon(x["dieu"], x["xep_hang"][che_do][:k])} for x in mau]
    return ra


def doc_jsonl(p: Path) -> list[dict]:
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []


def chay_ket_hop(c0: list[dict], l: list[dict], cach: str, ten: str) -> list[dict]:
    """Một dòng mỗi vụ có cả C0 và L, theo thứ tự của C0. Thời gian và cờ cắt/think cộng dồn từ hai bên."""
    theo_l = {r["id"]: r for r in l}
    ra = []
    for a in c0:
        b = theo_l.get(a["id"])
        if b is None:
            continue
        hien, lui = cd.ket_hop(a["hien_thi"], b["hien_thi"], cach)
        loi = "; ".join(f"{r['cau_hinh']}: {r['loi']}" for r in (a, b) if r.get("loi")) or None
        ra.append({"id": a["id"], "cau_hinh": ten, "dieu": a["dieu"], "tu": {"C0": a["hien_thi"], "L": b["hien_thi"]}, "hien_thi": hien,
                   "lui": lui, "cham": cd.cham_chon(a["dieu"], hien), "loi": loi, "giay": (a.get("giay") or 0) + (b.get("giay") or 0),
                   "co_the_bi_cat": bool(a.get("co_the_bi_cat") or b.get("co_the_bi_cat")),
                   "co_think": bool(a.get("co_think") or b.get("co_think"))})
    return ra


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--goi", type=Path, default=ROOT, help="thư mục gói lexo_do_ban_an (mặc định: thư mục chứa script)")
    ap.add_argument("--tap", choices=TAP_CHON, default="train90")
    ap.add_argument("--cau-hinh", default=None, help="mặc định A,B0,B1,C0 (test: theo file chốt)")
    ap.add_argument("--mo-hinh-goc", default="qwen3:8b")
    ap.add_argument("--mo-hinh-tach", default="qwen3-8b-lexo-sach-n368")
    ap.add_argument("--mo-hinh-chon", default=None, help="tên LoRA chọn Điều trong Ollama (cấu hình L)")
    ap.add_argument("--k", type=int, default=None, help="mặc định theo cau_hinh.json của gói")
    ap.add_argument("--che-do-uv", choices=cd.CHE_DO_UV, default=None, help="mặc định theo cau_hinh.json của gói")
    ap.add_argument("--m", type=int, default=3, help="số Điều hiển thị mỗi hành vi (B0, B1)")
    ap.add_argument("--num-ctx", type=int, default=8192)
    ap.add_argument("--endpoint", default="http://localhost:11434")
    ap.add_argument("--model-nhung", default="bge-m3")
    ap.add_argument("--ra", type=Path, default=None, help="mặc định <goi>/ket_qua/<tap>")
    ap.add_argument("--chi-id", default=None)
    ap.add_argument("--bo-qua-thieu", action="store_true", help="bỏ qua cấu hình có mô hình chưa có trong Ollama (không dùng cho test)")
    ap.add_argument("--da-chot", action="store_true")
    ap.add_argument("--chot", type=Path, default=None, help="file cau_hinh_chot.json (bắt buộc với --tap test)")
    ap.add_argument("--gia", action="store_true")
    args = ap.parse_args()

    goi = args.goi
    try:
        du_lieu = json.loads((goi / "ban_an_do.json").read_text(encoding="utf-8"))
        cau_hinh_goi = json.loads((goi / "cau_hinh.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as e:
        sys.exit(f"LỖI: không đọc được gói đo ở {goi}: {e}")
    if cau_hinh_goi.get("gia") and not args.gia:
        print("CẢNH BÁO: gói này dựng bằng vector giả (--gia); số đo không có giá trị.")

    chot, sha_chot = None, None
    if args.tap == "test":
        if not (args.da_chot and args.chot):
            sys.exit("LỖI: tập test chỉ chạy một lần với cấu hình đã chốt: cần --da-chot và --chot cau_hinh_chot.json")
        if any(v is not None for v in (args.cau_hinh, args.mo_hinh_chon, args.k, args.che_do_uv)):
            sys.exit("LỖI: với tập test, mô hình / K / chế độ ứng viên chỉ lấy từ file chốt; bỏ các tham số đó")
        raw = args.chot.read_bytes()
        sha_chot = hashlib.sha256(raw).hexdigest()
        chot = json.loads(raw.decode("utf-8"))
        for t in ("cau_hinh", "mo_hinh_goc", "k", "che_do_uv", "num_ctx"):
            if t not in chot:
                sys.exit(f"LỖI: file chốt thiếu khóa {t!r}")
        ds_cau_hinh = [c.strip() for c in chot["cau_hinh"]]
        args.mo_hinh_goc, args.mo_hinh_tach = chot["mo_hinh_goc"], chot.get("mo_hinh_tach", args.mo_hinh_tach)
        args.mo_hinh_chon, args.num_ctx = chot.get("mo_hinh_chon"), chot["num_ctx"]
        k, che_do = chot["k"], chot["che_do_uv"]
    else:
        ds_cau_hinh = [c.strip() for c in (args.cau_hinh or "A,B0,B1,C0").split(",") if c.strip()]
        k = args.k or cau_hinh_goi["ung_vien"]["k"]
        che_do = args.che_do_uv or cau_hinh_goi["ung_vien"]["che_do"]
    sai = [c for c in ds_cau_hinh if c not in CAU_HINH]
    if sai:
        sys.exit(f"LỖI: cấu hình không hợp lệ: {sai}; chọn trong {CAU_HINH}")
    if any(c in KET_HOP for c in ds_cau_hinh):                 # cấu hình kết hợp cần C0 và L đứng trước nó
        dau = [c for c in ds_cau_hinh if c not in KET_HOP]
        ds_cau_hinh = dau + [c for c in ("C0", "L") if c not in dau] + [c for c in ds_cau_hinh if c in KET_HOP]

    tap = {"train90": ("hoc", "dev"), "hoc": ("hoc",), "dev": ("dev",), "test": ("test",)}[args.tap]
    mau = [x for x in du_lieu["mau"] if x["tap"] in tap]
    if args.chi_id:
        ids = {s.strip() for s in args.chi_id.split(",") if s.strip()}
        mau = [x for x in mau if x["id"] in ids]
    if not mau:
        sys.exit("LỖI: không có vụ nào để đo")
    ra = args.ra or goi / "ket_qua" / args.tap
    ra.mkdir(parents=True, exist_ok=True)
    ids_mau = {x["id"] for x in mau}
    da_du = {c for c in ds_cau_hinh if c in CO_LLM and ids_mau <= {r["id"] for r in doc_jsonl(ra / f"{c}.jsonl")}}
    if "L" in ds_cau_hinh and "L" not in da_du and not args.mo_hinh_chon:
        sys.exit("LỖI: cấu hình L cần --mo-hinh-chon (hoặc L.jsonl đã đủ mọi vụ trong thư mục kết quả)")

    llm = OllamaGia(args.num_ctx) if args.gia else Ollama(args.endpoint, args.num_ctx)
    ten_mo_hinh = {"goc": args.mo_hinh_goc, "tach": args.mo_hinh_tach, "chon": args.mo_hinh_chon}
    if any(c in CO_LLM and c not in da_du for c in ds_cau_hinh):
        try:
            co = llm.co_san()
        except (OSError, ValueError) as e:
            sys.exit(f"LỖI: không gọi được Ollama ở {args.endpoint}: {e}")
        thieu = [c for c in ds_cau_hinh if c in CO_LLM and c not in da_du and "*" not in co and ten_mo_hinh[CO_LLM[c]] not in co]
        if thieu:
            if args.tap == "test" or not args.bo_qua_thieu:
                sys.exit(f"LỖI: Ollama chưa có mô hình cho {', '.join(f'{c} ({ten_mo_hinh[CO_LLM[c]]})' for c in thieu)}")
            print(f"BỎ QUA (thiếu mô hình): {', '.join(thieu)}")
            ds_cau_hinh = [c for c in ds_cau_hinh if c not in thieu and not (c in KET_HOP and {"C0", "L"} & set(thieu))]

    idx = emb = None
    if any(c in ("B0", "B1") for c in ds_cau_hinh):
        from src.index.embedder import HashEmbedder, OllamaEmbedder
        from src.index.store import open_index
        idx = open_index(goi / "db" / "chi_muc.sqlite")
        emb = HashEmbedder() if args.gia else OllamaEmbedder(args.model_nhung, args.endpoint)

    print(f"Đo {len(mau)} vụ [{args.tap}] — cấu hình {', '.join(ds_cau_hinh)}; ứng viên {che_do}, K = {k}; num_ctx {args.num_ctx}"
          + (f"; file chốt sha256 {sha_chot[:12]}" if sha_chot else ""))
    ket_qua: dict[str, list[dict]] = {}
    nguong_cat = args.num_ctx - max(NUM_PREDICT.values()) - 16
    for c in ds_cau_hinh:
        if c == "A":
            ket_qua.update(chay_A(mau, che_do))
            continue
        if c in KET_HOP:
            ket_qua[c] = chay_ket_hop(ket_qua["C0"], ket_qua["L"], KET_HOP[c], c)
            with (ra / f"{c}.jsonl").open("w", encoding="utf-8", newline="\n") as f:
                for r in ket_qua[c]:
                    f.write(json.dumps(dict(r, sha_chot=sha_chot) if sha_chot else r, ensure_ascii=False) + "\n")
            print(f"\n[{c}] kết hợp C0 và L ({KET_HOP[c]}): {len(ket_qua[c])} vụ, lùi {sum(r['lui'] for r in ket_qua[c])}")
            continue
        p = ra / f"{c}.jsonl"
        cu = doc_jsonl(p)
        for r in cu:
            if sha_chot and r.get("sha_chot") != sha_chot:
                sys.exit(f"LỖI: {p} có kết quả của cấu hình chốt khác; tập test không được chạy lại với cấu hình khác")
        da = {r["id"] for r in cu}
        model = ten_mo_hinh[CO_LLM[c]]
        khac = sorted({r.get("mo_hinh") for r in cu if r["id"] in ids_mau} - {model})
        if c in da_du:
            model = ", ".join(sorted({r.get("mo_hinh") or "?" for r in cu if r["id"] in ids_mau}))
        elif khac:
            print(f"CẢNH BÁO: {p} có vụ đo bằng mô hình khác ({', '.join(map(str, khac))}); chỉ chạy tiếp các vụ còn thiếu bằng {model}")
        print(f"\n[{c}] {model}: {len(da)} vụ đã có, còn {len(mau) - len([x for x in mau if x['id'] in da])}")
        with p.open("a", encoding="utf-8", newline="\n") as f:
            for i, x in enumerate(mau, 1):
                if x["id"] in da:
                    continue
                if c in ("B0", "B1"):
                    from src.index.search import gop_theo_dieu, tim
                    from src.index.tim_du import so_dieu
                    r = hoi_lap(llm, model, tin_nhan_tach(x["su_viec"], "thuan"), SCHEMA_TACH, NUM_PREDICT["tach"], doc_hanh_vi)
                    hv = r.pop("ket_qua") or [x["su_viec"]]               # hỏng cả 3 lần: coi như không tách (như tach_mot)
                    xh = []
                    for h in hv:
                        kq = tim(idx, h, embedder=emb, ngay=x["ngay_tra_cuu"], k=2000, che_do="vector", n_ung_vien=300)
                        xh.append([so_dieu(d.dieu) for d in gop_theo_dieu(kq.hits, 10_000)][:10])
                    hien = [d for d in dict.fromkeys(d for ds in xh for d in ds[:args.m]) if cd.la_dieu_toi_pham(d)]
                    ban_ghi = {"id": x["id"], "cau_hinh": c, "mo_hinh": model, "dieu": x["dieu"], "hanh_vi": hv, "xep_hang_hanh_vi": xh,
                            "hien_thi": hien, "cham": cd.cham_chon(x["dieu"], hien), **r}
                else:
                    uv, _ = cd.dung_ung_vien(x["xep_hang"][che_do], k)
                    r = hoi_lap(llm, model, cd.dung_tin_nhan(x["su_viec"], uv, x["tieu_de"]), cd.schema_chon(uv), NUM_PREDICT["chon"],
                                lambda t, uv=uv: cd.doc_chon(t, uv))
                    chon = r.pop("ket_qua") or []
                    ban_ghi = {"id": x["id"], "cau_hinh": c, "mo_hinh": model, "dieu": x["dieu"], "ung_vien": uv, "hien_thi": chon,
                            "cham": cd.cham_chon(x["dieu"], chon), **r}
                ban_ghi["co_the_bi_cat"] = (ban_ghi.get("prompt_eval_count") or 0) >= nguong_cat
                if sha_chot:
                    ban_ghi["sha_chot"] = sha_chot
                f.write(json.dumps(ban_ghi, ensure_ascii=False) + "\n")
                f.flush()
                print(f"  [{i}/{len(mau)}] {x['id']}: hiển thị {','.join(ban_ghi['hien_thi']) or '-'} | đáp án {','.join(x['dieu'])} | "
                      f"{ban_ghi['giay']}s, prompt {ban_ghi.get('prompt_eval_count')}{'  !! ' + ban_ghi['loi'] if ban_ghi['loi'] else ''}", flush=True)
        ket_qua[c] = [r for r in doc_jsonl(p) if r["id"] in ids_mau]

    # ---- báo cáo ---------------------------------------------------------------------------------------------------
    theo_id = {x["id"]: x for x in mau}
    dong = [f"# Đo bộ bản án [{args.tap}] — {len(mau)} vụ", "",
            f"Ứng viên: {che_do}, K = {k}; num_ctx {args.num_ctx}; mô hình gốc {args.mo_hinh_goc}, tách {args.mo_hinh_tach}, chọn {args.mo_hinh_chon}"
            + (f"; file chốt sha256 {sha_chot}" if sha_chot else "") + ("  (GIẢ: số không có giá trị)" if args.gia else ""), "",
            "| cấu hình | tìm đủ | bao phủ | chính xác | khớp đúng | Điều hiển thị TB | số hành vi TB | đúng số hành vi | lỗi | có thể bị cắt | giây/vụ |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    tom = {c: tong_hop(v) for c, v in ket_qua.items() if v}
    dong += [dong_bang(c, tb) for c, tb in tom.items()]
    dong += ["", "tìm đủ = mọi Điều tòa áp dụng đều được hiển thị. khớp đúng = tập Điều hiển thị trùng đúng tập của tòa. "
             "Đọc «tìm đủ» cùng «Điều hiển thị TB»: hiển thị nhiều hơn thì dễ tìm đủ hơn."]
    if any(c in KET_HOP for c in tom):
        dong += ["", "HOP = C0 ∪ L. LOC = C0 ∩ L, giao rỗng thì giữ L. LOC0 = C0 ∩ L, giao rỗng thì giữ C0. "
                 "Không gọi lại mô hình: tính từ C0.jsonl và L.jsonl. Số vụ phải lùi (giao rỗng): "
                 + ", ".join(f"{c} {tb['lui']}/{tb['n']}" for c, tb in tom.items() if c in KET_HOP and c != "HOP") + "."]
    dong += ["", "## Ứng viên: phần vụ có ĐỦ đáp án trong top K (ngoặc: phần Điều đáp án trong top K)", ""]
    bang = cd.bang_recall(mau)
    ks = sorted(next(iter(bang.values())))
    dong += ["| chế độ | " + " | ".join(f"K={x}" for x in ks) + " |", "|---|" + "---|" * len(ks)]
    dong += [f"| {c} | " + " | ".join(f"{t[x]['du']:.0%} ({t[x]['recall']:.0%})" for x in ks) + " |" for c, t in bang.items()]
    cap = list(CAP_SO_SANH)
    if chot and chot.get("tot_nhat_cu"):
        cap.append(("L", chot["tot_nhat_cu"], "việc mới có hơn cấu hình cũ tốt nhất (chọn trên 90 vụ train)"))
    cap = [(a, b, y) for a, b, y in cap if a in ket_qua and b in ket_qua]
    if cap:
        dong += ["", "## So sánh cặp (McNemar chính xác trên «tìm đủ»)", "", "| so sánh | trả lời | vụ khác nhau | thắng / thua | p |", "|---|---|---|---|---|"]
        for a, b, y in cap:
            n, at, bt, p = so_cap(ket_qua[a], ket_qua[b])
            dong.append(f"| {a} so với {b} | {y} | {n} | {at} / {bt} | {p:.3f} |")
    nhom = [("Điều chưa gặp ở train", lambda x: x.get("dieu_chua_gap")), ("lời kể còn nhắc tên tội", lambda x: x.get("ten_toi_trong_loi_ke", 0) > 0),
            ("nhiều Điều", lambda x: len(x["dieu"]) > 1), ("sự việc bị cắt", lambda x: x.get("da_cat"))]
    dong += ["", "## Theo nhóm (chỉ mô tả): tìm đủ khi có / không có đặc điểm", "", "| cấu hình | " + " | ".join(t for t, _ in nhom) + " |",
             "|---|" + "---|" * len(nhom)]
    for c, v in ket_qua.items():
        o = []
        for _, f in nhom:
            co = [r for r in v if f(theo_id[r["id"]])]
            khong = [r for r in v if not f(theo_id[r["id"]])]
            o.append(" / ".join(f"{int(sum(r['cham']['tim_du'] for r in g))}/{len(g)}" for g in (co, khong)))
        dong.append(f"| {c} | " + " | ".join(o) + " |")
    txt = "\n".join(dong) + "\n"
    (ra / "bao_cao.md").write_text(txt, encoding="utf-8", newline="\n")
    (ra / "tom_tat.json").write_text(json.dumps({"tap": args.tap, "k": k, "che_do_uv": che_do, "num_ctx": args.num_ctx, "sha_chot": sha_chot,
                                                 "tom_tat": tom, "recall": {c: {str(x): t[x] for x in t} for c, t in bang.items()}},
                                                ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("\n" + txt)
    print(f"Đã ghi {ra / 'bao_cao.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
