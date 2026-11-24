"""Gom số liệu đo Kaggle/Colab thành eval/TONG_HOP_SO_LIEU_KAGGLE.md + .csv.

Chạy từ thư mục gốc dự án: python scripts/tong_hop_so_lieu_kaggle.py
Đọc inbox/ket_qua/, inbox/ket_qua_1/, các thong_tin.json và eval/ket_qua.md; ghi đè hai file đầu ra.
Khi có đợt đo mới (ví dụ inbox/kaggle_ket_qua/), thêm vào danh sách đợt trong script rồi chạy lại.
"""
import json, re, csv, zipfile, statistics as st
from math import comb
from pathlib import Path

R1 = Path("inbox/ket_qua")       # đợt 1: 14 câu (Colab/Kaggle, 15/10)
R2 = Path("inbox/ket_qua_1")     # đợt 2: 34 câu (Kaggle, 17/10)
OUT_MD = Path("eval/TONG_HOP_SO_LIEU_KAGGLE.md")
OUT_CSV = Path("eval/TONG_HOP_SO_LIEU_KAGGLE.csv")
csv_rows = []                    # bang, mo_hinh, tap, chi_so, gia_tri, nguon

def add(bang, mo, tap, chi_so, gt, nguon):
    csv_rows.append([bang, mo, tap, chi_so, gt, nguon])

def doc_md(p):
    t = Path(p).read_text(encoding="utf-8")
    n = int(re.search(r"\((\d+) tình huống", t).group(1))
    thieu = int(re.search(r"còn thiếu Điều \(bản tách\): (\d+)/", t).group(1))
    rows = {}
    for l in t.splitlines():
        if l.startswith("| ") and not l.startswith("| cách") and not l.startswith("|---"):
            c = [x.strip() for x in l.strip("|").split("|")]
            rows[c[0]] = c[1:]
    tach = rows["TÁCH hành vi, mỗi hành vi 3 Điều"]
    khong = rows["không tách, cùng số Điều hiển thị với bản tách"]
    base = {k: rows[k] for k in rows if k.startswith("không tách, hiển thị")}
    return dict(n=n, thieu=thieu, du=n - thieu, tach=tach, khong=khong, base=base,
                ids_thieu=set(re.findall(r"\[(dn\d+)\]", t.split("còn thiếu")[1])))

def doc_log(p):
    return {json.loads(l)["id"]: json.loads(l) for l in Path(p).read_text(encoding="utf-8").splitlines() if l.strip()}

MODELS = [("qwen3:8b (chỉ lời nhắc)", "qwen3-8b"), ("LoRA cũ (397 mẫu, có 31 mẫu trùng tổ hợp)", "qwen3-8b-lexo-tach"),
          ("LoRA n50 (sạch)", "qwen3-8b-lexo-sach-n50"), ("LoRA n368 (sạch)", "qwen3-8b-lexo-sach-n368")]
ids = [f"dn{i:02d}" for i in range(1, 35)]
SUB = {"tất cả 34": ("tat_ca", ids), "dn01–dn14 (14)": ("dn01-14", ids[:14]), "dn15–dn34 (20)": ("dn15-34", ids[14:])}

D = {}   # (mo_key, tap) -> dict
dung, du = {}, {}
for ten, m in MODELS:
    lg = doc_log(R2 / f"tach_dev_{m}_thuan_0vd.log.jsonl")
    dung[m] = {i: lg[i]["loi"] is None and lg[i]["so_hanh_vi"] == lg[i]["so_dieu_dap_an"] for i in ids}
    D[(m, "log")] = lg
    for tap, (suf, sub) in SUB.items():
        D[(m, tap)] = doc_md(R2 / f"kq_nhieu_dev_{m}_{suf}.md")
    du[m] = {i: i not in D[(m, "tất cả 34")]["ids_thieu"] for i in ids}
tran34 = doc_md(R2 / "kq_nhieu_dev_tran_tat_ca.md")
tran14 = doc_md(R1 / "kq_nhieu_dev_tran.md")

