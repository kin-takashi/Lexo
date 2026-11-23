"""Sinh 3 notebook Kaggle (kaggle/lexo_do_ban_an.ipynb, lexo_hoc_chon_dieu.ipynb, lexo_gop_gguf.ipynb) từ mã nguồn ở đây.

  python scripts/tao_notebook_kaggle.py        # ghi đè 3 file .ipynb trong kaggle/

Sửa notebook ở file này rồi sinh lại, đừng sửa tay file .ipynb (mất đồng bộ). scripts/dong_goi_kaggle.py chép các file .ipynb và
.md trong kaggle/ ra cạnh hai gói dữ liệu.
"""
import json
import sys
from pathlib import Path


def _dong(s: str) -> list[str]:
    s = s.strip("\n")
    d = s.split("\n")
    return [x + "\n" for x in d[:-1]] + [d[-1]]


def md(s):
    return {"cell_type": "markdown", "metadata": {}, "source": _dong(s)}


def code(s):
    return {"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [], "source": _dong(s)}


def nb(cells, gpu: bool):
    for i, c in enumerate(cells):
        c["id"] = f"o{i:02d}"
    meta = {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python"},
            "kaggle": {"accelerator": "nvidiaTeslaT4" if gpu else "none", "isGpuEnabled": gpu, "isInternetEnabled": True,
                       "language": "python", "sourceType": "notebook", "dataSources": []}}
    return {"cells": cells, "metadata": meta, "nbformat": 4, "nbformat_minor": 5}


CHUNG = r'''
# ---- Hàm dùng chung (không cần sửa) ----
import collections, fnmatch, hashlib, json, math, os, re, shutil, subprocess, sys, time, zipfile
from collections import Counter
from pathlib import Path

INPUT, WORK = Path("/kaggle/input"), Path("/kaggle/working")
TAM = Path("/kaggle/tmp") if Path("/kaggle/tmp").is_dir() else Path("/tmp")   # thư mục tạm lớn, không vào Output


def sha256(p, khoi=1 << 24):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(khoi), b""):
            h.update(b)
    return h.hexdigest()


def tim(mau, goc=INPUT):
    """Mọi file có tên khớp mẫu (không phân biệt hoa thường) dưới goc, đi theo cả symlink."""
    ra = []
    for d, _, ten in os.walk(goc, followlinks=True):
        ra += [Path(d) / t for t in ten if fnmatch.fnmatch(t.lower(), mau.lower())]
    return sorted(ra)


def tim_goi(dau, mau_zip):
    """Thư mục gói (chứa file đánh dấu). Kaggle thường tự giải nén zip; nếu không thì giải nén vào thư mục tạm."""
    thay = tim(dau)
    if not thay:
        for z in tim(mau_zip):
            dich = TAM / "giai_nen" / z.stem
            with zipfile.ZipFile(z) as f:
                f.extractall(dich)
            thay = tim(dau, dich)
            break
    if len(thay) != 1:
        raise SystemExit(f"Cần đúng một gói có {dau} trong /kaggle/input, thấy {len(thay)}: {thay}")
    return thay[0].parent


def kiem_sha256sums(goc):
    r = subprocess.run(["sha256sum", "-c", "--quiet", "SHA256SUMS"], cwd=goc, capture_output=True, text=True)
    if r.returncode:
        raise SystemExit("SHA256SUMS SAI, dừng lại (tải lại gói):\n" + r.stdout[-3000:] + r.stderr[-1000:])
    n = len([x for x in (goc / "SHA256SUMS").read_text(encoding="utf-8").splitlines() if x.strip()])
    print(f"SHA256SUMS: OK cả {n} file ({goc})")


def chay(lenh, cwd=None, env=None, duoi=None):
    """Chạy lệnh và in đầu ra từng dòng (đầu ra của subprocess thường không hiện trong ô). duoi=N: chỉ in N dòng cuối.
    Lệnh lỗi thì dừng ô."""
    lenh = [str(x) for x in lenh]
    print("$", " ".join(lenh), flush=True)
    p = subprocess.Popen(lenh, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         encoding="utf-8", errors="replace")
    cuoi = collections.deque(maxlen=duoi or 1)
    for dong in p.stdout:
        if duoi:
            cuoi.append(dong)
        else:
            print(dong, end="", flush=True)
    if duoi:
        print("".join(cuoi), end="", flush=True)
    if p.wait():
        raise RuntimeError(f"lệnh thoát mã {p.returncode}: {' '.join(lenh[:4])} …")


def doc_jsonl(p):
    p = Path(p)
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []
'''

# ======================================================================================================================
# 1. Notebook ĐO
# ======================================================================================================================

DO = [md(r'''
# Lexo — đo bộ bản án (Vòng 1, cổng G3/G4 của LoRA chọn Điều, lượt test)

Notebook này chỉ chạy LLM qua Ollama. Sự việc đã cắt, ứng viên đã xếp hạng, mã nguồn và chỉ mục đều nằm sẵn trong gói đo
(sinh trên laptop bằng `scripts/dong_goi_kaggle.py`), nên vector bge-m3 của ứng viên không lệch giữa laptop và Kaggle.
Không cần `lexo_eval_colab.zip` cũ.

**Cài đặt notebook:** Accelerator **GPU T4** (một hay hai đều được), **Internet On**.

**Input (Add Input):**

| Gắn | Khi nào | Notebook tìm theo |
|---|---|---|
| Dataset private từ `lexo_do_ban_an.zip` | luôn | file `LEXO_DO_BAN_AN.md` |
| Dataset có GGUF n368 | để chạy B1 | tên file chứa `n368` và `q4_k_m`, đuôi `.gguf` |
| Output của notebook `lexo_gop_gguf` | sau Vòng 2 | tên file chứa `chon-dieu-v1` và `q4_k_m`, đuôi `.gguf` |

**Chạy:** sửa ô «Việc cần chạy» rồi Run All. Lượt dài (Vòng 1 ước 2–3 giờ, lượt test) nên dùng **Save Version → Save & Run All**
để chạy cả khi đóng trình duyệt. Mỗi phần ghi `ket_qua_<tên>.zip` vào Output: tải các zip đó về `inbox/kaggle_ket_qua/` trên laptop.
Kết quả từng vụ ghi vào `.jsonl` ngay sau mỗi vụ; chạy lại ô trong cùng phiên sẽ làm tiếp các vụ còn thiếu.

**Tập test (99 vụ) chỉ chạy một lần, ở cuối,** sau khi đã chốt cấu hình ở chat gốc. Ô test bị khóa bằng `DA_CHOT = False`.
'''), code(r'''
# ---- Việc cần chạy (sửa ở đây rồi Run All) ----
CHAY_VONG_1 = True        # Vòng 1: A, B0, B1, C0 trên 90 vụ train (hoc + dev)
CHAY_LORA_DEV = False     # sau Vòng 2: cổng G3/G4 của LoRA chọn Điều trên dev (A, C0, L)
CHAY_DOI_K = False        # Vòng 3, C3: đổi K lúc chạy, chỉ trên dev
DOI_K = (10, 30)
CHAY_TEST = False         # lượt test duy nhất: chỉ bật sau khi đã chốt (xem ô cuối)

MO_HINH_N368 = "qwen3-8b-lexo-sach-n368"           # tên trong Ollama (phải chứa "qwen3")
MAU_GGUF_N368 = "*n368*q4_k_m*.gguf"
MO_HINH_LORA = "qwen3-8b-lexo-chon-dieu-v1"
MAU_GGUF_LORA = "*chon-dieu-v1*q4_k_m*.gguf"
OLLAMA_VERSION = "0.40.4"  # như các lần đo dev 34 câu; "" = bản mới nhất. Bản thật được ghi vào moi_truong.json
NUM_CTX = 8192
REVISION_QWEN3 = "b968826d9c46dd6066d109eabc6255188de91218"   # chỉ để đếm token bằng tokenizer, cùng bản lúc học
'''), code(CHUNG), md(r'''
## 1. Gói đo: kiểm SHA256, chép sang `/kaggle/working/lexo`
'''), code(r'''
GOI = tim_goi("LEXO_DO_BAN_AN.md", "lexo_do_ban_an*.zip")
kiem_sha256sums(GOI)
LEXO = WORK / "lexo"
if LEXO.exists():
    if (LEXO / "SHA256SUMS").read_bytes() != (GOI / "SHA256SUMS").read_bytes():
        raise SystemExit(f"{LEXO} là bản của một gói khác: xóa thư mục đó (hoặc mở phiên mới) rồi chạy lại")
    print("Đã có", LEXO, "của cùng gói: giữ nguyên để chạy tiếp")
else:
    shutil.copytree(GOI, LEXO)
CAU_HINH = json.loads((LEXO / "cau_hinh.json").read_text(encoding="utf-8"))
if CAU_HINH.get("gia"):
    raise SystemExit("Gói này dựng bằng vector giả (--gia): không dùng để đo. Đóng gói lại trên laptop, không có --gia.")
DU_LIEU = json.loads((LEXO / "ban_an_do.json").read_text(encoding="utf-8"))
K, CHE_DO = CAU_HINH["ung_vien"]["k"], CAU_HINH["ung_vien"]["che_do"]
print("Vụ theo tập:", dict(Counter(x["tap"] for x in DU_LIEU["mau"])))
print(f"Ứng viên: {CHE_DO}, K = {K}; lời nhắc {CAU_HINH['phien_ban_tin_nhan']}; nhúng {CAU_HINH['mo_hinh_nhung']}")
sys.path.insert(0, str(LEXO))
from src.ban_an import chon_dieu as cd                                # cùng mã đã sinh gói
from src.index.tach_hanh_vi import dung_tin_nhan as tin_nhan_tach
assert cd.HE_THONG_CHON == CAU_HINH["he_thong_chon"]
print(subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], capture_output=True, text=True).stdout)
'''), md(r'''
## 2. Ollama: cài, chạy nền, kéo `qwen3:8b` và `bge-m3`

`OLLAMA_NUM_PARALLEL=1` để mỗi lần gọi có trọn `num_ctx` (bộ nhớ KV không bị chia). Mô hình lưu ở thư mục tạm, không vào Output.
'''), code(r'''
import urllib.request

LOG_OLLAMA = WORK / "ollama_serve.log"
URL = "http://localhost:11434"


def ollama_song():
    try:
        with urllib.request.urlopen(URL + "/api/version", timeout=5) as r:
            return json.loads(r.read())["version"]
    except OSError:
        return None


def mo_hinh_co():
    with urllib.request.urlopen(URL + "/api/tags", timeout=30) as r:
        return {m["name"]: m for m in json.loads(r.read())["models"]}


if not shutil.which("ollama"):
    chay(["bash", "-c", "apt-get -qq update && DEBIAN_FRONTEND=noninteractive apt-get -qq install -y zstd pciutils lshw"], duoi=3)
    chay(["bash", "-c", "curl -fsSL https://ollama.com/install.sh | " + (f"OLLAMA_VERSION={OLLAMA_VERSION} " if OLLAMA_VERSION else "") + "sh"], duoi=5)
if not ollama_song():
    env = dict(os.environ, OLLAMA_MODELS=str(TAM / "ollama_models"), OLLAMA_NUM_PARALLEL="1", OLLAMA_MAX_LOADED_MODELS="2",
               OLLAMA_KEEP_ALIVE="30m")
    subprocess.Popen(["ollama", "serve"], stdout=open(LOG_OLLAMA, "a"), stderr=subprocess.STDOUT, env=env, start_new_session=True)
    for _ in range(90):
        time.sleep(1)
        if ollama_song():
            break
PHIEN_BAN_OLLAMA = ollama_song()
assert PHIEN_BAN_OLLAMA, f"Ollama không chạy: xem {LOG_OLLAMA}"
print("Ollama", PHIEN_BAN_OLLAMA)
for m in ("qwen3:8b", "bge-m3"):
    chay(["ollama", "pull", m], duoi=2)
print(subprocess.run(["ollama", "list"], capture_output=True, text=True).stdout)
'''), md(r'''
## 3. Mô hình từ GGUF: n368 (cho B1) và LoRA chọn Điều (cho L)

Modelfile lấy nguyên khuôn chat và tham số của `qwen3:8b` (`ollama show qwen3:8b --modelfile`), chỉ thay dòng `FROM`, như các lần trước.
'''), code(r'''
GGUF = {}   # tên Ollama -> file, sha256, kích thước


def tao_tu_gguf(ten, mau):
    ds = tim(mau)
    if not ds:
        print(f"Không thấy GGUF khớp {mau!r} trong /kaggle/input: chưa có {ten}")
        return False
    if len(ds) > 1:
        raise SystemExit(f"Nhiều GGUF khớp {mau!r}: {ds}")
    print(f"{ten}: tính sha256 của {ds[0].name} …", flush=True)
    GGUF[ten] = {"file": ds[0].name, "sha256": sha256(ds[0]), "bytes": ds[0].stat().st_size}
    print("  sha256", GGUF[ten]["sha256"])
    if any(t in (ten, ten + ":latest") for t in mo_hinh_co()):
        print(f"  {ten} đã có trong Ollama")
        return True
    mf = subprocess.run(["ollama", "show", "qwen3:8b", "--modelfile"], capture_output=True, text=True, check=True).stdout
    mf, n = re.subn(r"(?m)^FROM .*$", f"FROM {ds[0]}", mf, count=1)
    assert n == 1, "không thấy dòng FROM trong Modelfile của qwen3:8b"
    p = TAM / f"Modelfile_{ten}"
    p.write_text(mf, encoding="utf-8")
    chay(["ollama", "create", ten, "-f", p], duoi=3)
    return True


CO_N368 = tao_tu_gguf(MO_HINH_N368, MAU_GGUF_N368)
CO_LORA = tao_tu_gguf(MO_HINH_LORA, MAU_GGUF_LORA)
'''), md(r'''
## 4. Hàm kiểm kỹ thuật (G3/G4) và đóng gói kết quả

- Số vụ lỗi, có khối think, «có thể bị cắt» (prompt_eval_count sát num_ctx), phải bằng 0.
- Nhật ký Ollama không được có dòng «truncating» (Ollama cắt ngầm khi ngữ cảnh quá nhỏ).
- `prompt_eval_count` so với số token tự đếm bằng tokenizer Qwen3 (cùng revision lúc học). Lệch vài token là do khuôn chat của
  Ollama; lệch lớn thì xem lại Modelfile.
- `ollama ps` phải báo `100% GPU`.
'''), code(r'''
from IPython.display import Markdown, display

try:
    from transformers import AutoTokenizer
    TOK = AutoTokenizer.from_pretrained("Qwen/Qwen3-8B", revision=REVISION_QWEN3)
except Exception as e:                                           # không chặn việc đo nếu không tải được tokenizer
    TOK = None
    print("CHÚ Ý: không tải được tokenizer Qwen3, bỏ phần so số token:", e)
THEO_ID = {x["id"]: x for x in DU_LIEU["mau"]}


def dem_token(c, r):
    x = THEO_ID[r["id"]]
    msgs = tin_nhan_tach(x["su_viec"], "thuan") if c in ("B0", "B1") else cd.dung_tin_nhan(x["su_viec"], r["ung_vien"], x["tieu_de"])
    s = TOK.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False)
    return len(TOK(s, add_special_tokens=False)["input_ids"])


def kiem_log():
    chu = LOG_OLLAMA.read_text(encoding="utf-8", errors="replace") if LOG_OLLAMA.exists() else ""
    cat = [d for d in chu.splitlines() if "truncat" in d.lower()]
    (WORK / "ollama_canh_bao.txt").write_text("\n".join(cat) + "\n", encoding="utf-8")
    print(f"Nhật ký Ollama: {len(cat)} dòng báo cắt ngữ cảnh" + (" → KHÔNG ĐẠT (xem ollama_canh_bao.txt)" if cat else " → đạt"))
    return not cat


def kiem_gpu():
    ps = subprocess.run(["ollama", "ps"], capture_output=True, text=True).stdout
    print(ps)
    return "CPU" not in ps


def kiem_ky_thuat(thu_muc, cac_cau_hinh):
    dat = True
    for c in cac_cau_hinh:
        ds = doc_jsonl(Path(thu_muc) / f"{c}.jsonl")
        if not ds:
            print(f"{c}: chưa có kết quả")
            dat = False
            continue
        loi, think, cat = (sum(bool(r.get(t)) for r in ds) for t in ("loi", "co_think", "co_the_bi_cat"))
        dong = f"{c}: {len(ds)} vụ | lỗi {loi} | khối think {think} | có thể bị cắt {cat}"
        if TOK is not None:
            lech = [dem_token(c, r) - r["prompt_eval_count"] for r in ds if r.get("prompt_eval_count") is not None]
            if lech:
                dong += f" | token tự đếm − prompt_eval_count: từ {min(lech)} đến {max(lech)}" + (" (khớp)" if max(map(abs, lech)) <= 8 else " (LỆCH)")
        print(dong)
        for r in ds:
            if r.get("loi"):
                print(f"   {r['id']}: {r['loi']}")
        dat = dat and not (loi or think or cat)
    return dat


def chay_do(*tham_so):
    chay([sys.executable, "-u", "scripts/do_ban_an.py", "--num-ctx", NUM_CTX, *tham_so], cwd=LEXO)


def bao_cao(thu_muc):
    display(Markdown((Path(thu_muc) / "bao_cao.md").read_text(encoding="utf-8")))


def ghi_moi_truong():
    co = mo_hinh_co()
    mt = {"ollama": PHIEN_BAN_OLLAMA, "num_ctx": NUM_CTX,
          "gpu": subprocess.run(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"], capture_output=True,
                                text=True).stdout.strip().splitlines(),
          "mo_hinh": {t: {"digest": m.get("digest"), "size": m.get("size")} for t, m in co.items()}, "gguf": GGUF,
          "goi_do": {"sha256_SHA256SUMS": sha256(LEXO / "SHA256SUMS"), "ung_vien": CAU_HINH["ung_vien"],
                     "phien_ban_tin_nhan": CAU_HINH["phien_ban_tin_nhan"]},
          "luc": time.strftime("%Y-%m-%d %H:%M:%S")}
    (WORK / "moi_truong.json").write_text(json.dumps(mt, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return mt


def dong_goi(nhan, cac):
    z = WORK / f"ket_qua_{nhan}.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as f:
        for p in [*map(Path, cac), WORK / "moi_truong.json", WORK / "ollama_canh_bao.txt"]:
            if p.is_dir():
                for q in sorted(p.rglob("*")):
                    if q.is_file():
                        f.write(q, q.relative_to(p.parent))
            elif p.exists():
                f.write(p, p.name)
    print(f"Đã ghi {z} ({z.stat().st_size / 1e6:.1f} MB): tải về inbox/kaggle_ket_qua/")
'''), md(r'''
## 5. Vòng 1: A, B0, B1, C0 trên 90 vụ train

Chạy thử 3 vụ trước (thư mục riêng `thu_vong_1`, không lẫn vào kết quả chính); có lỗi kỹ thuật thì dừng trước lượt dài.
Cách đọc bảng (ghi trước khi có số) nằm trong tài liệu kế hoạch, mục Vòng 1: quyết định sang Vòng 2 làm ở chat gốc.
'''), code(r'''
if CHAY_VONG_1:
    ghi_moi_truong()
    cau_hinh = ["A", "B0"] + (["B1"] if CO_N368 else []) + ["C0"]
    if not CO_N368:
        print("CHÚ Ý: không có GGUF n368 → bỏ B1 (so sánh B1 với B0 sẽ thiếu)")
    llm = [c for c in cau_hinh if c != "A"]
    train90 = [x for x in DU_LIEU["mau"] if x["tap"] in ("hoc", "dev")]
    ba = list(dict.fromkeys([max(train90, key=lambda x: x["so_tu_goc"])["id"],
                             next(x["id"] for x in train90 if len(x["dieu"]) > 1), train90[0]["id"]]))
    THU1 = WORK / "thu_vong_1"
    chay_do("--tap", "train90", "--cau-hinh", ",".join(llm), "--chi-id", ",".join(ba), "--ra", THU1)
    ok = kiem_gpu() & kiem_ky_thuat(THU1, llm) & kiem_log()
    if not ok:
        dong_goi("thu_vong_1", [THU1])
        raise SystemExit("Chạy thử 3 vụ chưa sạch về kỹ thuật: dừng trước lượt dài, mang ket_qua_thu_vong_1.zip về chat gốc")
    chay_do("--tap", "train90", "--cau-hinh", ",".join(cau_hinh))
    RA1 = LEXO / "ket_qua" / "train90"
    kiem_ky_thuat(RA1, llm)
    kiem_log()
    bao_cao(RA1)
    dong_goi("train90", [RA1, THU1])
'''), md(r'''
## 6. Sau Vòng 2: G3 và G4 của LoRA chọn Điều trên dev

Cần gắn output của `lexo_gop_gguf`. G3: 3 vụ dev, mô hình nằm trên GPU, `num_ctx` 8192, không lỗi, số token khớp.
G4: cả các vụ dev chạy không lỗi. Điểm tìm đủ / khớp đúng trên dev chỉ để xem, **không dùng để chọn mô hình**.
'''), code(r'''
if CHAY_LORA_DEV:
    if not CO_LORA:
        raise SystemExit(f"Chưa gắn GGUF khớp {MAU_GGUF_LORA} (output của notebook lexo_gop_gguf)")
    ghi_moi_truong()
    dev = sorted(x["id"] for x in DU_LIEU["mau"] if x["tap"] == "dev")
    THU3 = WORK / f"thu_g3_{MO_HINH_LORA}"
    chay_do("--tap", "dev", "--cau-hinh", "C0,L", "--mo-hinh-chon", MO_HINH_LORA, "--chi-id", ",".join(dev[:3]), "--ra", THU3)
    g3 = kiem_gpu() & kiem_ky_thuat(THU3, ["C0", "L"]) & kiem_log()
    print("G3:", "ĐẠT" if g3 else "KHÔNG ĐẠT")
    if not g3:
        dong_goi(f"g3_{MO_HINH_LORA}", [THU3])
        raise SystemExit("G3 không đạt: dừng, mang zip về chat gốc")
    RA2 = LEXO / "ket_qua" / f"dev_{MO_HINH_LORA}"
    chay_do("--tap", "dev", "--cau-hinh", "A,C0,L", "--mo-hinh-chon", MO_HINH_LORA, "--ra", RA2)
    g4 = kiem_ky_thuat(RA2, ["C0", "L"]) & kiem_log()
    print(f"G4 ({len(dev)} vụ dev):", "ĐẠT" if g4 else "KHÔNG ĐẠT")
    bao_cao(RA2)
    dong_goi(f"dev_{MO_HINH_LORA}", [RA2, THU3])
'''), md(r'''
## 7. Vòng 3, C3 (tùy chọn): đổi K lúc chạy, chỉ trên dev

Không học lại. Phải xong trước lượt test.
'''), code(r'''
if CHAY_DOI_K:
    ghi_moi_truong()
    cac = []
    for k in DOI_K:
        ra = LEXO / "ket_qua" / f"dev_k{k}"
        chay_do("--tap", "dev", "--cau-hinh", "A,C0" + (",L" if CO_LORA else ""), *(["--mo-hinh-chon", MO_HINH_LORA] if CO_LORA else []),
                "--k", k, "--ra", ra)
        kiem_ky_thuat(ra, ["C0"] + (["L"] if CO_LORA else []))
        bao_cao(ra)
        cac.append(ra)
    kiem_log()
    dong_goi("dev_doi_k", cac)
'''), md(r'''
## 8. Lượt test (99 vụ): một lần duy nhất

Chỉ làm khi: Vòng 2 (và Vòng 3 nếu làm) đã xong, cấu hình đã chốt ở chat gốc dựa trên 90 vụ train, dev và val loss.
Điền `CHOT_CHON`, đặt `DA_CHOT = True` và `CHAY_TEST = True` (tắt các phần khác), rồi **Save Version → Save & Run All**.

Ô này ghi `cau_hinh_chot.json` (mô hình, SHA256 của GGUF, digest trong Ollama, K, chế độ ứng viên, lời nhắc, `num_ctx`,
phiên bản Ollama) rồi gọi `do_ban_an.py --tap test --da-chot --chot`. Script lấy mọi tham số từ file chốt, ghi sha256 của file
vào từng dòng kết quả và từ chối chạy tiếp nếu file chốt khác. Sau lượt test: chép bảng số tổng vào tài liệu trước, rồi mới xem từng vụ.
'''), code(r'''
DA_CHOT = False
CHOT_CHON = {
    "cau_hinh": ["A", "B0", "B1", "C0", "L"],   # mọi cấu hình trong cùng một lượt
    "mo_hinh_goc": "qwen3:8b",
    "mo_hinh_tach": MO_HINH_N368,
    "mo_hinh_chon": MO_HINH_LORA,
    "k": K,                                     # K đã chọn trên 90 vụ train (hoặc K khác nếu C3 trên dev cho lý do rõ)
    "che_do_uv": CHE_DO,
    "num_ctx": NUM_CTX,
    "tot_nhat_cu": "B1",                        # cấu hình cũ tốt nhất trên 90 vụ train: A3, A5, B0 hoặc B1
}

if CHAY_TEST:
    if not DA_CHOT:
        raise SystemExit("Chưa chốt: điền CHOT_CHON theo quyết định ở chat gốc rồi đặt DA_CHOT = True")
    can = {"B1": CHOT_CHON["mo_hinh_tach"], "L": CHOT_CHON["mo_hinh_chon"]}
    thieu = [m for c, m in can.items() if c in CHOT_CHON["cau_hinh"] and m not in GGUF]
    if thieu:
        raise SystemExit(f"Chưa gắn GGUF cho {thieu}")
    mt = ghi_moi_truong()
    dung = [CHOT_CHON["mo_hinh_goc"]] + [m for c, m in can.items() if c in CHOT_CHON["cau_hinh"]]
    chot = dict(CHOT_CHON, phien_ban_ollama=PHIEN_BAN_OLLAMA, phien_ban_tin_nhan=CAU_HINH["phien_ban_tin_nhan"],
                sha256_he_thong_chon=hashlib.sha256(CAU_HINH["he_thong_chon"].encode("utf-8")).hexdigest(),
                gguf={m: GGUF[m] for m in dung if m in GGUF},
                digest_ollama={m: (mt["mo_hinh"].get(m) or mt["mo_hinh"].get(m + ":latest") or {}).get("digest") for m in dung},
                sha256_ban_an_do=CAU_HINH["sha256"]["ban_an_do.json"])
    F_CHOT = WORK / "cau_hinh_chot.json"
    if F_CHOT.exists():
        if json.loads(F_CHOT.read_text(encoding="utf-8")) != chot:
            raise SystemExit("cau_hinh_chot.json đã có và khác cấu hình này: test chỉ chạy một lần, không chạy lại với cấu hình khác")
    else:
        F_CHOT.write_text(json.dumps(chot, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print("sha256 file chốt:", sha256(F_CHOT))
    chay([sys.executable, "-u", "scripts/do_ban_an.py", "--tap", "test", "--da-chot", "--chot", F_CHOT], cwd=LEXO)
    RAT = LEXO / "ket_qua" / "test"
    kiem_ky_thuat(RAT, [c for c in chot["cau_hinh"] if c != "A"])
    kiem_log()
    bao_cao(RAT)
    dong_goi("test", [RAT, F_CHOT])
''')]

# ======================================================================================================================
# 2. Notebook HỌC
# ======================================================================================================================

HOC = [md(r'''
# Lexo — học LoRA «chọn Điều từ ứng viên» (Vòng 2)

**Cài đặt notebook:** Accelerator **GPU T4** (một hay hai; notebook chỉ dùng GPU 0), **Internet On** (tải Qwen3-8B đúng revision
và cài thư viện đúng bản n368).

**Input:** chỉ Dataset private từ `lexo_hoc_chon_dieu.zip`. **Không gắn gói đo** (`lexo_do_ban_an`): ô 1 dừng nếu thấy nó.

**Cách chạy:**
1. Chạy tương tác với `CHE_DO = "thu"`: G0 (dữ liệu, token), rồi học 2 bước trên 16 mẫu dài nhất để đo VRAM và giây mỗi bước.
2. Ổn thì đặt `CHE_DO = "that"`, rồi **Save Version → Save & Run All** (chạy nền). Sau 10 bước notebook ước tổng thời gian
   và tự dừng nếu quá `GIO_TOI_DA` giờ.
3. Output: `<TEN>/` (adapter đã chọn + `thong_tin.json`), `<TEN>_cac_epoch/` (adapter cuối mỗi epoch), `<TEN>.zip`.
   Gắn output này vào notebook `lexo_gop_gguf`.

**Siêu tham số** giữ như n368; chỉ đổi `max_len` 4096, micro-batch 1 × grad-acc 8 (lô hiệu dụng vẫn 8), gradient checkpointing
(theo tài liệu kế hoạch). Hai thay đổi kỹ thuật không đổi phép tính: logits chỉ tính ở các vị trí trả lời (`logits_to_keep`,
cùng loss chỉ-trên-assistant), và `lm_head` (đóng băng) để fp16 thay vì fp32: dưới autocast fp16 phép nhân của nó vẫn chạy
fp16 như n368. Nếu vẫn hết VRAM: hạ `MAX_LEN` xuống 3072 (phần sự việc tự cắt thêm ở chỗ nối, số mẫu bị cắt ghi vào
`thong_tin.json`); không đổi gì khác.

**Chọn checkpoint:** val loss thấp nhất trong các điểm cuối epoch; chênh dưới 0,01 thì lấy điểm sớm hơn. Không theo điểm dev.

**Vòng 3:** C1 → `DU_LIEU = "train_tong_hop"`, `TEN = "lexo-qwen3-8b-chon-dieu-c1"`. C2 → `SEED = 43` (hoặc 44),
`TEN = "lexo-qwen3-8b-chon-dieu-v1-s43"`.
'''), code(r'''
import os
os.environ.setdefault("CUDA_VISIBLE_DEVICES", "0")                    # Kaggle 2×T4: một GPU, tránh DataParallel
os.environ.setdefault("PYTORCH_CUDA_ALLOC_CONF", "expandable_segments:True")

# ---- Cấu hình (sửa ở đây) ----
CHE_DO = "thu"            # "thu": G0 + học 2 bước trên 16 mẫu dài nhất | "that": học đủ (Save & Run All)
TEN = "lexo-qwen3-8b-chon-dieu-v1"
DU_LIEU = "train"         # "train": vụ bản án học + 368 tổng hợp | "train_tong_hop": chỉ 368 tổng hợp (Vòng 3, C1)
SEED = 42
MO_HINH_GOC, REVISION = "Qwen/Qwen3-8B", "b968826d9c46dd6066d109eabc6255188de91218"
MAX_LEN = 4096
MICRO_BS, GRAD_ACC, EPOCH = 1, 8, 3
LR, WARMUP, SCHEDULER = 2e-4, 0.05, "cosine"
LORA_R, LORA_ALPHA, LORA_DROPOUT = 16, 32, 0.05
GIO_TOI_DA = 9.0          # dự kiến (đo sau 10 bước) quá số giờ này thì dừng và báo, không tự đổi siêu tham số
LM_HEAD_FP16 = True
SO_MAU_G1 = 20
PHIEN_BAN = {"transformers": "5.20.1", "peft": "0.21.2", "bitsandbytes": "0.50.2", "accelerate": "1.15.0"}   # như n368
assert CHE_DO in ("thu", "that") and MICRO_BS == 1
'''), code(CHUNG), md(r'''
## 1. Gói học và G0 (dữ liệu)

Kiểm SHA256SUMS; không có gói đo; không dòng nào trùng mã hay băm sự việc của 99 vụ test (`kiem_giao.json`); train và val
không giao nhau; lời nhắc hệ thống khớp từng ký tự; đáp án luôn nằm trong ứng viên.
'''), code(r'''
cam = tim("LEXO_DO_BAN_AN.md") + tim("ban_an_do.json") + tim("lexo_do_ban_an*.zip")
if cam:
    raise SystemExit(f"Gói ĐO đang gắn vào notebook học ({cam[0]}): Remove input rồi chạy lại. Notebook học chỉ nhận gói học.")
GOI = tim_goi("LEXO_HOC_CHON_DIEU.md", "lexo_hoc_chon_dieu*.zip")
kiem_sha256sums(GOI)
TT = json.loads((GOI / "thong_tin_du_lieu.json").read_text(encoding="utf-8"))
if TT.get("gia"):
    raise SystemExit("Gói dựng bằng vector giả (--gia): không học trên gói này")
KG = json.loads((GOI / "kiem_giao.json").read_text(encoding="utf-8"))
F_TRAIN, F_VAL = GOI / f"sft_chon_{DU_LIEU}.jsonl", GOI / "sft_chon_val.jsonl"
TRAIN, VAL = doc_jsonl(F_TRAIN), doc_jsonl(F_VAL)
DAU_USER, TACH = "Sự việc:\n", "\n\nĐiều ứng viên:\n"


def tach_user(msgs):
    u = msgs[1]["content"]
    if not u.startswith(DAU_USER) or TACH not in u:
        raise ValueError("nội dung user không đúng dạng «Sự việc: … Điều ứng viên: …»")
    i = u.rindex(TACH)
    return u[len(DAU_USER):i], u[i + len(TACH):]


def ung_vien(msgs):
    return [re.match(r"Điều (\d+[a-z]?)\.", d).group(1) for d in tach_user(msgs)[1].split("\n")]


ma_test, bam_test = set(KG["ma_test"]), set(KG["sha256_su_viec_test"])
loi = []
for tap, ds in (("train", TRAIN), ("val", VAL)):
    for d in ds:
        m = d["messages"]
        if [x["role"] for x in m] != ["system", "user", "assistant"]:
            loi.append(f"{tap} {d['id']}: vai {[x['role'] for x in m]}")
            continue
        if m[0]["content"] != TT["he_thong_chon"]:
            loi.append(f"{tap} {d['id']}: lời nhắc hệ thống khác thong_tin_du_lieu.json")
        su, _ = tach_user(m)
        if d["id"] in ma_test or hashlib.sha256(su.encode("utf-8")).hexdigest() in bam_test:
            loi.append(f"{tap} {d['id']}: TRÙNG VỤ TEST")
        if not set(json.loads(m[2]["content"])["dieu"]) <= set(ung_vien(m)):
            loi.append(f"{tap} {d['id']}: đáp án ngoài ứng viên")
if {d["id"] for d in TRAIN} & {d["id"] for d in VAL}:
    loi.append("train và val có id chung")
if loi:
    raise SystemExit("G0 (dữ liệu) KHÔNG ĐẠT:\n" + "\n".join(loi[:20]))
print(f"G0 dữ liệu: đạt. train {len(TRAIN)} dòng {dict(Counter(d['nguon'] for d in TRAIN))}, "
      f"val {len(VAL)} dòng {dict(Counter(d['nguon'] for d in VAL))}")
print(f"Ứng viên {TT['ung_vien']['che_do']}, K = {TT['ung_vien']['k']}; đáp án đã chèn: {TT['chen']}; lời nhắc {TT['phien_ban_tin_nhan']}")
'''), md(r'''
## 2. Thư viện (đúng bản n368)
'''), code(r'''
chay([sys.executable, "-m", "pip", "install", "-q", *[f"{k}=={v}" for k, v in PHIEN_BAN.items()]], duoi=5)
import platform
import accelerate, bitsandbytes, peft, torch, transformers
BAN = {"python": platform.python_version(), "torch": torch.__version__, "cuda": torch.version.cuda,
       "transformers": transformers.__version__, "peft": peft.__version__, "bitsandbytes": bitsandbytes.__version__,
       "accelerate": accelerate.__version__}
print(BAN)
assert torch.cuda.is_available(), "Chưa bật GPU (Settings → Accelerator → GPU T4)"
GPU = torch.cuda.get_device_name(0)
VRAM_TONG = torch.cuda.get_device_properties(0).total_memory / 2**30
print(f"{GPU}, {VRAM_TONG:.1f} GB")
lech = {k: (BAN[k], v) for k, v in PHIEN_BAN.items() if BAN[k] != v}
if lech:
    print("CHÚ Ý: khác bản đã ghim (đang dùng, ghim):", lech)
'''), md(r'''
## 3. Mô hình gốc đúng revision, tokenizer, đếm token (G0)

Chuỗi học = lời nhắc (`add_generation_prompt=True, enable_thinking=False`, kết thúc bằng khối think rỗng) + phần trả lời
`{"dieu": [...]}<|im_end|>`. Hai phần được mã hóa riêng, giống lúc chạy: Ollama mã hóa lời nhắc rồi mô hình sinh tiếp.
Loss chỉ trên phần trả lời. Mẫu nào quá `MAX_LEN` thì cắt bớt sự việc ở chỗ nối đầu/cuối (giữ dấu […]); phần trả lời không bao giờ bị cắt.
'''), code(r'''
from huggingface_hub import snapshot_download
from transformers import AutoTokenizer

GOC_DIR = TAM / "qwen3-8b"
snapshot_download(MO_HINH_GOC, revision=REVISION, local_dir=GOC_DIR, allow_patterns=["*.json", "*.safetensors", "*.txt"])
TOK = AutoTokenizer.from_pretrained(GOC_DIR)
KET = "<|im_end|>"
DAU_LUOC = "\n[…]\n"


def chuoi(msgs):
    p = TOK.apply_chat_template(msgs[:2], tokenize=False, add_generation_prompt=True, enable_thinking=False)
    full = TOK.apply_chat_template(msgs, tokenize=False, enable_thinking=False)
    c = msgs[2]["content"] + KET
    if not (p.endswith("<think>\n\n</think>\n\n") and full.startswith(p) and full[len(p):].rstrip("\n") == c):
        raise SystemExit("Khuôn chat của tokenizer khác dự kiến (Qwen3, enable_thinking=False):\n" + repr(full[-400:]))
    return p, c


def ids(s):
    return TOK(s, add_special_tokens=False)["input_ids"]


def bot_giua(su, n):
    """Bỏ n từ ở chỗ nối đầu/cuối của sự việc (cuối phần đầu trước, rồi đầu phần cuối), giữ ít nhất 50 từ mỗi phía và dấu […]."""
    if DAU_LUOC in su:
        dau, cuoi = su.split(DAU_LUOC, 1)
        a, b = dau.split(" "), cuoi.split(" ")
    else:
        tu = su.split(" ")
        a, b = tu[:int(0.7 * len(tu))], tu[int(0.7 * len(tu)):]
    bo_a = min(n, max(0, len(a) - 50))
    bo_b = min(n - bo_a, max(0, len(b) - 50))
    if bo_a + bo_b == 0:
        raise ValueError("sự việc đã quá ngắn, không cắt thêm được")
    return " ".join(a[:len(a) - bo_a]) + DAU_LUOC + " ".join(b[bo_b:])


def ma_hoa(d):
    msgs = d["messages"]
    p, c = chuoi(msgs)
    ip, ic = ids(p), ids(c)
    n_goc, bot = len(ip) + len(ic), 0
    while len(ip) + len(ic) > MAX_LEN:
        su, uv = tach_user(msgs)
        thua = len(ip) + len(ic) - MAX_LEN + 8
        try:
            su = bot_giua(su, thua)
        except ValueError:
            raise SystemExit(f"{d['id']}: vẫn quá MAX_LEN dù sự việc chỉ còn {len(su.split())} từ (danh sách ứng viên quá dài?)")
        msgs = [msgs[0], {"role": "user", "content": DAU_USER + su + TACH + uv}, msgs[2]]
        p, c = chuoi(msgs)
        ip, ic = ids(p), ids(c)
        bot += thua
    return {"id": d["id"], "nguon": d["nguon"], "ip": ip, "ic": ic, "n_goc": n_goc, "n_prompt_goc": n_goc - len(ic), "bot_tu": bot}


MH_TRAIN, MH_VAL = [ma_hoa(d) for d in TRAIN], [ma_hoa(d) for d in VAL]


def thong_ke(ds):
    n = [x["n_goc"] for x in ds]
    return {"toi_da_truoc_cat": max(n), "trung_binh": round(sum(n) / len(n), 1), "vuot_max_len": sum(v > MAX_LEN for v in n),
            "so_mau_bi_cat": sum(x["bot_tu"] > 0 for x in ds), "so_tu_da_bo": sum(x["bot_tu"] for x in ds),
            "so_tra_loi_bi_cat": 0, "tra_loi_dai_nhat": max(len(x["ic"]) for x in ds),
            "tong_token_sau_cat": sum(len(x["ip"]) + len(x["ic"]) for x in ds),
            "prompt_dai_nhat_khi_chay": max(x["n_prompt_goc"] for x in ds)}


TOKEN = {"train": thong_ke(MH_TRAIN), "val": thong_ke(MH_VAL)}
assert all(len(x["ip"]) + len(x["ic"]) <= MAX_LEN for x in MH_TRAIN + MH_VAL)
for t, v in TOKEN.items():
    print(t, v)
print(f"G0 token: 0 câu trả lời bị cắt; {TOKEN['train']['so_mau_bi_cat']} mẫu train và {TOKEN['val']['so_mau_bi_cat']} mẫu val "
      f"bị cắt bớt sự việc để vừa {MAX_LEN} token. Lời nhắc dài nhất khi chạy (không cắt): "
      f"{max(TOKEN['train']['prompt_dai_nhat_khi_chay'], TOKEN['val']['prompt_dai_nhat_khi_chay'])} token (num_ctx Ollama 8192).")
'''), md(r'''
## 4. Nạp mô hình 4-bit và gắn LoRA
'''), code(r'''
from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
from transformers import AutoModelForCausalLM, BitsAndBytesConfig, Trainer, TrainerCallback, TrainingArguments, set_seed

set_seed(SEED)
bnb = BitsAndBytesConfig(load_in_4bit=True, bnb_4bit_quant_type="nf4", bnb_4bit_use_double_quant=True,
                         bnb_4bit_compute_dtype=torch.float16)
model = AutoModelForCausalLM.from_pretrained(GOC_DIR, quantization_config=bnb, dtype=torch.float16, device_map={"": 0})
model.config.use_cache = False
model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True, gradient_checkpointing_kwargs={"use_reentrant": False})
if LM_HEAD_FP16 and not getattr(model.config, "tie_word_embeddings", False):
    model.get_output_embeddings().to(torch.float16)            # prepare_… đưa lên fp32; lớp này đóng băng, autocast vẫn nhân fp16
model = get_peft_model(model, LoraConfig(r=LORA_R, lora_alpha=LORA_ALPHA, lora_dropout=LORA_DROPOUT, target_modules="all-linear",
                                         bias="none", task_type="CAUSAL_LM"))
model.print_trainable_parameters()
print(f"VRAM sau khi nạp: {torch.cuda.memory_allocated() / 2**30:.2f} GB")
'''), md(r'''
## 5. Học

`thu`: 2 bước trên 16 mẫu dài nhất + một lần đo val trên 2 mẫu val dài nhất, in VRAM đỉnh và giây mỗi bước rồi dừng.
`that`: đo val lúc bắt đầu (bước 0), giữa và cuối mỗi epoch; lưu adapter cuối mỗi epoch vào thư mục tạm.
'''), code(r'''
class Tap(torch.utils.data.Dataset):
    def __init__(self, ds):
        self.ds = ds

    def __len__(self):
        return len(self.ds)

    def __getitem__(self, i):
        x = self.ds[i]
        return {"input_ids": x["ip"] + x["ic"], "labels": [-100] * len(x["ip"]) + x["ic"]}


def gom(lo):
    assert len(lo) == 1, "micro-batch phải là 1: phần trả lời luôn ở cuối chuỗi, không đệm"
    ii, lab = torch.tensor([lo[0]["input_ids"]]), torch.tensor([lo[0]["labels"]])
    return {"input_ids": ii, "attention_mask": torch.ones_like(ii), "labels": lab}


class TrainerTraLoi(Trainer):
    """Loss chỉ trên phần trả lời như n368, nhưng chỉ tính logits ở các vị trí đó (logits_to_keep): tránh tensor logits
    4096 × 152k trên T4. Cách chia như mặc định của transformers: tổng loss token / số token trả lời của cả lô hiệu dụng."""
    so_token = 0

    def compute_loss(self, model, inputs, return_outputs=False, num_items_in_batch=None):
        lab = inputs["labels"]
        s = int((lab[0] != -100).nonzero()[0])
        m = lab.shape[1] - s
        out = model(input_ids=inputs["input_ids"], attention_mask=inputs["attention_mask"], logits_to_keep=m + 1, use_cache=False)
        logits = out.logits[:, :-1, :].float()
        tong = torch.nn.functional.cross_entropy(logits.reshape(-1, logits.size(-1)), lab[:, s:].reshape(-1).to(logits.device),
                                                 reduction="sum")
        loss = tong / (num_items_in_batch if num_items_in_batch is not None else m)
        if model.training:
            TrainerTraLoi.so_token += lab.shape[1]
        return (loss, out) if return_outputs else loss


class GiuaEpoch(TrainerCallback):
    """Đo val thêm một lần ở giữa mỗi epoch (cuối epoch đã có eval_strategy="epoch")."""
    def __init__(self):
        self.da = set()

    def on_step_end(self, args, state, control, **kw):
        moc = int(state.epoch * 2 + 1e-9)
        if moc % 2 == 1 and moc not in self.da:
            self.da.add(moc)
            control.should_evaluate = True


class GioiHanGio(TrainerCallback):
    """Sau 10 bước: ước tổng giờ theo số token đã học (val tính 1/3 vì chỉ chạy xuôi); quá GIO_TOI_DA thì dừng.
    Đã chạy quá GIO_TOI_DA + 1,5 giờ thì cũng dừng, để kịp lưu trước giới hạn 12 giờ của Kaggle."""
    def __init__(self, token_quy_doi):
        self.token_quy_doi, self.t0, self.du_kien_gio, self.dung = token_quy_doi, None, None, None

    def on_train_begin(self, args, state, control, **kw):
        self.t0 = time.time()

    def on_step_end(self, args, state, control, **kw):
        da = time.time() - self.t0
        if state.global_step == 10:
            self.du_kien_gio = da / max(TrainerTraLoi.so_token, 1) * self.token_quy_doi / 3600
            print(f"\n[10 bước] {da / 10:.1f} s/bước; dự kiến cả lượt ≈ {self.du_kien_gio:.2f} giờ", flush=True)
            if self.du_kien_gio > GIO_TOI_DA:
                self.dung = f"dự kiến {self.du_kien_gio:.1f} giờ > {GIO_TOI_DA} giờ"
                control.should_training_stop = True
        if da > (GIO_TOI_DA + 1.5) * 3600 and not self.dung:
            self.dung = f"đã chạy {da / 3600:.1f} giờ"
            control.should_training_stop = True


thu = CHE_DO == "thu"
dai = lambda ds, n: sorted(ds, key=lambda x: -(len(x["ip"]) + len(x["ic"])))[:n]
ds_hoc, ds_val = (dai(MH_TRAIN, 2 * GRAD_ACC), dai(MH_VAL, 2)) if thu else (MH_TRAIN, MH_VAL)
BUOC_MOI_EPOCH = math.ceil(len(ds_hoc) / (MICRO_BS * GRAD_ACC))
TONG_BUOC = 2 if thu else EPOCH * BUOC_MOI_EPOCH
WARMUP_STEPS = math.ceil(WARMUP * TONG_BUOC)
CKPT = TAM / f"ckpt_{TEN}"
if CKPT.exists():
    shutil.rmtree(CKPT)
args = TrainingArguments(
    output_dir=str(CKPT), per_device_train_batch_size=MICRO_BS, per_device_eval_batch_size=1, gradient_accumulation_steps=GRAD_ACC,
    num_train_epochs=EPOCH, max_steps=2 if thu else -1, learning_rate=LR, lr_scheduler_type=SCHEDULER, warmup_steps=WARMUP_STEPS,
    fp16=True, logging_steps=1, eval_strategy="no" if thu else "epoch", eval_on_start=not thu,
    save_strategy="no" if thu else "epoch", save_only_model=True, gradient_checkpointing=True,
    gradient_checkpointing_kwargs={"use_reentrant": False}, seed=SEED, report_to="none", remove_unused_columns=False,
    label_names=["labels"], prediction_loss_only=True, dataloader_num_workers=0)
tok_hoc = sum(len(x["ip"]) + len(x["ic"]) for x in ds_hoc)
tok_val = sum(len(x["ip"]) + len(x["ic"]) for x in ds_val)
GH = GioiHanGio(EPOCH * tok_hoc + (2 * EPOCH + 1) * tok_val / 3)
trainer = TrainerTraLoi(model=model, args=args, train_dataset=Tap(ds_hoc), eval_dataset=Tap(ds_val), data_collator=gom,
                        callbacks=[] if thu else [GiuaEpoch(), GH])
print(f"{len(ds_hoc)} mẫu học, {BUOC_MOI_EPOCH} bước/epoch, tổng {TONG_BUOC} bước, warmup {WARMUP_STEPS} bước; optim {args.optim}")
torch.cuda.reset_peak_memory_stats()
t0 = time.time()
trainer.train()
GIAY = time.time() - t0
VRAM_DINH = torch.cuda.max_memory_allocated() / 2**30
LOSS_HOC = [{"buoc": h["step"], "loss": h["loss"], "lr": h.get("learning_rate"), "grad_norm": h.get("grad_norm")}
            for h in trainer.state.log_history if "loss" in h]
if any(not math.isfinite(x["loss"]) for x in LOSS_HOC):
    raise SystemExit(f"Loss NaN/inf: {LOSS_HOC[-5:]}")
print(f"Học {trainer.state.global_step} bước trong {GIAY / 60:.1f} phút ({GIAY / max(trainer.state.global_step, 1):.1f} s/bước); "
      f"VRAM đỉnh {VRAM_DINH:.1f} / {VRAM_TONG:.1f} GB")
if thu:
    ev = trainer.evaluate()
    print("loss học:", [round(x["loss"], 4) for x in LOSS_HOC], "| val loss (2 mẫu dài nhất):", round(ev["eval_loss"], 4))
    print(f"Mẫu dài nhất {len(ds_hoc[0]['ip']) + len(ds_hoc[0]['ic'])} token. Ổn thì đặt CHE_DO = 'that' rồi Save Version → Save & Run All.")
    raise SystemExit("Dừng ở chế độ thử (không phải lỗi).")
'''), md(r'''
## 6. Chọn checkpoint theo val loss
'''), code(r'''
VAL_LOSS = [{"buoc": h["step"], "epoch": round(h["epoch"], 3), "loss": h["eval_loss"]} for h in trainer.state.log_history if "eval_loss" in h]
for x in VAL_LOSS:
    print(f"  bước {x['buoc']:>4} (epoch {x['epoch']:.2f}): val loss {x['loss']:.4f}")
if GH.dung and not list(CKPT.glob("checkpoint-*")):
    (WORK / f"{TEN}_DUNG.json").write_text(json.dumps({"dung": GH.dung, "du_kien_gio": GH.du_kien_gio, "loss_hoc": LOSS_HOC,
                                                        "token": TOKEN, "phien_ban_thu_vien": BAN, "gpu": GPU}, ensure_ascii=False, indent=1))
    raise SystemExit(f"Đã dừng: {GH.dung}. Báo về chat gốc (file {TEN}_DUNG.json), không tự đổi siêu tham số.")
DIEM = []
for c in sorted(CKPT.glob("checkpoint-*"), key=lambda p: int(p.name.split("-")[1])):
    b = int(c.name.split("-")[1])
    l = [x for x in VAL_LOSS if x["buoc"] == b]
    if not l:
        raise SystemExit(f"Không có val loss ở bước {b} (checkpoint {c.name})")
    DIEM.append({"buoc": b, "epoch": l[-1]["epoch"], "val_loss": l[-1]["loss"], "thu_muc": c})
thap = min(x["val_loss"] for x in DIEM)
CHON = next(x for x in DIEM if x["val_loss"] - thap < 0.01)
for x in DIEM:
    print(f"checkpoint bước {x['buoc']} (epoch {x['epoch']:.0f}): val loss {x['val_loss']:.4f}" + ("  ← CHỌN" if x is CHON else ""))
'''), md(r'''
## 7. G1: sinh thử 20 mẫu val

Đạt khi: val loss giảm so với bước 0 và không NaN; JSON hợp lệ 20/20; mọi Điều nằm trong ứng viên; 0 khối think.
Không ghi điểm đúng/sai ở đây (chọn mô hình không dựa vào điểm).
'''), code(r'''
from peft import set_peft_model_state_dict
from safetensors.torch import load_file

kq = set_peft_model_state_dict(model, load_file(CHON["thu_muc"] / "adapter_model.safetensors"))
assert not getattr(kq, "unexpected_keys", []), kq.unexpected_keys[:5]
model.eval()
model.config.use_cache = True
ban_an = sorted((d for d in VAL if d["nguon"] == "ban_an"), key=lambda d: d["id"])
tong_hop = sorted((d for d in VAL if d["nguon"] != "ban_an"), key=lambda d: d["id"])
mau_g1 = ban_an[:SO_MAU_G1 // 2]
mau_g1 += tong_hop[:SO_MAU_G1 - len(mau_g1)]
G1_MAU = []
for d in mau_g1:
    p, _ = chuoi(d["messages"])
    ii = torch.tensor([ids(p)], device="cuda")
    with torch.no_grad(), torch.autocast("cuda", dtype=torch.float16):
        out = model.generate(input_ids=ii, attention_mask=torch.ones_like(ii), max_new_tokens=200, do_sample=False,
                             pad_token_id=TOK.pad_token_id or TOK.eos_token_id)
    chu = TOK.decode(out[0, ii.shape[1]:], skip_special_tokens=False)
    sach = chu.split(KET)[0].strip()
    try:
        obj = json.loads(sach)
    except ValueError:
        obj = None
    uv = set(ung_vien(d["messages"]))
    trong = isinstance(obj, dict) and isinstance(obj.get("dieu"), list) and bool(obj["dieu"]) and all(isinstance(x, str) and x in uv for x in obj["dieu"])
    G1_MAU.append({"id": d["id"], "nguon": d["nguon"], "json_hop_le": isinstance(obj, dict), "trong_ung_vien": trong,
                   "co_think": "<think>" in chu, "co_ket_thuc": KET in chu, "tho": chu[:200]})
G1 = {"so_mau": len(G1_MAU), "json_hop_le": sum(x["json_hop_le"] for x in G1_MAU), "trong_ung_vien": sum(x["trong_ung_vien"] for x in G1_MAU),
      "co_think": sum(x["co_think"] for x in G1_MAU), "co_ket_thuc": sum(x["co_ket_thuc"] for x in G1_MAU),
      "val_loss_buoc_0": VAL_LOSS[0]["loss"] if VAL_LOSS and VAL_LOSS[0]["buoc"] == 0 else None, "val_loss_chon": CHON["val_loss"]}
G1["dat"] = (G1["json_hop_le"] == G1["trong_ung_vien"] == G1["so_mau"] and G1["co_think"] == 0 and G1["val_loss_buoc_0"] is not None
             and CHON["val_loss"] < G1["val_loss_buoc_0"] and all(math.isfinite(x["loss"]) for x in VAL_LOSS))
for x in G1_MAU:
    if not (x["json_hop_le"] and x["trong_ung_vien"]) or x["co_think"]:
        print("  !", x["id"], repr(x["tho"]))
print(f"G1: JSON hợp lệ {G1['json_hop_le']}/{G1['so_mau']}, trong ứng viên {G1['trong_ung_vien']}/{G1['so_mau']}, khối think {G1['co_think']}, "
      f"val loss {G1['val_loss_buoc_0']} → {CHON['val_loss']:.4f} → {'ĐẠT' if G1['dat'] else 'KHÔNG ĐẠT (vẫn lưu để xem; không đưa sang bước gộp)'}")
'''), md(r'''
## 8. Lưu adapter, `thong_tin.json`, zip
'''), code(r'''
RA = WORK / TEN
CAC = WORK / f"{TEN}_cac_epoch"
for p in (RA, CAC):
    if p.exists():
        shutil.rmtree(p)
RA.mkdir()
for f in ("adapter_model.safetensors", "adapter_config.json"):
    shutil.copy2(CHON["thu_muc"] / f, RA / f)
cfg = json.loads((RA / "adapter_config.json").read_text(encoding="utf-8"))
cfg["base_model_name_or_path"], cfg["revision"] = MO_HINH_GOC, REVISION
(RA / "adapter_config.json").write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
for i, x in enumerate(DIEM, 1):
    d = CAC / f"epoch{i}_buoc{x['buoc']}"
    d.mkdir(parents=True)
    for f in ("adapter_model.safetensors", "adapter_config.json"):
        shutil.copy2(x["thu_muc"] / f, d / f)
thong_tin = {
    "ten": TEN, "ten_ollama": "qwen3-8b-lexo-" + TEN.removeprefix("lexo-qwen3-8b-"), "nhiem_vu": "chọn Điều từ K ứng viên",
    "phien_ban_tin_nhan": TT["phien_ban_tin_nhan"], "mo_hinh_goc": MO_HINH_GOC, "revision": REVISION,
    "du_lieu": {"train": F_TRAIN.name, "val": F_VAL.name,
                "sha256": {f.name: sha256(f) for f in (F_TRAIN, F_VAL, GOI / "thong_tin_du_lieu.json", GOI / "kiem_giao.json", GOI / "SHA256SUMS")},
                "so_mau": {"train": len(TRAIN), "val": len(VAL), "train_theo_nguon": dict(Counter(d["nguon"] for d in TRAIN)),
                           "val_theo_nguon": dict(Counter(d["nguon"] for d in VAL))},
                "ung_vien": TT["ung_vien"], "chen": TT["chen"], "dong_co_chen": TT.get("dong_co_chen"), "sha256_nguon": TT["sha256_nguon"]},
    "token": {"max_len": MAX_LEN, **TOKEN, "prompt_val_theo_id": {x["id"]: x["n_prompt_goc"] for x in MH_VAL}},
    "sieu_tham_so": {"luong_tu": "nf4 + double quant, tính fp16", "lora_r": LORA_R, "lora_alpha": LORA_ALPHA, "lora_dropout": LORA_DROPOUT,
                     "target_modules": "all-linear", "lr": LR, "scheduler": SCHEDULER, "warmup": WARMUP, "warmup_steps": WARMUP_STEPS,
                     "epoch": EPOCH, "micro_bs": MICRO_BS, "grad_acc": GRAD_ACC, "seed": SEED, "fp16": True,
                     "gradient_checkpointing": True, "optim": str(args.optim), "loss": "chỉ trên assistant", "enable_thinking": False},
    "ky_thuat": {"logits_to_keep": True, "lm_head_fp16": LM_HEAD_FP16,
                 "chuan_hoa_loss": "tổng loss token trả lời / số token trả lời của lô hiệu dụng (như mặc định transformers)"},
    "so_buoc": trainer.state.global_step, "so_buoc_moi_epoch": BUOC_MOI_EPOCH, "so_giay_hoc": round(GIAY, 1),
    "giay_moi_buoc": round(GIAY / max(trainer.state.global_step, 1), 2), "du_kien_gio_sau_10_buoc": GH.du_kien_gio, "dung_som": GH.dung,
    "val_loss": VAL_LOSS, "train_loss": LOSS_HOC,
    "checkpoint": [{k: v for k, v in x.items() if k != "thu_muc"} for x in DIEM],
    "chon": {"buoc": CHON["buoc"], "epoch": CHON["epoch"], "val_loss": CHON["val_loss"],
             "quy_tac": "val loss thấp nhất trong các điểm cuối epoch; chênh dưới 0,01 thì lấy điểm sớm hơn"},
    "g1": {**G1, "mau": G1_MAU}, "phien_ban_thu_vien": BAN, "gpu": GPU, "vram_dinh_gb": round(VRAM_DINH, 2),
    "sha256_adapter": sha256(RA / "adapter_model.safetensors"), "luc": time.strftime("%Y-%m-%d %H:%M:%S"),
}
(RA / "thong_tin.json").write_text(json.dumps(thong_tin, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
z = WORK / f"{TEN}.zip"
with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as f:
    for q in sorted(RA.iterdir()):
        f.write(q, f"{TEN}/{q.name}")
print(f"Đã lưu {RA} (adapter sha256 {thong_tin['sha256_adapter'][:16]}…), {CAC}, {z}")
print("Tiếp: gắn Output của notebook này vào lexo_gop_gguf." if G1["dat"] else "G1 KHÔNG ĐẠT: mang thong_tin.json về chat gốc trước.")
''')]

# ======================================================================================================================
# 3. Notebook GỘP → GGUF
# ======================================================================================================================

GOP = [md(r'''
# Lexo — hợp nhất LoRA chọn Điều và chuyển GGUF Q4_K_M (cổng G2)

**Cài đặt notebook:** **CPU** (không cần GPU), **Internet On**.
**Input:** Output của notebook `lexo_hoc_chon_dieu` (thư mục `<TEN>/` hoặc `<TEN>.zip`).
**Chạy:** Save Version → Save & Run All. Các bước: tải Qwen3-8B đúng revision → hợp nhất ở fp16 trên CPU → `convert_hf_to_gguf.py`
ra f16 → xóa bản hợp nhất → dựng `llama-quantize` → Q4_K_M → kiểm G2 (kiến trúc qwen3, 399 tensor, có chat template).
**Output:** `<ten_ollama>-q4_k_m.gguf` (~5 GB), `merge_info.json`, bản sao `thong_tin.json` của adapter. Gắn output này vào notebook đo.
'''), code(r'''
TEN = "lexo-qwen3-8b-chon-dieu-v1"       # trùng TEN của notebook học
LLAMA_CPP_COMMIT = ""                    # trống = bản mới nhất; mã commit thật được ghi vào merge_info.json
PHIEN_BAN = {"transformers": "5.20.1", "peft": "0.21.2", "accelerate": "1.15.0"}
TEN_OLLAMA = "qwen3-8b-lexo-" + TEN.removeprefix("lexo-qwen3-8b-")
'''), code(CHUNG), md(r'''
## 1. Tìm adapter, kiểm SHA256 theo `thong_tin.json`
'''), code(r'''
def tim_adapter(goc):
    ra = []
    for p in tim("thong_tin.json", goc):
        try:
            ok = json.loads(p.read_text(encoding="utf-8")).get("ten") == TEN
        except ValueError:
            ok = False
        if ok and (p.parent / "adapter_model.safetensors").exists():
            ra.append(p.parent)
    return ra


ung = tim_adapter(INPUT)
if not ung:
    for z in tim(f"{TEN}.zip"):
        with zipfile.ZipFile(z) as f:
            f.extractall(TAM / "adapter")
        ung = tim_adapter(TAM / "adapter")
        break
if len(ung) != 1:
    raise SystemExit(f"Cần đúng một adapter {TEN} trong /kaggle/input, thấy {len(ung)}: {ung}")
AD = ung[0]
TT = json.loads((AD / "thong_tin.json").read_text(encoding="utf-8"))
assert sha256(AD / "adapter_model.safetensors") == TT["sha256_adapter"], "SHA256 adapter không khớp thong_tin.json"
REVISION = TT["revision"]
print(f"Adapter {AD}: bước {TT['chon']['buoc']} (val loss {TT['chon']['val_loss']:.4f}), G1 {'đạt' if TT['g1']['dat'] else 'KHÔNG ĐẠT'}")
if not TT["g1"]["dat"]:
    raise SystemExit("G1 của adapter chưa đạt: không gộp. Xem thong_tin.json ở chat gốc.")
print(shutil.disk_usage(TAM))
'''), md(r'''
## 2. Hợp nhất ở fp16 trên CPU
'''), code(r'''
chay([sys.executable, "-m", "pip", "install", "-q", *[f"{k}=={v}" for k, v in PHIEN_BAN.items()]], duoi=5)
import gc, platform
import peft, torch, transformers
from huggingface_hub import snapshot_download
from peft import PeftModel
from transformers import AutoModelForCausalLM

BAN = {"python": platform.python_version(), "torch": torch.__version__, "transformers": transformers.__version__, "peft": peft.__version__}
print(BAN)
GOC_DIR, GOP_DIR = TAM / "qwen3-8b", TAM / "gop"
t0 = time.time()
snapshot_download(TT["mo_hinh_goc"], revision=REVISION, local_dir=GOC_DIR, allow_patterns=["*.json", "*.safetensors", "*.txt"])
base = AutoModelForCausalLM.from_pretrained(GOC_DIR, dtype=torch.float16, low_cpu_mem_usage=True)
gop = PeftModel.from_pretrained(base, AD).merge_and_unload()
gop.save_pretrained(GOP_DIR, safe_serialization=True, max_shard_size="4GB")
for f in GOC_DIR.iterdir():                      # tokenizer gốc nguyên bản (chat template nằm trong tokenizer_config.json)
    if f.name.startswith("tokenizer") or f.name in ("vocab.json", "merges.txt"):
        shutil.copy2(f, GOP_DIR / f.name)
del gop, base
gc.collect()
shutil.rmtree(GOC_DIR)
GIAY = {"hop_nhat": round(time.time() - t0)}
print(f"Hợp nhất xong sau {GIAY['hop_nhat'] / 60:.1f} phút;", shutil.disk_usage(TAM))
'''), md(r'''
## 3. GGUF f16 → Q4_K_M bằng llama.cpp
'''), code(r'''
LC = TAM / "llama.cpp"
if not LC.exists():
    if LLAMA_CPP_COMMIT:
        chay(["git", "clone", "https://github.com/ggml-org/llama.cpp", LC], duoi=2)
        chay(["git", "-C", LC, "checkout", LLAMA_CPP_COMMIT], duoi=2)
    else:
        chay(["git", "clone", "--depth", "1", "https://github.com/ggml-org/llama.cpp", LC], duoi=2)
COMMIT = subprocess.run(["git", "-C", str(LC), "rev-parse", "HEAD"], capture_output=True, text=True, check=True).stdout.strip()
print("llama.cpp", COMMIT)
chay([sys.executable, "-m", "pip", "install", "-q", str(LC / "gguf-py"), "sentencepiece", "protobuf"], duoi=5)
F16 = TAM / f"{TEN_OLLAMA}-f16.gguf"
t0 = time.time()
chay([sys.executable, LC / "convert_hf_to_gguf.py", GOP_DIR, "--outtype", "f16", "--outfile", F16], duoi=15)
shutil.rmtree(GOP_DIR)
GIAY["chuyen_f16"] = round(time.time() - t0)
if not shutil.which("cmake"):
    chay([sys.executable, "-m", "pip", "install", "-q", "cmake"], duoi=2)
t0 = time.time()
chay(["cmake", "-S", LC, "-B", LC / "build", "-DGGML_NATIVE=OFF", "-DLLAMA_CURL=OFF", "-DCMAKE_BUILD_TYPE=Release"], duoi=5)
chay(["cmake", "--build", LC / "build", "--target", "llama-quantize", "-j", os.cpu_count() or 4], duoi=3)
LQ = next(p for p in (LC / "build" / "bin").glob("llama-quantize*"))
Q4 = WORK / f"{TEN_OLLAMA}-q4_k_m.gguf"
chay([LQ, F16, Q4, "Q4_K_M"], duoi=8)
F16.unlink()
GIAY["luong_tu"] = round(time.time() - t0)
print(Q4, f"{Q4.stat().st_size / 2**30:.2f} GiB")
'''), md(r'''
## 4. G2 và `merge_info.json`
'''), code(r'''
sys.path.insert(0, str(LC / "gguf-py"))
from gguf import GGUFReader

r = GGUFReader(str(Q4))


def gia_tri(ten):
    f = r.fields.get(ten)
    if f is None:
        return None
    try:
        return f.contents()
    except AttributeError:
        v = f.parts[f.data[0]]
        return bytes(v).decode("utf-8") if v.dtype.kind == "u" and v.dtype.itemsize == 1 else v.tolist()


G2 = {"kien_truc": gia_tri("general.architecture"), "so_tensor": len(r.tensors), "co_chat_template": bool(gia_tri("tokenizer.chat_template")),
      "file_type": gia_tri("general.file_type")}
G2["dat"] = G2["kien_truc"] == "qwen3" and G2["so_tensor"] == 399 and G2["co_chat_template"]
print("G2:", G2, "→", "ĐẠT" if G2["dat"] else "KHÔNG ĐẠT")
info = {"ten": TEN, "ten_ollama": TEN_OLLAMA, "gguf": Q4.name, "kich_thuoc": Q4.stat().st_size, "sha256": sha256(Q4), "luong_tu": "Q4_K_M",
        "adapter": {"sha256": TT["sha256_adapter"], "chon": TT["chon"], "phien_ban_tin_nhan": TT["phien_ban_tin_nhan"]},
        "mo_hinh_goc": TT["mo_hinh_goc"], "revision": REVISION, "hop_nhat": "fp16 trên CPU (PeftModel.merge_and_unload)",
        "llama_cpp_commit": COMMIT, "g2": G2, "phien_ban_thu_vien": BAN, "giay": GIAY, "luc": time.strftime("%Y-%m-%d %H:%M:%S")}
(WORK / "merge_info.json").write_text(json.dumps(info, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
shutil.copy2(AD / "thong_tin.json", WORK / f"thong_tin_{TEN}.json")
print(f"sha256 {info['sha256']}\nĐã ghi {Q4.name} và merge_info.json. Tiếp: gắn Output này vào lexo_do_ban_an, bật CHAY_LORA_DEV.")
''')]


def main():
    ra = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "kaggle"
    ra.mkdir(exist_ok=True)
    for ten, cells, gpu in (("lexo_do_ban_an.ipynb", DO, True), ("lexo_hoc_chon_dieu.ipynb", HOC, True), ("lexo_gop_gguf.ipynb", GOP, False)):
        (ra / ten).write_text(json.dumps(nb(cells, gpu), ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
        print("ghi", ra / ten)


if __name__ == "__main__":
    main()
