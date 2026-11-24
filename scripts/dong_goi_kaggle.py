"""Đóng gói dữ liệu và notebook cho Kaggle (tài liệu «Lexo — Quy trình train trên Kaggle»): hai gói tách biệt, kèm SHA256SUMS.

  python scripts/dong_goi_kaggle.py              # cần Ollama đang chạy và đã `ollama pull bge-m3` (nhúng các đoạn sự việc để tìm ứng viên)
  python scripts/dong_goi_kaggle.py --gia        # vector giả, chỉ thử đường ống: zip có hậu tố _GIA, KHÔNG đem lên Kaggle

Đầu ra (mặc định inbox/kaggle/):
  lexo_hoc_chon_dieu.zip   gói HỌC (Dataset Kaggle private, gắn vào notebook học). Không có chữ của vụ test nào.
  lexo_do_ban_an.zip       gói ĐO (Dataset Kaggle private, gắn vào notebook đo): mã nguồn, chỉ mục, 189 vụ kèm ứng viên đã xếp hạng.
  *.ipynb, KE_HOACH_KAGGLE_V2.md   chép từ thư mục kaggle/ của dự án.

Các bước: chia 90 vụ train thành 70 học / 20 dev theo nhóm vụ (hạt 2026) -> cắt sự việc (1.400 từ đầu + 600 từ cuối) -> tìm ứng viên
cho 189 vụ + 419 mẫu tổng hợp (mỗi đoạn ~300 từ tìm riêng, gộp RRF, chỉ Điều 108–425) -> chọn chế độ + K trên 90 vụ train
(K nhỏ nhất có «đủ đáp án trong top K» >= 90%, tối đa 30) -> SFT -> kiểm giao G0 (test không được dính vào gói học) -> ghi gói.
Recall của 99 vụ test KHÔNG được tính hay in ở đây (test chỉ chạy một lần, ở cuối).
Kết quả tìm ứng viên được nhớ trong <ra>/_tam/xep_hang.json: dừng giữa chừng thì chạy lại sẽ tiếp từ chỗ dừng.
Thoát 0 nếu ổn; 1 nếu G0 phát hiện rò rỉ hoặc dữ liệu lỗi; 2 nếu ứng viên dưới sàn (vẫn ghi gói đo, không ghi gói học,
trừ khi thêm --bo-qua-cong).
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ban_an import chon_dieu as cd  # noqa: E402
from src.ban_an import goi_kaggle as gk  # noqa: E402
from src.config import index_path, load_config  # noqa: E402
from src.index.embedder import EmbedError, HashEmbedder, tu_config  # noqa: E402
from src.index.store import open_index  # noqa: E402

BAN_AN_MAC_DINH = ROOT / "inbox" / "anle_hf" / "ban_an_hinh_su.json"
SACH_MAC_DINH = ROOT / "train" / "sach"
TINH_HUONG_MAC_DINH = ROOT / "train" / "tinh_huong.json"
KAGGLE_DIR = ROOT / "kaggle"
SCRIPT_GOI_DO = ("do_ban_an.py",)


class NhoTam:
    """Bọc embedder: cùng một đoạn chữ chỉ nhúng một lần."""

    def __init__(self, emb):
        self.emb, self.name, self.cache = emb, emb.name, {}

    def embed(self, texts):
        thieu = [t for t in dict.fromkeys(texts) if t not in self.cache]
        if thieu:
            for t, v in zip(thieu, self.emb.embed(thieu)):
                self.cache[t] = v
        return [self.cache[t] for t in texts]


def in_bang_recall(ten: str, bang: dict) -> list[str]:
    ks = sorted(next(iter(bang.values())))
    dong = [f"{ten}: phần vụ có ĐỦ đáp án trong top K (trong ngoặc: phần Điều đáp án nằm trong top K)",
            "| chế độ | " + " | ".join(f"K={k}" for k in ks) + " |", "|---|" + "---|" * len(ks)]
    for c, theo_k in bang.items():
        dong.append(f"| {c} | " + " | ".join(f"{theo_k[k]['du']:.0%} ({theo_k[k]['recall']:.0%})" for k in ks) + " |")
    return dong


def readme_hoc(tt: dict) -> str:
    return f"""# Lexo — gói học «chọn Điều từ ứng viên» ({gk.TEN_GOI_HOC})