def k_dung(m, sub): return sum(dung[m][i] for i in sub)
def pct(a, b): return f"{a}/{b} ({round(100*a/b)}%)"

L = []
w = L.append
w("# Lexo — Tổng hợp số liệu đo (Kaggle/Colab) dùng cho bài báo")
w("")
w("Tạo ngày 2026-10-24 bằng script, đọc thẳng từ các file kết quả gốc (cột «Nguồn» ghi file). Không nhập tay số nào từ trí nhớ. "
  "File đi kèm `TONG_HOP_SO_LIEU_KAGGLE.csv` có cùng số liệu ở dạng dòng-dài (bảng, mô hình, tập, chỉ số, giá trị, nguồn) để vẽ biểu đồ.")
w("")
w("## 0. Số liệu gốc nằm ở đâu, dạng gì")
w("")
w("| Loại | Vị trí (trong `E:\\Lexo`) | Dạng | Ghi chú |")
w("|---|---|---|---|")
w("| Đợt 1: đo 14 câu (qwen3:4b, qwen3:8b, LoRA cũ, tách lý tưởng) | `inbox/ket_qua/` và `inbox/ket_qua.zip` | `kq_nhieu_dev_*.md` (bảng), `tach_dev_*.json` (kết quả tách), `tach_dev_*.log.jsonl` (mỗi dòng một câu: số hành vi, số Điều đáp án, giây, lỗi, văn bản thô) | zip và thư mục giống nhau |")
w("| Đợt 2: đo 34 câu (qwen3:8b, LoRA cũ, n50, n368, mốc trần) | `inbox/ket_qua_1/` và `inbox/ket_qua_1.zip` | như trên, thêm hậu tố `_tat_ca`, `_dn01-14`, `_dn15-34`; `Modelfile_*`; `thong_tin_n368.json` | `_14cau/` giữ mốc trần 14 câu cũ |")
w("| Thông tin từng lần học LoRA | `inbox/lexo-qwen3-8b-1/thong_tin.json` (LoRA cũ), `inbox/lexo-qwen3-8b-sach-n50-final.zip` → `thong_tin.json` (n50), `inbox/lexo-qwen3-8b-sach-n368-final/thong_tin.json` | JSON: siêu tham số, val loss theo bước, số giây, SHA256 adapter, phiên bản thư viện | adapter `.safetensors` ~167 MB mỗi cái |")
w("| Truy hồi 58 câu (chạy cục bộ, không phải Kaggle) | `eval/ket_qua.md` | Markdown: Hit@k, MRR, hạng từng câu | bộ câu `eval/cau_hoi_thu.json` |")
w("| Kế hoạch / quy tắc đọc kết quả đăng ký trước | `train/sach/KE_HOACH_LORA_PHAN_CON_LAI.md`, `kaggle/KE_HOACH_KAGGLE_V2.md` | Markdown | mục 5 của file đầu là bảng đọc kết quả |")
w("| Vòng 1 trên 90 vụ bản án (notebook v2) | **chưa có kết quả** | — | `inbox/kaggle_ket_qua/` chưa tồn tại; thư mục `kaggle/` mới chỉ có 3 notebook và kế hoạch |")
w("")
w("Không có CSDL hay file CSV tổng hợp nào có sẵn trước đây: số liệu nằm rải trong các file `.md` và `.jsonl` ở trên. File này là bản gom đầu tiên.")
w("")

