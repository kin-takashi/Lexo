"""Đóng gói MẪU CON của cbba cho Kaggle (kế hoạch V3, kaggle/KE_HOACH_KAGGLE_V3.md): hai gói tách biệt, kèm SHA256SUMS.

  python scripts/dong_goi_cbba_kaggle.py --chi-chon     # chưa cần Ollama: chọn mẫu + cổng G0, ghi chon_mau.json, bao_cao_chon.md rồi dừng
  python scripts/dong_goi_cbba_kaggle.py                # cần Ollama + bge-m3: tìm ứng viên cho mọi mẫu, chọn K, ghi hai gói
  python scripts/dong_goi_cbba_kaggle.py --gia --so-test 50 --so-dev 20 --tran 5   # vector giả: chỉ thử đường ống (zip có hậu tố _GIA)

Đầu vào: inbox/cbba_blhs/nhan/{train,test}.jsonl (scripts/xu_ly_cbba_blhs.py) và chỉ mục db/chi_muc.sqlite.
Đầu ra (mặc định inbox/kaggle_cbba/):
  lexo_hoc_chon_dieu_cbba.zip   gói HỌC: sft_chon_train.jsonl (tập học theo trần mỗi Điều), sft_chon_val.jsonl (dev), kiem_giao.json
                                (mã + băm của vụ test). Cùng tên file đánh dấu và cùng định dạng với gói học V2 nên dùng lại notebook học.
  lexo_do_ban_an_cbba.zip       gói ĐO: mã nguồn, chỉ mục, vụ test + một phần dev kèm ứng viên đã xếp hạng, cho scripts/do_ban_an.py.
  chon_mau.json, bao_cao_chon.md   danh sách mã đã chọn, số liệu từng bước lọc, kết quả G0.
Chỉ gắn MỘT gói học vào notebook học (không gắn cùng lúc gói học V2); không bao giờ gắn gói đo vào notebook học.

Các bước (không bước nào nhìn điểm của mô hình): siêu dữ liệu 165 nghìn văn bản -> lọc (ngày >= 2018, Điều có trong chỉ mục, train <= --toi-da-ky-tu,
bỏ văn bản trùng chữ giữa train và test) -> dev theo nhóm vụ -> học theo trần mỗi Điều -> test mỗi nhóm vụ một văn bản, đủ --so-test sau khi
bỏ vụ có bản gần-trùng (độ chứa 5-gram >= 0,5) trong học + dev (và bỏ văn bản học / dev gần-trùng với 99 vụ test án lệ) -> G0 -> [tìm ứng viên: mỗi đoạn ~300 từ tìm riêng, gộp RRF] -> chọn chế độ + K
trên học + dev (K nhỏ nhất có «đủ đáp án trong top K» >= 90%, tối đa 30) -> SFT -> ghi gói.
Recall của test KHÔNG được tính hay in ở đây. Kết quả tìm ứng viên nhớ trong <ra>/_tam/xep_hang.jsonl (ghi nối): dừng giữa chừng thì chạy lại tiếp được.
Chạy lại với cùng đầu vào và tham số cho cùng danh sách mẫu. Đổi --so-test chỉ cắt ngắn / kéo dài cùng một danh sách test.
Thoát 0 nếu ổn; 1 nếu G0 phát hiện rò rỉ hoặc dữ liệu lỗi; 2 nếu ứng viên dưới sàn (vẫn ghi gói đo, không ghi gói học, trừ khi thêm --bo-qua-cong).
"""
from __future__ import annotations

import argparse
import bisect
import json
import shutil
import sys
import time
from collections import Counter, OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ban_an import cbba_kaggle as cb  # noqa: E402
from src.ban_an import chon_dieu as cd  # noqa: E402
from src.ban_an import goi_kaggle as gk  # noqa: E402
from src.config import index_path, load_config  # noqa: E402
from src.index.embedder import EmbedError, HashEmbedder, tu_config  # noqa: E402
from src.index.store import open_index  # noqa: E402

TEN_GOI_HOC, TEN_GOI_DO = "lexo_hoc_chon_dieu_cbba", "lexo_do_ban_an_cbba"      # khớp mẫu zip của notebook học / đo V2
PHIEN_BAN_META = 1
KAGGLE_DIR = ROOT / "kaggle"
SCRIPT_GOI_DO = ("do_ban_an.py",)


def _duong_dan(p: str | Path) -> Path:
    p = Path(p)
    return p if p.is_absolute() else ROOT / p