Gói này chỉ dùng cho notebook học `lexo_hoc_chon_dieu.ipynb`. Không có chữ của vụ test nào; `kiem_giao.json` chỉ chứa mã và băm
của 99 vụ test để notebook tự kiểm. Kiểm toàn vẹn: `sha256sum -c SHA256SUMS`.

| File | Dòng | Dùng để |
|---|---|---|
| `sft_chon_train.jsonl` | {tt['so_dong']['train']} | học: {tt['so_mau']['ban_an_hoc']} vụ bản án + {tt['so_mau']['tong_hop_hoc']} mẫu tổng hợp |
| `sft_chon_val.jsonl` | {tt['so_dong']['val']} | val loss, chọn checkpoint: {tt['so_mau']['ban_an_dev']} vụ dev + {tt['so_mau']['tong_hop_val']} mẫu tổng hợp |
| `sft_chon_train_tong_hop.jsonl` | {tt['so_dong']['train_tong_hop']} | Vòng 3, C1: chỉ mẫu tổng hợp |
| `thong_tin_du_lieu.json` | | K, chế độ ứng viên, số đáp án đã chèn, mã băm nguồn |
| `kiem_giao.json` | | mã + băm sự việc của vụ test |

Ứng viên: chế độ `{tt['ung_vien']['che_do']}`, K = {tt['ung_vien']['k']}, xếp theo số Điều. Đáp án thiếu trong top K được chèn
thay ứng viên hạng thấp nhất ({tt['chen']['train']} lần ở train, {tt['chen']['val']} lần ở val); dev/test lúc đo không bao giờ chèn.
Lời nhắc hệ thống: `{cd.PHIEN_BAN_TIN_NHAN}`, phải khớp từng ký tự với lúc đo (nằm sẵn trong từng dòng).
"""


def readme_do(ch: dict) -> str:
    return f"""# Lexo — gói đo bản án ({gk.TEN_GOI_DO})

Dùng cho notebook `lexo_do_ban_an.ipynb` (Vòng 1, cổng G3/G4 của LoRA chọn Điều, và lượt test cuối). KHÔNG gắn gói này vào notebook học.
Kiểm toàn vẹn: `sha256sum -c SHA256SUMS`.

- `ban_an_do.json`: 189 vụ (tap hoc / dev / test), sự việc đã cắt, Điều tòa áp dụng, ứng viên đã xếp hạng (top 50 mỗi chế độ),
  tiêu đề Điều theo ngày bản án.
- `cau_hinh.json`: chế độ ứng viên `{ch['ung_vien']['che_do']}`, K = {ch['ung_vien']['k']}, lời nhắc, bảng Recall@K trên 90 vụ train.
- `src/`, `scripts/do_ban_an.py`, `config.yaml`, `db/chi_muc.sqlite`: mã nguồn và chỉ mục đúng bản đã sinh ứng viên.