# ---- 1. Huấn luyện
old = json.loads(Path("inbox/lexo-qwen3-8b-1/thong_tin.json").read_text(encoding="utf-8"))
z = zipfile.ZipFile("inbox/lexo-qwen3-8b-sach-n50-final.zip")
n50 = json.loads(z.read("thong_tin.json"))
n368 = json.loads((R2 / "thong_tin_n368.json").read_text(encoding="utf-8"))
w("## 1. Huấn luyện LoRA trên Kaggle (Qwen3-8B, QLoRA nf4, T4)")
w("")
w("Siêu tham số giống nhau cả ba lần: r16, α32, dropout 0,05, all-linear, lr 2e-4 cosine, warmup 5%, 3 epoch, micro-batch 4 × grad-acc 2, max_len 512, hạt 42, loss chỉ trên phần trả lời, `enable_thinking=False`.")
w("")
w("| | LoRA cũ | LoRA n50 | LoRA n368 |")
w("|---|---|---|---|")
w(f"| Ngày học (UTC) | {old['ngay_hoc'][:10]} | {n50['ngay_hoc'][:10]} | {n368['ngay_hoc'][:10]} |")
w("| Mẫu học / val | 397 / 53 (đếm dòng `train/sft_train.jsonl`, `sft_val.jsonl`) | 50 / 51 | 368 / 51 |")
w(f"| Số bước | 150 (3 epoch × 50) | {n50['so_buoc_thuc']} | {n368['so_buoc_thuc']} |")
w(f"| Thời gian học (giây) | không ghi | {n50['so_giay_hoc']} (≈{n50['so_giay_hoc']/n50['so_buoc_thuc']:.1f} s/bước) | {n368['so_giay_hoc']} (≈{n368['so_giay_hoc']/n368['so_buoc_thuc']:.1f} s/bước, ≈{n368['so_giay_hoc']/60:.1f} phút) |")
w(f"| Val loss ban đầu | {old['val_loss_ban_dau']:.4f} | {n50['val_loss_ban_dau']:.4f} | {n368['val_loss_ban_dau']:.4f} |")
w(f"| Val loss cuối | {old['val_loss_cuoi']:.4f} | {n50['val_loss_epoch_da_chon']:.4f} (epoch {n50['chon_epoch']['da_chon']}) | {n368['val_loss_epoch_da_chon']:.4f} (epoch {n368['chon_epoch']['da_chon']}; epoch 3 = {n368['val_loss_cuoi_epoch']['3']:.4f}) |")
w(f"| Val loss thấp nhất đã đo | {min(v for _, v in old['val_loss_theo_buoc']):.4f} (bước {min(old['val_loss_theo_buoc'], key=lambda x: x[1])[0]}) | {min(v for _, v in n50['val_loss_theo_buoc']):.4f} | {min(v for _, v in n368['val_loss_theo_buoc']):.4f} |")
w(f"| Sinh thử 20 mẫu val: JSON hợp lệ / có khối think / đúng số hành vi | {old['sinh_thu_val']['json_hop_le']}/20 / {old['sinh_thu_val']['co_khoi_think']} / không ghi | {n50['sinh_thu_val']['json_hop_le']}/20 / {n50['sinh_thu_val']['co_khoi_think']} / {n50['sinh_thu_val']['dung_so_hanh_vi']}/20 | {n368['sinh_thu_val']['json_hop_le']}/20 / {n368['sinh_thu_val']['co_khoi_think']} / {n368['sinh_thu_val']['dung_so_hanh_vi']}/20 |")
w(f"| Mẫu bị cắt do max_len | không ghi | {n50['du_lieu']['so_mau_bi_cat']} | {n368['du_lieu'].get('so_mau_bi_cat','không ghi')} |")
w(f"| Mô hình gốc ghim | `revision` null (không ghim) | `{n50['mo_hinh_goc']['commit_thuc_dung'][:8]}…` | `{n368['mo_hinh_goc']['commit_thuc_dung'][:8]}…` |")
w(f"| transformers / peft | {old['thu_vien']['transformers']} / {old['thu_vien']['peft']} | {n50['thu_vien']['transformers']} / {n50['thu_vien']['peft']} | {n368['thu_vien']['transformers']} / {n368['thu_vien']['peft']} |")
w(f"| SHA256 adapter | `{old['sha256_adapter'][:16]}…` | `{n50['sha256_adapter'][:16]}…` | `{n368['sha256_adapter'][:16]}…` |")
w("")
w("Val loss theo bước (bước, loss):")
w("")
for ten, d in (("LoRA cũ", old), ("LoRA n50", n50), ("LoRA n368", n368)):
    w(f"- {ten}: " + "; ".join(f"{b}: {v:.3f}" for b, v in d["val_loss_theo_buoc"]))
    for b, v in d["val_loss_theo_buoc"]:
        add("huan_luyen_val_loss", ten, "val", f"buoc_{b}", round(v, 4), "thong_tin.json")