class NhoTam:
    """Bọc embedder: nhớ vài trăm đoạn gần nhất (một đoạn được nhúng cho cả chế độ vector lẫn fts), không để bộ nhớ phình theo số mẫu."""

    def __init__(self, emb, toi_da: int = 512):
        self.emb, self.name, self.toi_da, self.cache = emb, emb.name, toi_da, OrderedDict()

    def embed(self, texts):
        thieu = [t for t in dict.fromkeys(texts) if t not in self.cache]
        if thieu:
            for t, v in zip(thieu, self.emb.embed(thieu)):
                self.cache[t] = v
        ra = [self.cache[t] for t in texts]
        while len(self.cache) > self.toi_da:
            self.cache.popitem(last=False)
        return ra


class TieuDeTheoNgay:
    """cd.tieu_de_dieu theo ngày, nhớ theo «phiên bản hiệu lực» (các mốc hieu_luc_tu / hieu_luc_den) thay vì theo từng ngày."""

    def __init__(self, idx):
        self.idx = idx
        moc = {r[0] for r in idx.execute("SELECT hieu_luc_tu FROM chunk WHERE loai = 'dieu'")}
        moc |= {r[0] for r in idx.execute("SELECT hieu_luc_den FROM chunk WHERE loai = 'dieu' AND hieu_luc_den IS NOT NULL")}
        self.moc = sorted(m for m in moc if m)
        self.cache: dict[int, dict[str, str]] = {}

    def __call__(self, ngay: str | None) -> dict[str, str]:
        if ngay is None:
            return cd.tieu_de_dieu(self.idx, None)
        v = bisect.bisect_right(self.moc, ngay)
        if v not in self.cache:
            self.cache[v] = cd.tieu_de_dieu(self.idx, ngay)
        return self.cache[v]

    def tra_cuu_duoc(self, dieu, ngay) -> bool:
        td = self(ngay)
        return all(d in td for d in dieu)


def doc_tat_ca_meta(f: dict[str, Path], tam: Path) -> list[dict]:
    """Siêu dữ liệu mọi văn bản (cache theo kích thước + thời gian sửa của hai file nguồn)."""
    khoa = {t: [p.stat().st_size, p.stat().st_mtime_ns] for t, p in f.items()}
    cache = tam / "meta.json"
    if cache.exists():
        try:
            o = json.loads(cache.read_text(encoding="utf-8"))
            if o.get("phien_ban") == PHIEN_BAN_META and o.get("nguon") == khoa:
                print(f"[meta] dùng cache {cache} ({len(o['metas'])} văn bản)")
                return o["metas"]
        except ValueError:
            pass
    metas, t0 = [], time.time()
    for t, p in f.items():
        for i, m in enumerate(cb.doc_meta(p), 1):
            metas.append(m)
            if i % 20000 == 0:
                print(f"[meta] {t}: {i} ({time.time() - t0:.0f}s)", flush=True)
    tam.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"phien_ban": PHIEN_BAN_META, "nguon": khoa, "metas": metas}, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(f"[meta] {len(metas)} văn bản ({time.time() - t0:.0f}s)")
    return metas


def in_bang_recall(ten: str, bang: dict) -> list[str]:
    ks = sorted(next(iter(bang.values())))
    dong = [f"{ten}: phần mẫu có ĐỦ đáp án trong top K (trong ngoặc: phần Điều đáp án nằm trong top K)",
            "| chế độ | " + " | ".join(f"K={k}" for k in ks) + " |", "|---|" + "---|" * len(ks)]
    for c, theo_k in bang.items():
        dong.append(f"| {c} | " + " | ".join(f"{theo_k[k]['du']:.0%} ({theo_k[k]['recall']:.0%})" for k in ks) + " |")
    return dong


def readme_hoc(tt: dict) -> str:
    return f"""# Lexo — gói học «chọn Điều từ ứng viên», mẫu con cbba ({TEN_GOI_HOC})

Dùng cho notebook học (bản V3, `lexo_hoc_cbba.ipynb`; cùng định dạng gói với V2). Không có chữ của vụ test nào; `kiem_giao.json` chỉ chứa mã và
băm của {tt['so_mau']['test']} vụ test để notebook tự kiểm. Kiểm toàn vẹn: `sha256sum -c SHA256SUMS`. Chỉ gắn MỘT gói học vào notebook.

| File | Dòng | Dùng để |
|---|---|---|
| `sft_chon_train.jsonl` | {tt['so_dong']['train']} | học: {tt['so_mau']['hoc']} bản án (trần {tt['tham_so']['tran_moi_dieu']} văn bản mỗi Điều) |
| `sft_chon_val.jsonl` | {tt['so_dong']['val']} | val loss: {tt['so_mau']['dev']} bản án dev (chọn theo nhóm vụ, phân bố tự nhiên) |
| `thong_tin_du_lieu.json` | | K, chế độ ứng viên, số đáp án đã chèn, tham số chọn mẫu, mã băm nguồn |
| `kiem_giao.json` | | mã + băm sự việc của vụ test |

Ứng viên: chế độ `{tt['ung_vien']['che_do']}`, K = {tt['ung_vien']['k']}, xếp theo số Điều. Đáp án thiếu trong top K được chèn thay ứng viên hạng thấp nhất
({tt['chen']['train']} lần ở train, {tt['chen']['val']} lần ở val); dev/test lúc đo không bao giờ chèn.
Lời nhắc hệ thống: `{cd.PHIEN_BAN_TIN_NHAN}`, khớp từng ký tự với lúc đo.
"""