Chạy: `python scripts/do_ban_an.py --tap train90` (Vòng 1). Lượt test (`--tap test`) cần `--da-chot` và `cau_hinh_chot.json`.
"""


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ban-an", type=Path, default=BAN_AN_MAC_DINH)
    ap.add_argument("--sach", type=Path, default=SACH_MAC_DINH, help="thư mục tập sạch n368 (sft_train_sach.jsonl, sft_val_sach.jsonl)")
    ap.add_argument("--tinh-huong", type=Path, default=TINH_HUONG_MAC_DINH)
    ap.add_argument("--index", type=Path, default=None)
    ap.add_argument("--ra", type=Path, default=ROOT / "inbox" / "kaggle")
    ap.add_argument("--so-dev", type=int, default=20)
    ap.add_argument("--seed", type=int, default=2026)
    ap.add_argument("--model", default=None, help="mô hình nhúng trong Ollama (mặc định theo config.yaml: bge-m3)")
    ap.add_argument("--endpoint", default=None)
    ap.add_argument("--gia", action="store_true", help="vector giả: chỉ thử đường ống")
    ap.add_argument("--bo-qua-cong", action="store_true", help="vẫn ghi gói học khi ứng viên dưới sàn (ghi rõ trong báo cáo)")
    args = ap.parse_args()

    ip = args.index or index_path()
    for p in (args.ban_an, args.sach / "sft_train_sach.jsonl", args.sach / "sft_val_sach.jsonl", args.tinh_huong, ip):
        if not p.exists():
            sys.exit(f"LỖI: không thấy {p}")
    try:
        ban_an = json.loads(args.ban_an.read_text(encoding="utf-8"))
        ba = gk.mau_ban_an(ban_an, args.so_dev, args.seed)
        th, canh_bao = gk.mau_tong_hop(json.loads(args.tinh_huong.read_text(encoding="utf-8")),
                                       [x["id"] for x in gk.doc_jsonl(args.sach / "sft_train_sach.jsonl")],
                                       [x["id"] for x in gk.doc_jsonl(args.sach / "sft_val_sach.jsonl")])
    except (gk.GoiError, cd.ChonError, KeyError, ValueError) as e:
        sys.exit(f"LỖI: {e}")
    for c in canh_bao:
        print(f"  ! {c}")
    theo_tap = {t: [x for x in ba + th if x["tap"] == t] for t in ("hoc", "dev", "test", "tong_hop_hoc", "tong_hop_val")}
    print("Mẫu: " + ", ".join(f"{t} {len(v)}" for t, v in theo_tap.items())
          + f"; vụ bị cắt sự việc: train {sum(x['da_cat'] for x in theo_tap['hoc'] + theo_tap['dev'])}, test {sum(x['da_cat'] for x in theo_tap['test'])}")

    idx = open_index(ip)
    emb = NhoTam(HashEmbedder() if args.gia else tu_config(load_config(), model=args.model, endpoint=args.endpoint))
    tam = args.ra / "_tam" / "xep_hang.json"
    cache = json.loads(tam.read_text(encoding="utf-8")) if tam.exists() else {}
    t0 = time.time()

    def bao(i: int, n: int) -> None:
        if i % 20 == 0 or i == n:
            print(f"  tìm ứng viên {i}/{n} ({time.time() - t0:.0f}s)", flush=True)
            tam.parent.mkdir(parents=True, exist_ok=True)
            tam.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")

    tat_ca = ba + th
    print(f"Tìm ứng viên cho {len(tat_ca)} mẫu bằng {emb.name} + FTS5 (đã nhớ sẵn {len(cache)})...")
    try:
        gk.gan_xep_hang(tat_ca, lambda chu, ngay: cd.xep_hang_dieu(idx, emb, chu, ngay), cache, emb.name, bao)
    except (EmbedError, ValueError) as e:
        tam.parent.mkdir(parents=True, exist_ok=True)
        tam.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        sys.exit(f"LỖI: {e}")

    train90 = theo_tap["hoc"] + theo_tap["dev"]
    bang = cd.bang_recall(train90)
    chon = cd.chon_k(bang)
    for d in in_bang_recall(f"90 vụ train bản án", bang) + [""] + in_bang_recall("368 mẫu tổng hợp (học)", cd.bang_recall(theo_tap["tong_hop_hoc"])):
        print(d)
    print(f"\nChọn: chế độ {chon['che_do']}, K = {chon['k']} ({'đạt' if chon['dat_muc'] else 'KHÔNG đạt'} mức {cd.RECALL_MUC:.0%}; "
          f"đủ đáp án trong top {chon['k_toi_da']}: {chon['du_tai_k_toi_da']:.0%})")
    duoi_san = chon["du_tai_k_toi_da"] < cd.RECALL_SAN
    if duoi_san:
        print(f"CẢNH BÁO: dưới sàn {cd.RECALL_SAN:.0%}: bộ sinh ứng viên là nút thắt. Theo kế hoạch: sửa truy hồi trước, hoãn Vòng 2.")

    tieu_de_ngay: dict = {}

    def tieu_de(x: dict) -> dict[str, str]:
        if x["ngay_tra_cuu"] not in tieu_de_ngay:
            tieu_de_ngay[x["ngay_tra_cuu"]] = cd.tieu_de_dieu(idx, x["ngay_tra_cuu"])
        return tieu_de_ngay[x["ngay_tra_cuu"]]

    loi = [f"{x['id']}: Điều {d} không có trong chỉ mục tại ngày {x['ngay_tra_cuu'] or 'hôm nay'}"
           for x in tat_ca for d in x["dieu"] if d not in tieu_de(x)]
    if loi:
        sys.exit("LỖI: " + "; ".join(loi[:5]))

    # ---- gói ĐO ----------------------------------------------------------------------------------------------------
    hau_to = "_GIA" if args.gia else ""
    goi_do = args.ra / gk.TEN_GOI_DO
    if goi_do.exists():
        shutil.rmtree(goi_do)
    goi_do.mkdir(parents=True)
    mau_do = []
    for x in ba:
        td = tieu_de(x)
        can = {d for v in x["xep_hang"].values() for d in v} | set(x["dieu"])
        mau_do.append({k: x[k] for k in ("id", "tap", "su_viec", "da_cat", "so_tu_goc", "dieu", "nhom_vu", "ngay", "ngay_tra_cuu",
                                         "ten_toi_trong_loi_ke", "dieu_chua_gap", "xep_hang")}
                      | {"tieu_de": {d: td[d] for d in cd.sap_xep(can) if d in td}})
    gk.ghi_json(goi_do / "ban_an_do.json", {"phien_ban": 1, "nguon": ban_an.get("nguon"), "so_dev": args.so_dev, "seed": args.seed,
                                             "mau": mau_do})
    cau_hinh = {"phien_ban_tin_nhan": cd.PHIEN_BAN_TIN_NHAN, "he_thong_chon": cd.HE_THONG_CHON, "so_tu_dau": cd.SO_TU_DAU,
                "so_tu_cuoi": cd.SO_TU_CUOI, "doan_tu": cd.DOAN_TU, "rrf_k": cd.RRF_K, "mo_hinh_nhung": emb.name, "gia": args.gia,
                "ung_vien": {"che_do": chon["che_do"], "k": chon["k"]}, "chon_k": chon,
                "recall_train90": {c: {str(k): v for k, v in t.items()} for c, t in bang.items()},
                "sha256": {"ban_an_do.json": gk.sha256_file(goi_do / "ban_an_do.json"), "chi_muc.sqlite": gk.sha256_file(ip),
                           "ban_an_hinh_su.json": gk.sha256_file(args.ban_an)}}
    gk.ghi_json(goi_do / "cau_hinh.json", cau_hinh)
    gk.chep_ma_nguon(ROOT, goi_do, SCRIPT_GOI_DO)
    (goi_do / "db").mkdir(exist_ok=True)
    shutil.copyfile(ip, goi_do / "db" / "chi_muc.sqlite")
    (goi_do / gk.DAU_GOI_DO).write_text(readme_do(cau_hinh), encoding="utf-8", newline="\n")
    gk.ghi_sha256sums(goi_do)
    sha_do = gk.nen_zip(goi_do, args.ra / f"{gk.TEN_GOI_DO}{hau_to}.zip")
    print(f"\nĐã ghi {args.ra / (gk.TEN_GOI_DO + hau_to + '.zip')} (sha256 {sha_do})")
    for p in sorted(KAGGLE_DIR.glob("*")) if KAGGLE_DIR.exists() else []:
        if p.is_file() and p.suffix in (".ipynb", ".md"):
            shutil.copyfile(p, args.ra / p.name)
            print(f"Đã chép {p.name}")

    # ---- gói HỌC ---------------------------------------------------------------------------------------------------
    hoc = theo_tap["hoc"] + theo_tap["tong_hop_hoc"]
    val = theo_tap["dev"] + theo_tap["tong_hop_val"]
    loi_g0 = gk.kiem_giao(theo_tap["test"], hoc + val)
    if loi_g0:
        print("LỖI G0 (rò rỉ test vào gói học): " + "; ".join(loi_g0[:10]))
        return 1
    print(f"G0: 0 vụ test dính vào gói học (id, nhóm vụ, băm, độ chứa 5-gram >= 0,5; so với {len(hoc + val)} mẫu)")
    if duoi_san and not args.bo_qua_cong:
        print("Chưa ghi gói học (ứng viên dưới sàn). Thêm --bo-qua-cong nếu vẫn muốn học.")
        return 2

    k, che_do = chon["k"], chon["che_do"]
    dong = {t: [gk.dong_sft(x, che_do, k, tieu_de(x)) for x in ds] for t, ds in
            (("train", hoc), ("val", val), ("train_tong_hop", theo_tap["tong_hop_hoc"]))}
    goi_hoc = args.ra / gk.TEN_GOI_HOC
    if goi_hoc.exists():
        shutil.rmtree(goi_hoc)
    goi_hoc.mkdir(parents=True)
    for t, ds in dong.items():
        gk.ghi_jsonl(goi_hoc / f"sft_chon_{t}.jsonl", ds)
    gk.ghi_json(goi_hoc / "kiem_giao.json", {"ghi_chu": "mã và sha256 sự việc (đã cắt) của vụ test; notebook học kiểm không dòng nào trùng",
                                            "ma_test": sorted(x["id"] for x in theo_tap["test"]),
                                            "sha256_su_viec_test": sorted(cd.bam_chu(x["su_viec"]) for x in theo_tap["test"])})
    so_tu = [r["so_tu_su_viec"] for r in dong["train"] + dong["val"]]
    tt = {"phien_ban_tin_nhan": cd.PHIEN_BAN_TIN_NHAN, "he_thong_chon": cd.HE_THONG_CHON, "gia": args.gia,
          "ung_vien": {"che_do": che_do, "k": k}, "chon_k": chon,
          "so_mau": {"ban_an_hoc": len(theo_tap["hoc"]), "ban_an_dev": len(theo_tap["dev"]),
                     "tong_hop_hoc": len(theo_tap["tong_hop_hoc"]), "tong_hop_val": len(theo_tap["tong_hop_val"])},
          "so_dong": {t: len(ds) for t, ds in dong.items()},
          "chen": {t: sum(r["chen"] for r in ds) for t, ds in dong.items()},
          "dong_co_chen": {t: sum(1 for r in ds if r["chen"]) for t, ds in dong.items()},
          "ban_an_bi_cat": {"train": sum(x["da_cat"] for x in theo_tap["hoc"]), "val": sum(x["da_cat"] for x in theo_tap["dev"])},
          "so_tu_su_viec": {"toi_da": max(so_tu), "trung_binh": round(sum(so_tu) / len(so_tu), 1)},
          "so_tu_dau": cd.SO_TU_DAU, "so_tu_cuoi": cd.SO_TU_CUOI, "seed_chia_dev": args.seed,
          "id": {t: [x["id"] for x in ds] for t, ds in (("ban_an_hoc", theo_tap["hoc"]), ("ban_an_dev", theo_tap["dev"]))},
          "sha256_nguon": {"ban_an_hinh_su.json": gk.sha256_file(args.ban_an), "tinh_huong.json": gk.sha256_file(args.tinh_huong),
                           "sft_train_sach.jsonl": gk.sha256_file(args.sach / "sft_train_sach.jsonl"),
                           "sft_val_sach.jsonl": gk.sha256_file(args.sach / "sft_val_sach.jsonl"), "chi_muc.sqlite": gk.sha256_file(ip)},
          "g0": {"so_mau_so_sanh": len(hoc + val), "so_vu_test": len(theo_tap["test"]), "loi": []}}
    gk.ghi_json(goi_hoc / "thong_tin_du_lieu.json", tt)
    (goi_hoc / gk.DAU_GOI_HOC).write_text(readme_hoc(tt), encoding="utf-8", newline="\n")
    gk.ghi_sha256sums(goi_hoc)
    sha_hoc = gk.nen_zip(goi_hoc, args.ra / f"{gk.TEN_GOI_HOC}{hau_to}.zip")
    print(f"Đã ghi {args.ra / (gk.TEN_GOI_HOC + hau_to + '.zip')} (sha256 {sha_hoc})")
    print(f"  train {tt['so_dong']['train']} dòng, val {tt['so_dong']['val']}, chỉ tổng hợp {tt['so_dong']['train_tong_hop']}; "
          f"đáp án đã chèn: train {tt['chen']['train']}, val {tt['chen']['val']}; sự việc dài nhất {tt['so_tu_su_viec']['toi_da']} từ")

    if args.gia:
        print("\nCHÚ Ý: đây là bản --gia (vector giả). Không tải lên Kaggle.")
    else:
        print("\nTiếp theo: tải hai zip lên Kaggle thành hai Dataset private (xem KE_HOACH_KAGGLE_V2.md).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