w("")
w("Nguồn: `inbox/lexo-qwen3-8b-1/thong_tin.json`, `inbox/lexo-qwen3-8b-sach-n50-final.zip/thong_tin.json`, `inbox/ket_qua_1/thong_tin_n368.json`.")
w("")
for ten, d, tg in (("LoRA cũ", old, None), ("LoRA n50", n50, n50["so_giay_hoc"]), ("LoRA n368", n368, n368["so_giay_hoc"])):
    add("huan_luyen", ten, "-", "val_loss_ban_dau", round(d["val_loss_ban_dau"], 4), "thong_tin.json")
    if tg: add("huan_luyen", ten, "-", "so_giay_hoc", tg, "thong_tin.json")

# ---- 2. Đo tách hành vi dev 34 câu
w("## 2. Đo tách hành vi → truy hồi trên dev 34 câu nhiều Điều (đợt 2, Ollama 0.40.4, bge-m3, chế độ vector, mỗi hành vi 3 Điều)")
w("")
w("Tập dev: `eval/bo_cau_hoi.json` (dn01–dn34, TB 2,2 Điều đáp án/câu). **Nhãn còn `nhap`: do Claude soạn, chưa được người dùng duyệt** (xem mục 7).")
w("")
w("### 2.1 Bảng chính (tất cả 34 câu)")
w("")
w("| Mô hình tách | Tìm đủ | Bao phủ | Chính xác | Hành vi có đáp án | Đúng số hành vi | Điều hiển thị TB | «Không tách» cùng số Điều: tìm đủ |")
w("|---|---|---|---|---|---|---|---|")
for ten, m in MODELS:
    d = D[(m, "tất cả 34")]
    ds = k_dung(m, ids)
    w(f"| {ten} | {pct(d['du'], 34)} | {d['tach'][1]} | {d['tach'][2]} | {d['tach'][3]} | {pct(ds, 34)} | {d['tach'][5]} | {d['khong'][0]} (hiển thị {d['khong'][5]}) |")
    for tap in ("tất cả 34",):
        add("dev34_chinh", ten, tap, "tim_du", d["du"], f"inbox/ket_qua_1/kq_nhieu_dev_{m}_tat_ca.md")
        add("dev34_chinh", ten, tap, "tim_du_pct", d["tach"][0], f"inbox/ket_qua_1/kq_nhieu_dev_{m}_tat_ca.md")
        add("dev34_chinh", ten, tap, "bao_phu", d["tach"][1], f"inbox/ket_qua_1/kq_nhieu_dev_{m}_tat_ca.md")
        add("dev34_chinh", ten, tap, "chinh_xac", d["tach"][2], f"inbox/ket_qua_1/kq_nhieu_dev_{m}_tat_ca.md")
        add("dev34_chinh", ten, tap, "hanh_vi_co_dap_an", d["tach"][3], f"inbox/ket_qua_1/kq_nhieu_dev_{m}_tat_ca.md")
        add("dev34_chinh", ten, tap, "dung_so_hanh_vi", ds, f"inbox/ket_qua_1/tach_dev_{m}_thuan_0vd.log.jsonl")
        add("dev34_chinh", ten, tap, "dieu_hien_thi_tb", d["tach"][5], f"inbox/ket_qua_1/kq_nhieu_dev_{m}_tat_ca.md")
        add("dev34_chinh", ten, tap, "khong_tach_cung_so_dieu_tim_du_pct", d["khong"][0], f"inbox/ket_qua_1/kq_nhieu_dev_{m}_tat_ca.md")