def readme_do(ch: dict) -> str:
    return f"""# Lexo — gói đo mẫu con cbba ({TEN_GOI_DO})

Dùng cho notebook đo (bản V3, `lexo_do_ban_an_cbba.ipynb`; cùng định dạng gói với V2): cổng G3/G4 trên dev và lượt test cuối. KHÔNG gắn gói này vào notebook học.
Kiểm toàn vẹn: `sha256sum -c SHA256SUMS`.

- `ban_an_do.json`: {ch['so_mau']['test']} vụ test + {ch['so_mau']['dev_do']} vụ dev, sự việc đã cắt, Điều tòa áp dụng, ứng viên đã xếp hạng (top 50 mỗi chế độ), tiêu đề Điều.
- `cau_hinh.json`: chế độ ứng viên `{ch['ung_vien']['che_do']}`, K = {ch['ung_vien']['k']}, lời nhắc, bảng Recall@K trên học + dev.
- `src/`, `scripts/do_ban_an.py`, `config.yaml`, `db/chi_muc.sqlite`: mã nguồn và chỉ mục đúng bản đã sinh ứng viên.

Chạy: `python scripts/do_ban_an.py --tap dev --cau-hinh A,C0,L --mo-hinh-chon <tên>` (G3/G4). Lượt test (`--tap test`) cần `--da-chot` và `cau_hinh_chot.json`.
"""


def ghi_bao_cao(p: Path, bc: dict) -> None:
    th = bc["tham_so"]
    d = [f"# Chọn mẫu con cbba cho Kaggle (V3)", "",
         f"Tham số: trần {th['tran_moi_dieu']} văn bản mỗi Điều, dev {th['so_dev']}, test {th['so_test']}, train <= {th['toi_da_ky_tu']} ký tự, "
         f"năm {th['nam_tu']}–{th['nam_den']}, hạt {th['seed']}, cấp giữ: {th['cap_giu']}.", "",
         "## Lọc (số văn bản bị loại, mỗi văn bản một lý do)", "", "| lý do | train | test |", "|---|---|---|"]
    for ly_do in cb.LY_DO:
        d.append(f"| {ly_do} | {bc['loai']['train'].get(ly_do, 0)} | {bc['loai']['test'].get(ly_do, 0)} |")
    d += ["", f"Còn lại sau lọc: train {bc['pool']['train']}, test {bc['pool']['test']} (test: {bc['pool']['nhom_test']} nhóm vụ).", "",
          "## Đã chọn", "", f"- học: {bc['so_mau']['hoc']} bản án; dev: {bc['so_mau']['dev']} (bỏ {len(bc['bo_gan_trung']['dev'])} vì gần-trùng với tập học); "
          f"test: {bc['so_mau']['test']} (bỏ {len(bc['bo_gan_trung']['test'])} ứng viên vì gần-trùng với học + dev).",
          f"- Điều trong tập học: {bc['phan_bo_dieu_hoc']['so_dieu']}; trung vị {bc['phan_bo_dieu_hoc'].get('trung_vi')} văn bản/Điều; "
          f"nhiều nhất {bc['phan_bo_dieu_hoc'].get('lon_nhat')}; Điều có dưới 10 văn bản học: {bc['phan_bo_dieu_hoc'].get('duoi_10')}.",
          f"- test có Điều chưa gặp ở học + dev: {bc['test_dieu_chua_gap']} vụ; nhiều Điều: {bc['test_nhieu_dieu']} vụ; "
          f"theo cấp: {bc['test_theo_cap']}; theo năm: {bc['test_theo_nam']}.",
          f"- ký tự đầu vào (trước khi cắt sự việc) của học: trung vị {bc['ky_tu_hoc']['trung_vi']}, lớn nhất {bc['ky_tu_hoc']['lon_nhat']}; "
          f"của test: trung vị {bc['ky_tu_test']['trung_vi']}, lớn nhất {bc['ky_tu_test']['lon_nhat']}.", "",
          "## G0 (rò rỉ test vào gói học)", "",
          (f"- giao với {bc['anle']['so_vu_test_anle']} vụ test án lệ (bộ test độc lập thứ hai): {len(bc['anle']['bi_loai'])} văn bản học / dev bị loại vì gần-trùng."
           if bc["anle"]["da_kiem"] else "- giao với 99 vụ test án lệ: KHÔNG kiểm (không có bộ bản án án lệ)."),
          f"- so {bc['g0']['so_mau_so_sanh']} mẫu học + dev với {bc['so_mau']['test']} vụ test: trùng id, trùng nhóm vụ, trùng băm, độ chứa 5-gram >= "
          f"{cb.NGUONG_GAN_TRUNG}: **{len(bc['g0']['loi'])} lỗi**."]
    d += [f"  - {x}" for x in bc["g0"]["loi"][:20]]
    p.write_text("\n".join(d) + "\n", encoding="utf-8", newline="\n")