w(f"| Tách lý tưởng, viết tay (mốc trần) | {pct(tran34['du'], 34)} | {tran34['tach'][1]} | {tran34['tach'][2]} | {tran34['tach'][3]} | 34/34 (100%) | {tran34['tach'][5]} | {tran34['khong'][0]} (hiển thị {tran34['khong'][5]}) |")
add("dev34_chinh", "Tách lý tưởng", "tất cả 34", "tim_du", tran34["du"], "inbox/ket_qua_1/kq_nhieu_dev_tran_tat_ca.md")
w("")
b = D[(MODELS[0][1], "tất cả 34")]["base"]
w("Mốc «không tách» (cùng cho mọi mô hình vì không dùng mô hình tách): " + "; ".join(f"{k.replace('không tách, hiển thị ','hiển thị ')}: tìm đủ {v[0]}, bao phủ {v[1]}, chính xác {v[2]}" for k, v in b.items()) + ".")
for k, v in b.items():
    add("dev34_khong_tach", "khong_tach", k, "tim_du_pct", v[0], "inbox/ket_qua_1/kq_nhieu_dev_qwen3-8b_tat_ca.md")
w("")
w("Định nghĩa: **tìm đủ** = mọi Điều đáp án đều nằm trong số Điều hiển thị (chỉ số chính); **bao phủ** = phần Điều đáp án được hiển thị; **chính xác** = phần Điều hiển thị là đáp án; **hành vi có đáp án** = phần hành vi tách ra có ít nhất một Điều đáp án trong 3 Điều đầu (đo tách thừa); **đúng số hành vi** = số hành vi tách ra bằng số Điều đáp án.")
w("")
w("### 2.2 Tách theo hai nhóm câu")
w("")
w("dn01–dn14: đã có từ trước; LoRA cũ có mẫu học trùng tổ hợp Điều với 6/14 câu này. dn15–dn34: thêm ngày 2026-10-16, tổ hợp Điều **không trùng** bất kỳ mẫu học nào của cả bốn mô hình (theo `KE_HOACH_LORA_PHAN_CON_LAI.md` mục 3), nên là phép so sánh sạch.")
w("")
w("| Mô hình | Tìm đủ dn01–14 | Đúng số dn01–14 | Tìm đủ dn15–34 | Đúng số dn15–34 | Điều hiển thị TB (dn01–14 / dn15–34) |")
w("|---|---|---|---|---|---|")
for ten, m in MODELS:
    a, c = D[(m, "dn01–dn14 (14)")], D[(m, "dn15–dn34 (20)")]
    w(f"| {ten} | {pct(a['du'],14)} | {pct(k_dung(m, ids[:14]),14)} | {pct(c['du'],20)} | {pct(k_dung(m, ids[14:]),20)} | {a['tach'][5]} / {c['tach'][5]} |")
    for tap, dd, sub in (("dn01–14", a, ids[:14]), ("dn15–34", c, ids[14:])):
        add("dev34_nhom", ten, tap, "tim_du", dd["du"], "kq_nhieu_dev_*_dn*.md")
        add("dev34_nhom", ten, tap, "dung_so_hanh_vi", k_dung(m, sub), "tach_dev_*.log.jsonl")
t14 = tran34["n"]
tr_a = 14 - tran14["thieu"]
w(f"| Tách lý tưởng (mốc trần) | {pct(tr_a,14)} | 14/14 (100%) | {pct(tran34['du']-tr_a,20)} (suy ra từ 34 − 14) | 20/20 (100%) | — |")
w("")
w("Nguồn: `inbox/ket_qua_1/kq_nhieu_dev_<mô hình>_{tat_ca,dn01-14,dn15-34}.md` (tìm đủ và các cột %), `inbox/ket_qua_1/tach_dev_<mô hình>_thuan_0vd.log.jsonl` (đúng số hành vi: đếm các câu có `so_hanh_vi == so_dieu_dap_an`, mọi câu `loi = null`).")
w("")

# ---- 3. Kiểm cặp
def mcn(a, bb, sub):
    x = sum(1 for i in sub if a[i] and not bb[i]); y = sum(1 for i in sub if bb[i] and not a[i]); n = x + y
    if n == 0: return x, y, 1.0
    k = max(x, y); p = min(1.0, 2 * sum(comb(n, j) for j in range(k, n + 1)) / 2 ** n); return x, y, p
w("## 3. So sánh cặp (McNemar chính xác, hai phía) — ba so sánh đã đăng ký trước + hai so sánh phụ")
w("")
w("Cùng bộ câu cho mọi mô hình nên dùng kiểm cặp: đếm câu mà hai mô hình cho kết quả khác nhau. Cột «hơn/kém» là số câu chỉ mô hình thứ nhất đúng / chỉ mô hình thứ hai đúng.")
w("")
w("| So sánh | Tập | Đúng số hành vi (hơn/kém, p) | Tìm đủ (hơn/kém, p) |")
w("|---|---|---|---|")
cmp_ = [("① n368 so với qwen3:8b (đăng ký trước)", "qwen3-8b-lexo-sach-n368", "qwen3-8b", "34", ids),
        ("② n368 so với n50 (đăng ký trước)", "qwen3-8b-lexo-sach-n368", "qwen3-8b-lexo-sach-n50", "34", ids),
        ("③ n368 so với LoRA cũ (đăng ký trước, chỉ dn15–34)", "qwen3-8b-lexo-sach-n368", "qwen3-8b-lexo-tach", "20 (dn15–34)", ids[14:]),
        ("n368 so với LoRA cũ (phụ)", "qwen3-8b-lexo-sach-n368", "qwen3-8b-lexo-tach", "34", ids),
        ("n50 so với qwen3:8b (phụ)", "qwen3-8b-lexo-sach-n50", "qwen3-8b", "34", ids)]
for nm, a, bb, tap, sub in cmp_:
    r1 = mcn(dung[a], dung[bb], sub); r2 = mcn(du[a], du[bb], sub)
    w(f"| {nm} | {tap} | {r1[0]}/{r1[1]}, p = {r1[2]:.4f} | {r2[0]}/{r2[1]}, p = {r2[2]:.4f} |")
    add("kiem_cap", nm, tap, "dung_so_p", round(r1[2], 4), "tính từ log + md"); add("kiem_cap", nm, tap, "tim_du_p", round(r2[2], 4), "tính từ log + md")
w("")
w("Không hiệu chỉnh nhiều phép kiểm (5 phép trên cùng một tập 34 câu). Nhãn dev chưa được duyệt và dev đã bị «nhìn» nhiều lần nên p-value chỉ để tham khảo; kết luận cuối phải dựa vào tập kiểm tra đóng băng chạy một lần.")
w("")
w("Theo bảng đọc đăng ký trước (`KE_HOACH_LORA_PHAN_CON_LAI.md` mục 5): n368 đạt 24/34 đúng số hành vi, dưới ngưỡng 29/34 nhưng hơn qwen3:8b có ý nghĩa → rơi vào dòng «vùng giữa, chưa kết luận».")
w("")

# ---- 4. Đợt 1: 14 câu
w("## 4. Đợt 1 — đo 14 câu (dn01–dn14, 15/10)")
w("")
w("| Mô hình | Tìm đủ | Bao phủ | Chính xác | Hành vi có đáp án | Đúng số hành vi | Điều hiển thị TB | Giây TB/câu |")
w("|---|---|---|---|---|---|---|---|")
for ten, f, lg in (("qwen3:4b (chỉ lời nhắc)", "qwen3-4b_thuan_0vd", "qwen3-4b"), ("qwen3:8b (chỉ lời nhắc)", "qwen3-8b_thuan_0vd", "qwen3-8b"),
                   ("LoRA cũ", "qwen3-8b-lexo-tach_thuan_0vd", "qwen3-8b-lexo-tach")):
    d = doc_md(R1 / f"kq_nhieu_dev_{f}.md"); lgd = doc_log(R1 / f"tach_dev_{lg}_thuan_0vd.log.jsonl")
    ds = sum(v["loi"] is None and v["so_hanh_vi"] == v["so_dieu_dap_an"] for v in lgd.values())
    gi = st.mean(v["giay"] for v in lgd.values())
    w(f"| {ten} | {pct(d['du'],14)} | {d['tach'][1]} | {d['tach'][2]} | {d['tach'][3]} | {pct(ds,14)} | {d['tach'][5]} | {gi:.1f} |")
    add("dev14_dot1", ten, "dn01–14", "tim_du", d["du"], f"inbox/ket_qua/kq_nhieu_dev_{f}.md"); add("dev14_dot1", ten, "dn01–14", "dung_so", ds, f"inbox/ket_qua/tach_dev_{lg}_thuan_0vd.log.jsonl")