def tom_do_dai(mau_meta: list[dict]) -> dict:
    v = sorted(m["n_ky_tu"] for m in mau_meta)
    return {"trung_vi": v[len(v) // 2], "lon_nhat": v[-1]} if v else {"trung_vi": 0, "lon_nhat": 0}


def main() -> int:
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vao", type=Path, default=Path("inbox/cbba_blhs/nhan"), help="thư mục có train.jsonl, test.jsonl (đầu ra của xu_ly_cbba_blhs.py)")
    ap.add_argument("--ra", type=Path, default=Path("inbox/kaggle_cbba"))
    ap.add_argument("--index", type=Path, default=None)
    ap.add_argument("--tran", type=int, default=cb.TRAN_MOI_DIEU, help="trần số văn bản học mỗi Điều")
    ap.add_argument("--so-dev", type=int, default=cb.SO_DEV)
    ap.add_argument("--so-dev-do", type=int, default=cb.SO_DEV_DO, help="số vụ dev đưa vào gói đo (G3/G4 trên Ollama)")
    ap.add_argument("--so-test", type=int, default=cb.SO_TEST)
    ap.add_argument("--toi-da-ky-tu", type=int, default=cb.TOI_DA_KY_TU, help="train: bỏ văn bản dài hơn (0 = không bỏ); test không bỏ gì")
    ap.add_argument("--nam-tu", type=int, default=cb.NAM_TU)
    ap.add_argument("--nam-den", type=int, default=cb.NAM_DEN)
    ap.add_argument("--cap-giu", default=None, help="chỉ giữ cấp trong danh sách (so_tham,phuc_tham,...), cách nhau dấu phẩy; mặc định tất cả")
    ap.add_argument("--seed", type=int, default=cb.SEED)
    ap.add_argument("--ban-an-anle", type=Path, default=None,
                    help="bộ bản án án lệ (inbox/anle_hf/ban_an_hinh_su.json): văn bản học / dev gần-trùng với 99 vụ test của nó bị bỏ; "
                         "mặc định dùng file đó nếu có")
    ap.add_argument("--khong-kiem-anle", action="store_true", help="không kiểm giao với 99 vụ test án lệ")
    ap.add_argument("--chi-chon", action="store_true", help="chỉ chọn mẫu + G0 (không cần Ollama)")
    ap.add_argument("--model", default=None, help="mô hình nhúng trong Ollama (mặc định theo config.yaml: bge-m3)")
    ap.add_argument("--endpoint", default=None)
    ap.add_argument("--gia", action="store_true", help="vector giả: chỉ thử đường ống")
    ap.add_argument("--bo-qua-cong", action="store_true", help="vẫn ghi gói học khi ứng viên dưới sàn (ghi rõ trong báo cáo)")
    a = ap.parse_args()

    vao, ra = _duong_dan(a.vao), _duong_dan(a.ra)
    f_vao = {t: vao / f"{t}.jsonl" for t in ("train", "test")}
    ip = _duong_dan(a.index) if a.index else index_path()
    for p in (*f_vao.values(), ip):
        if not p.exists():
            sys.exit(f"LỖI: không thấy {p}")
    if min(a.tran, a.so_dev, a.so_test) < 1 or a.so_dev_do < 0 or a.so_dev_do > a.so_dev:
        sys.exit("LỖI: --tran, --so-dev, --so-test phải >= 1 và 0 <= --so-dev-do <= --so-dev")
    cap_giu = {c.strip() for c in a.cap_giu.split(",") if c.strip()} if a.cap_giu else None

    # ---- 1. chọn mẫu -----------------------------------------------------------------------------------------------
    idx = open_index(ip)
    td_ngay = TieuDeTheoNgay(idx)
    metas = doc_tat_ca_meta(f_vao, ra / "_tam")
    pool, loai = cb.loc_pool(metas, nam_tu=a.nam_tu, nam_den=a.nam_den, toi_da_ky_tu=a.toi_da_ky_tu or None, cap_giu=cap_giu,
                             tra_cuu_duoc=td_ngay.tra_cuu_duoc)
    so_bo = cb.chon_so_bo(pool, tran=a.tran, so_dev=a.so_dev, seed=a.seed)
    hoc, dev, ung_test = so_bo["hoc"], so_bo["dev"], so_bo["ung_test"]
    if not hoc or not dev or len(ung_test) < a.so_test:
        sys.exit(f"LỖI: sau lọc chỉ còn {len(hoc)} văn bản học, {len(dev)} dev, {len(ung_test)} nhóm vụ test (cần {a.so_test})")
    print(f"[chọn] pool train {len(pool['train'])}, test {len(pool['test'])}; học {len(hoc)}, dev {len(dev)}, ứng viên test {len(ung_test)} nhóm vụ")

    ung_doc = ung_test[:int(a.so_test * cb.BIEN_AN_TEST) + 50]
    t0 = time.time()
    van_train = cb.doc_van_ban(f_vao["train"], {m["ma"] for m in hoc + dev})
    van_test = cb.doc_van_ban(f_vao["test"], {m["ma"] for m in ung_doc})
    print(f"[văn bản] đọc {len(van_train)} train + {len(van_test)} test ({time.time() - t0:.0f}s)")

    chi_muc = cb.ChiMucGanTrung()
    for m in hoc:
        chi_muc.them(m["ma"], van_train[m["ma"]])
    dev, dev_bo = cb.loc_dev_gan_trung(dev, van_train, chi_muc)
    if len(dev) < a.so_dev_do:
        sys.exit(f"LỖI: dev còn {len(dev)} < --so-dev-do {a.so_dev_do} sau khi bỏ vụ gần-trùng với tập học")
    for m in dev:
        chi_muc.them(m["ma"], van_train[m["ma"]])
    print(f"[gần-trùng] bỏ {len(dev_bo)} dev (trùng tập học)")

    vu_anle, trung_anle = {}, {}
    if not a.khong_kiem_anle:
        ap_anle = _duong_dan(a.ban_an_anle) if a.ban_an_anle else ROOT / "inbox" / "anle_hf" / "ban_an_hinh_su.json"
        if ap_anle.exists():
            vu_anle = {b["ma"]: b["dau_vao"] for b in json.loads(ap_anle.read_text(encoding="utf-8"))["mau"] if b.get("tap") == "test"}
            trung_anle = cb.loc_giao_anle(chi_muc, vu_anle)
        elif a.ban_an_anle:
            sys.exit(f"LỖI: không thấy {ap_anle}")
        else:
            print(f"CẢNH BÁO: không thấy {ap_anle}: BỎ QUA kiểm giao với 99 vụ test án lệ (thêm --khong-kiem-anle để tắt cảnh báo)")
    if trung_anle:
        hoc = [m for m in hoc if m["ma"] not in trung_anle]
        dev = [m for m in dev if m["ma"] not in trung_anle]
        if len(dev) < a.so_dev_do or not hoc:
            sys.exit(f"LỖI: sau khi bỏ {len(trung_anle)} văn bản trùng với test án lệ, dev còn {len(dev)} (cần >= {a.so_dev_do}), học còn {len(hoc)}")
        chi_muc = cb.ChiMucGanTrung()
        for m in hoc + dev:
            chi_muc.them(m["ma"], van_train[m["ma"]])
    print(f"[án lệ] {len(vu_anle)} vụ test án lệ so với học + dev: bỏ {len(trung_anle)} văn bản gần-trùng")
    test, test_bo = cb.loc_gan_trung_test(ung_doc, van_test, chi_muc, a.so_test)
    print(f"[gần-trùng] test {len(test)} vụ, bỏ {len(test_bo)} ứng viên (trùng học + dev); chỉ mục {len(chi_muc)} văn bản ({time.time() - t0:.0f}s)")

    dieu_da_hoc = {d for m in hoc + dev for d in m["dieu"]}
    mau_hoc = [cb.mau_cbba(m, van_train[m["ma"]], "hoc") for m in hoc]
    mau_dev = [cb.mau_cbba(m, van_train[m["ma"]], "dev") for m in dev]
    mau_test = [cb.mau_cbba(m, van_test[m["ma"]], "test", dieu_da_hoc) for m in test]
    cb.gan_tan_suat(mau_hoc + mau_dev + mau_test, Counter(d for m in hoc for d in m["dieu"]))
    loi_g0 = cb.kiem_giao_cbba(mau_test, mau_hoc + mau_dev, chi_muc, {x["id"]: x["dau_vao_goc"] for x in mau_test})

    ids = {"hoc": [m["ma"] for m in hoc], "dev": [m["ma"] for m in dev], "dev_do": [m["ma"] for m in dev[:a.so_dev_do]],
           "test": [m["ma"] for m in test]}
    bc = {"tham_so": {"tran_moi_dieu": a.tran, "so_dev": a.so_dev, "so_dev_do": a.so_dev_do, "so_test": a.so_test, "toi_da_ky_tu": a.toi_da_ky_tu,
                      "nam_tu": a.nam_tu, "nam_den": a.nam_den, "cap_giu": sorted(cap_giu) if cap_giu else "tat_ca", "seed": a.seed,
                      "nguong_gan_trung": cb.NGUONG_GAN_TRUNG},
          "loai": {t: dict(c) for t, c in loai.items()},
          "pool": {"train": len(pool["train"]), "test": len(pool["test"]), "nhom_test": len(ung_test)},
          "so_mau": {"hoc": len(hoc), "dev": len(dev), "dev_do": a.so_dev_do, "test": len(test)},
          "bo_gan_trung": {"dev": dev_bo, "test": test_bo},
          "anle": {"so_vu_test_anle": len(vu_anle), "da_kiem": bool(vu_anle), "bi_loai": trung_anle},
          "phan_bo_dieu_hoc": cb.phan_bo(Counter(d for m in hoc for d in m["dieu"])),
          "test_dieu_chua_gap": sum(x["dieu_chua_gap"] for x in mau_test), "test_nhieu_dieu": sum(len(x["dieu"]) > 1 for x in mau_test),
          "test_theo_cap": dict(Counter(x["cap"] for x in mau_test)), "test_theo_nam": dict(sorted(Counter(x["nam"] for x in mau_test).items())),
          "ky_tu_hoc": tom_do_dai(hoc), "ky_tu_test": tom_do_dai(test),
          "g0": {"so_mau_so_sanh": len(mau_hoc) + len(mau_dev), "so_vu_test": len(mau_test), "loi": loi_g0},
          "sha256_nguon": {"train.jsonl": gk.sha256_file(f_vao["train"]), "test.jsonl": gk.sha256_file(f_vao["test"]),
                           "chi_muc.sqlite": gk.sha256_file(ip)}}
    ra.mkdir(parents=True, exist_ok=True)
    gk.ghi_json(ra / "chon_mau.json", {"phien_ban": 1, **bc, "id": ids})
    ghi_bao_cao(ra / "bao_cao_chon.md", bc)
    print((ra / "bao_cao_chon.md").read_text(encoding="utf-8"))
    if loi_g0:
        print("LỖI G0 (rò rỉ test vào gói học): " + "; ".join(loi_g0[:10]))
        return 1
    print(f"G0: 0 vụ test dính vào gói học (id, nhóm vụ, băm, độ chứa 5-gram >= {cb.NGUONG_GAN_TRUNG}; {len(mau_hoc) + len(mau_dev)} mẫu so sánh)")
    if a.chi_chon:
        print(f"\nĐã ghi {ra / 'chon_mau.json'} và {ra / 'bao_cao_chon.md'}. Bỏ --chi-chon để tìm ứng viên và đóng gói.")
        return 0

    # ---- 2. ứng viên -----------------------------------------------------------------------------------------------
    emb = NhoTam(HashEmbedder() if a.gia else tu_config(load_config(), model=a.model, endpoint=a.endpoint))
    cache = cb.CacheXepHang(ra / "_tam" / ("xep_hang_gia.jsonl" if a.gia else "xep_hang.jsonl"))
    tat_ca = mau_hoc + mau_dev + mau_test
    t0 = time.time()
    da_co = len(cache)

    def bao(i: int, n: int) -> None:
        if i % 50 == 0 or i == n:
            cache.flush()
            print(f"  tìm ứng viên {i}/{n} ({time.time() - t0:.0f}s)", flush=True)

    print(f"Tìm ứng viên cho {len(tat_ca)} mẫu bằng {emb.name} + FTS5 (đã nhớ sẵn {da_co} kết quả)...")
    try:
        gk.gan_xep_hang(tat_ca, lambda chu, ngay: cd.xep_hang_dieu(idx, emb, chu, ngay), cache, emb.name, bao)
    except (EmbedError, ValueError) as e:
        cache.flush()
        sys.exit(f"LỖI: {e} (kết quả đã tìm được lưu trong {cache.duong_dan}; chạy lại để tiếp tục)")
    finally:
        cache.flush()
        cache.dong()

    hoc_dev = mau_hoc + mau_dev
    bang = cd.bang_recall(hoc_dev)
    chon = cd.chon_k(bang)
    bang_dev = cd.bang_recall(mau_dev)
    for d in in_bang_recall("tập học + dev", bang) + [""] + in_bang_recall("riêng dev (phân bố tự nhiên)", bang_dev):
        print(d)
    print(f"\nChọn: chế độ {chon['che_do']}, K = {chon['k']} ({'đạt' if chon['dat_muc'] else 'KHÔNG đạt'} mức {cd.RECALL_MUC:.0%}; "
          f"đủ đáp án trong top {chon['k_toi_da']}: {chon['du_tai_k_toi_da']:.0%})")
    duoi_san = chon["du_tai_k_toi_da"] < cd.RECALL_SAN
    if duoi_san:
        print(f"CẢNH BÁO: dưới sàn {cd.RECALL_SAN:.0%}: bộ sinh ứng viên là nút thắt. Theo kế hoạch: sửa truy hồi trước, hoãn học.")

    def tieu_de(x: dict) -> dict[str, str]:
        return td_ngay(x["ngay_tra_cuu"])

    loi = [f"{x['id']}: Điều {d} không có trong chỉ mục tại ngày {x['ngay_tra_cuu']}" for x in tat_ca for d in x["dieu"] if d not in tieu_de(x)]
    if loi:
        sys.exit("LỖI: " + "; ".join(loi[:5]))

    # ---- 3. gói ĐO -------------------------------------------------------------------------------------------------
    hau_to = "_GIA" if a.gia else ""
    goi_do = ra / TEN_GOI_DO
    if goi_do.exists():
        shutil.rmtree(goi_do)
    goi_do.mkdir(parents=True)
    mau_do = []
    for x in mau_dev[:a.so_dev_do] + mau_test:
        td = tieu_de(x)
        can = {d for v in x["xep_hang"].values() for d in v} | set(x["dieu"])
        mau_do.append({k: x[k] for k in ("id", "tap", "su_viec", "da_cat", "so_tu_goc", "dieu", "nhom_vu", "ngay", "ngay_tra_cuu",
                                         "ten_toi_trong_loi_ke", "dieu_chua_gap", "xep_hang", "cap", "nam", "tan_suat_dieu_hoc")}
                      | {"tieu_de": {d: td[d] for d in cd.sap_xep(can) if d in td}})
    gk.ghi_json(goi_do / "ban_an_do.json", {"phien_ban": 1, "nguon": cb.NGUON_CBBA, "seed": a.seed, "mau": mau_do})
    so_mau = {"hoc": len(mau_hoc), "dev": len(mau_dev), "dev_do": a.so_dev_do, "test": len(mau_test)}
    cau_hinh = {"phien_ban_tin_nhan": cd.PHIEN_BAN_TIN_NHAN, "he_thong_chon": cd.HE_THONG_CHON, "so_tu_dau": cd.SO_TU_DAU,
                "so_tu_cuoi": cd.SO_TU_CUOI, "doan_tu": cd.DOAN_TU, "rrf_k": cd.RRF_K, "mo_hinh_nhung": emb.name, "gia": a.gia,
                "bo_du_lieu": cb.NGUON_CBBA, "so_mau": so_mau, "tham_so_chon": bc["tham_so"],
                "ung_vien": {"che_do": chon["che_do"], "k": chon["k"]}, "chon_k": chon,
                "recall_hoc_dev": {c: {str(k): v for k, v in t.items()} for c, t in bang.items()},
                "recall_dev": {c: {str(k): v for k, v in t.items()} for c, t in bang_dev.items()},
                "sha256": {"ban_an_do.json": gk.sha256_file(goi_do / "ban_an_do.json"), "chi_muc.sqlite": gk.sha256_file(ip),
                           "train.jsonl": bc["sha256_nguon"]["train.jsonl"], "test.jsonl": bc["sha256_nguon"]["test.jsonl"]}}
    gk.ghi_json(goi_do / "cau_hinh.json", cau_hinh)
    gk.chep_ma_nguon(ROOT, goi_do, SCRIPT_GOI_DO)
    (goi_do / "db").mkdir(exist_ok=True)
    shutil.copyfile(ip, goi_do / "db" / "chi_muc.sqlite")
    (goi_do / gk.DAU_GOI_DO).write_text(readme_do(cau_hinh), encoding="utf-8", newline="\n")
    gk.ghi_sha256sums(goi_do)
    sha_do = gk.nen_zip(goi_do, ra / f"{TEN_GOI_DO}{hau_to}.zip")
    print(f"\nĐã ghi {ra / (TEN_GOI_DO + hau_to + '.zip')} (sha256 {sha_do})")
    for p in sorted(KAGGLE_DIR.glob("*")) if KAGGLE_DIR.exists() else []:
        if p.is_file() and p.suffix in (".ipynb", ".md") and ("cbba" in p.name or "V3" in p.name):
            shutil.copyfile(p, ra / p.name)
            print(f"Đã chép {p.name}")

    if duoi_san and not a.bo_qua_cong:
        print("Chưa ghi gói học (ứng viên dưới sàn). Thêm --bo-qua-cong nếu vẫn muốn học.")
        return 2

    # ---- 4. gói HỌC ------------------------------------------------------------------------------------------------
    k, che_do = chon["k"], chon["che_do"]
    dong = {t: [gk.dong_sft(x, che_do, k, tieu_de(x)) for x in ds] for t, ds in (("train", mau_hoc), ("val", mau_dev))}
    goi_hoc = ra / TEN_GOI_HOC
    if goi_hoc.exists():
        shutil.rmtree(goi_hoc)
    goi_hoc.mkdir(parents=True)
    for t, ds in dong.items():
        gk.ghi_jsonl(goi_hoc / f"sft_chon_{t}.jsonl", ds)
    gk.ghi_json(goi_hoc / "kiem_giao.json", {"ghi_chu": "mã và sha256 sự việc (đã cắt) của vụ test; notebook học kiểm không dòng nào trùng",
                                            "ma_test": sorted(x["id"] for x in mau_test),
                                            "sha256_su_viec_test": sorted(cd.bam_chu(x["su_viec"]) for x in mau_test)})
    so_tu = [r["so_tu_su_viec"] for r in dong["train"] + dong["val"]]
    tt = {"phien_ban_tin_nhan": cd.PHIEN_BAN_TIN_NHAN, "he_thong_chon": cd.HE_THONG_CHON, "gia": a.gia, "bo_du_lieu": cb.NGUON_CBBA,
          "ung_vien": {"che_do": che_do, "k": k}, "chon_k": chon, "tham_so": bc["tham_so"],
          "so_mau": so_mau, "so_dong": {t: len(ds) for t, ds in dong.items()},
          "chen": {t: sum(r["chen"] for r in ds) for t, ds in dong.items()},
          "dong_co_chen": {t: sum(1 for r in ds if r["chen"]) for t, ds in dong.items()},
          "ban_an_bi_cat": {"train": sum(x["da_cat"] for x in mau_hoc), "val": sum(x["da_cat"] for x in mau_dev)},
          "so_tu_su_viec": {"toi_da": max(so_tu), "trung_binh": round(sum(so_tu) / len(so_tu), 1)},
          "so_tu_dau": cd.SO_TU_DAU, "so_tu_cuoi": cd.SO_TU_CUOI,
          "phan_bo_dieu_hoc": bc["phan_bo_dieu_hoc"], "id": {"hoc": ids["hoc"], "dev": ids["dev"]},
          "sha256_nguon": bc["sha256_nguon"], "g0": bc["g0"]}
    gk.ghi_json(goi_hoc / "thong_tin_du_lieu.json", tt)
    (goi_hoc / gk.DAU_GOI_HOC).write_text(readme_hoc(tt), encoding="utf-8", newline="\n")
    gk.ghi_sha256sums(goi_hoc)
    sha_hoc = gk.nen_zip(goi_hoc, ra / f"{TEN_GOI_HOC}{hau_to}.zip")
    print(f"Đã ghi {ra / (TEN_GOI_HOC + hau_to + '.zip')} (sha256 {sha_hoc})")
    print(f"  train {tt['so_dong']['train']} dòng, val {tt['so_dong']['val']}; đáp án đã chèn: train {tt['chen']['train']}, val {tt['chen']['val']}; "
          f"sự việc dài nhất {tt['so_tu_su_viec']['toi_da']} từ, TB {tt['so_tu_su_viec']['trung_binh']}")
    if a.gia:
        print("\nCHÚ Ý: đây là bản --gia (vector giả). Không tải lên Kaggle.")
    else:
        print("\nTiếp theo: tải hai zip lên Kaggle thành hai Dataset private (xem kaggle/KE_HOACH_KAGGLE_V3.md).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