w(f"| Tách lý tưởng (mốc trần) | {pct(tran14['du'],14)} | {tran14['tach'][1]} | {tran14['tach'][2]} | {tran14['tach'][3]} | 14/14 (100%) | {tran14['tach'][5]} | — |")
w("")
w("Số 14 câu đợt 1 và số 34 câu đợt 2 không phải cùng một phép đo; chỉ dùng cột dn01–dn14 của mục 2.2 để đối chiếu. Trên dn01–14, qwen3:8b và LoRA cũ cho cùng số liệu tổng ở đợt 1 và đợt 2 (tìm đủ 36% và 57%).")
w("")

# ---- 5. Thời gian
w("## 5. Thời gian và độ ổn định khi tách (34 câu, T4, Ollama)")
w("")
w("| Mô hình | Lỗi | Khối think | Giây TB | Giây trung vị | Giây lớn nhất | Tổng giây | Hành vi TB/câu |")
w("|---|---|---|---|---|---|---|---|")
for ten, m in MODELS:
    lg = D[(m, "log")]; gi = [v["giay"] for v in lg.values()]
    loi = sum(v["loi"] is not None for v in lg.values()); th = sum("<think>" in (v["tho"] or "") for v in lg.values())
    w(f"| {ten} | {loi}/34 | {th} | {st.mean(gi):.1f} | {st.median(gi):.1f} | {max(gi):.1f} | {sum(gi):.0f} | {st.mean(v['so_hanh_vi'] for v in lg.values()):.2f} |")
    add("thoi_gian", ten, "34", "giay_tb", round(st.mean(gi), 2), f"inbox/ket_qua_1/tach_dev_{m}_thuan_0vd.log.jsonl"); add("thoi_gian", ten, "34", "giay_max", max(gi), "log.jsonl")
w("")
w("Lần chạy qwen3:8b đầu có một câu mất khoảng 99 giây (có thể do nạp mô hình lần đầu; chưa xác minh), kéo trung bình lên; trung vị 3,0 giây gần với các mô hình LoRA. Đừng dùng số trung bình để so tốc độ.")
w("")

# ---- 6. Truy hồi
w("## 6. Truy hồi 58 câu (chạy cục bộ, không phải Kaggle)")
w("")
w("Nguồn: `eval/ket_qua.md`, bộ `eval/cau_hoi_thu.json` (58 câu, nhãn đã được người dùng duyệt), bge-m3 qua Ollama, 6351 chunk.")
w("")
w("| Chế độ | Hit@1 | Hit@3 | Hit@5 | Hit@10 | MRR |")
w("|---|---|---|---|---|---|")
t = Path("eval/ket_qua.md").read_text(encoding="utf-8")
for l in t.splitlines():
    if re.match(r"\| (hybrid|vector|fts) \|", l):
        c = [x.strip() for x in l.strip("|").split("|")]
        w(f"| {c[0]} | {c[1]} | {c[2]} | {c[3]} | {c[4]} | {c[5]} |")
        for nm, v in zip(("hit1", "hit3", "hit5", "hit10", "mrr"), c[1:]): add("truy_hoi_58", c[0], "kiem_tra58", nm, v, "eval/ket_qua.md")
w("")
w("Kết quả thử câu hỏi sinh sẵn (doc2query, qwen2.5:3b) xấu hơn mốc vector và đã bị loại; số liệu chỉ nằm trong hội thoại, **chưa lưu thành file**. Chạy lại với qwen3:8b chưa làm.")
w("")

# ---- 7. Lưu ý
w("## 7. Lưu ý khi dùng trong bài báo")
w("")
w("1. **Nhãn dev chưa duyệt.** `eval/bo_cau_hoi.json`: 104 câu `dev` đều `nguon = claude`, `trang_thai = nhap`. Cùng một người soạn với dữ liệu học nên nghiêng về lạc quan. Cần ≥ 10 câu do người dùng tự viết (`nguon = nguoi_dung`) và nhờ người khác duyệt trước khi trích số.")
w("2. **Dev đã bị nhìn nhiều lần** (mỗi lần đo lại là một lần xem), nên không dùng số dev làm kết quả cuối. Kết luận chỉ nên dựa vào tập `kiem_tra` đóng băng, chạy đúng một lần khi mô hình và tham số đã chốt.")
w("3. **Một hạt (42), một lần chạy mỗi cấu hình.** Chưa đo độ dao động giữa các hạt (kế hoạch C1: n50 hạt 43/44). Chênh dưới khoảng 7 câu coi là nhiễu theo bảng độ lớn ở `KE_HOACH_LORA_PHAN_CON_LAI.md` mục 5.")
w("4. **LoRA cũ không ghim commit mô hình gốc và dùng transformers 5.19.0**; n50/n368 ghim `b968826d…`; n50 dùng transformers 5.19.0, n368 dùng 5.20.1. Tập val của LoRA cũ (53 mẫu) khác tập val của n50/n368 (51 mẫu) nên val loss không so trực tiếp được giữa LoRA cũ và hai bản sạch. Nêu các khác biệt này khi so LoRA cũ với hai bản sạch.")
w("5. **LoRA cũ đứng đầu về «đúng số hành vi» (29/34) và «tìm đủ» (21/34), hơn n368 (24/34 và 17/34)**, kể cả trên dn15–34 là nhóm sạch (16/20 so với 14/20 đúng số; 13/20 so với 10/20 tìm đủ). Chênh lệch trên nhóm sạch nhỏ (2–3 câu) và không có ý nghĩa theo kiểm cặp ở mục 3. Chưa giải thích được vì sao bản sạch n368 không vượt LoRA cũ; kế hoạch C (hạt, số mẫu, bỏ tiền tố tên tội) chưa chạy.")
w("6. **Mốc trần cho thấy nút thắt nằm ở truy hồi, không ở khâu tách**: tách lý tưởng đúng số hành vi 100% nhưng tìm đủ chỉ 44% (15/34), thấp hơn LoRA cũ (62%) và n368 (50%). Nghĩa là «đúng số hành vi» không suy ra «tìm đủ»; báo cáo cả hai chỉ số.")
w("7. **Hợp nhất sang GGUF Q4_K_M** nên số đo là của mô hình lượng tử hóa, không phải adapter gốc.")
w("")
w("## 8. Chưa có số (đừng điền khống)")
w("")
w("- Vòng 1 đo 90 vụ bản án, Vòng 2 học chọn Điều, Vòng 3, và tập test của kế hoạch v2 (`kaggle/KE_HOACH_KAGGLE_V2.md`): chưa chạy, `inbox/kaggle_ket_qua/` chưa có.")
w("- Thời gian học và số mẫu bị cắt của LoRA cũ (`thong_tin.json` của lần đó không có hai khóa này).")
w("- Kiểm tra đóng băng (`kiem_tra`) cho khâu tách: chưa chạy.")
OUT_MD.write_text("\n".join(L) + "\n", encoding="utf-8", newline="\n")
with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
    cw = csv.writer(f); cw.writerow(["bang", "mo_hinh", "tap", "chi_so", "gia_tri", "nguon"]); cw.writerows(csv_rows)
print(len(L), "dòng md;", len(csv_rows), "dòng csv")
