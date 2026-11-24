"""Baseline T (bài báo, lộ trình v3): TF-IDF + bộ phân loại tuyến tính dự đoán Điều BLHS từ sự việc đã che, không LLM, chạy CPU.

  python scripts/baseline_tfidf.py --muc hoc        # chỉ 3.526 văn bản học (bằng dữ liệu của L)
  python scripts/baseline_tfidf.py --muc toan_bo    # mọi văn bản train hợp lệ (trừ nhóm vụ dev)
  python scripts/baseline_tfidf.py --muc toan_bo --tap test --da-chot   # test: CHỈ chạy một lần, sau khi khoá giao thức

Đầu vào mặc định: inbox/cbba_blhs/train.jsonl.gz, test.jsonl.gz (scripts/xu_ly_cbba_blhs.py) và inbox/kaggle_cbba/chon_mau.json
(id học / dev / dev_do / test). Chữ đưa vào giống hệt chữ C0 / L đọc: chon_dieu.cat_su_viec (1.400 từ đầu + 600 từ cuối).
Nhãn = các Điều 108–425 của văn bản; văn bản không còn Điều nào trong khoảng đó bị bỏ. Chỉ lấy bản án 2018–2026 (số Điều BLHS 2015).

Mô hình: HashingVectorizer (âm tiết 1–2 gram, 2^20 chiều) + idf + tf dưới tuyến tính + chuẩn L2, rồi SGDClassifier hinge có lấy
trung bình (một-với-còn-lại), học theo khối 4.096 văn bản trong 10 lượt, nên chạy được với ~100 nghìn văn bản trên máy 16 GB. Văn bản nhiều Điều được nhân thành nhiều mẫu, mỗi mẫu một Điều. Dự đoán = Điều điểm cao nhất (top 1),
vì 95% vụ dev chỉ có một Điều; `xep_hang` giữ top 10 để tính Recall@K. Không tham số nào được chọn theo điểm dev / test.

Đầu ra (--ra, mặc định inbox/kaggle_ket_qua/baseline_T/<tập>/): T_<muc>.jsonl cùng dạng kết quả scripts/do_ban_an.py (đọc được bằng
scripts/phan_tich_cbba.py) và bao_cao_T_<muc>.md: micro P/R/F1, khớp đúng, tìm đủ, Acc@1, Recall@5/10; nếu --so-voi có C0.jsonl /
L.jsonl thì thêm các chỉ số đó tính trên cùng vụ và McNemar chính xác trên «khớp đúng».

Cần thêm: pip install scikit-learn==1.7.2 (không nằm trong requirements.txt vì chức năng chính không dùng).
"""
from __future__ import annotations

import argparse
import gzip
import json
import math
import sys
import time
from collections.abc import Iterable, Iterator, Sequence
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.ban_an import chon_dieu as cd  # noqa: E402

TIEN_TO_ID = "cbba_"
NAM_TU, NAM_DEN = 2018, 2026
SO_CHIEU = 2 ** 20
NGRAM = (1, 2)
ALPHA = 1e-5
EPOCH = 10
KHOI = 4096
SEED = 2026
TOP_K = 10
TAP = ("dev_do", "dev", "test")
MUC = ("hoc", "toan_bo")


class BaselineError(ValueError):
    pass


# --------------------------------------------------------------------------------------------------------------------
# Đọc dữ liệu
# --------------------------------------------------------------------------------------------------------------------


def mo(p: Path):
    return gzip.open(p, "rt", encoding="utf-8") if p.suffix == ".gz" else open(p, encoding="utf-8")


def doc_jsonl(p: Path) -> Iterator[dict]:
    with mo(p) as f:
        for dong in f:
            if dong.strip():
                yield json.loads(dong)


def ngay_hop_le(ngay: str | None) -> bool:
    try:
        return NAM_TU <= date.fromisoformat(ngay or "").year <= NAM_DEN
    except ValueError:
        return False


def nhan(r: dict) -> list[str]:
    dieu = r["dieu"] if isinstance(r["dieu"], list) else [r["dieu"]]
    return cd.sap_xep(str(d) for d in dieu if cd.la_dieu_toi_pham(str(d)))


def chu_vao(r: dict) -> str:
    return cd.cat_su_viec(r["dau_vao"])[0]


def doc_train(p: Path, muc: str, id_hoc: set[str], id_dev: set[str]) -> tuple[list[str], list[list[str]], dict]:
    """(chữ, nhãn, thống kê) của tập học. `muc` = 'hoc': đúng các mã trong id_hoc; 'toan_bo': mọi văn bản train hợp lệ, bỏ mọi văn bản
    thuộc nhóm vụ có mặt trong dev (nhóm vụ dev đọc ở lượt đầu, nên đọc file hai lượt để không giữ chữ của văn bản bị bỏ)."""
    if muc not in MUC:
        raise BaselineError(f"muc = {muc!r}")
    nhom_dev: set[str] = set()
    if muc == "toan_bo":
        for r in doc_jsonl(p):
            if str(r["ma"]) in id_dev:
                nhom_dev.add(str(r.get("nhom_vu") or r["ma"]))
        if len(nhom_dev) == 0 and id_dev:
            raise BaselineError(f"{p.name}: không thấy văn bản dev nào; sai file train?")
    chu, y = [], []
    tk = {"doc": 0, "sai_ngay": 0, "khong_nhan": 0, "nhom_dev": 0, "khac_tap": 0, "giu": 0}
    for r in doc_jsonl(p):
        tk["doc"] += 1
        ma = str(r["ma"])
        if r.get("tap", "train") != "train":
            tk["khac_tap"] += 1
            continue
        if muc == "hoc":
            if ma not in id_hoc:
                continue
        else:
            if str(r.get("nhom_vu") or ma) in nhom_dev:
                tk["nhom_dev"] += 1
                continue
            if not ngay_hop_le(r.get("ngay")):
                tk["sai_ngay"] += 1
                continue
        n = nhan(r)
        if not n:
            tk["khong_nhan"] += 1
            continue
        chu.append(chu_vao(r))
        y.append(n)
    tk["giu"] = len(chu)
    if muc == "hoc" and len(chu) != len(id_hoc):
        raise BaselineError(f"chỉ đọc được {len(chu)}/{len(id_hoc)} văn bản học")
    return chu, y, tk


def doc_danh_gia(p: Path, can: Sequence[str]) -> list[dict]:
    """Các văn bản cần đánh giá theo đúng thứ tự `can`: [{id, chu, dieu}]."""
    tim = set(can)
    gap: dict[str, dict] = {}
    for r in doc_jsonl(p):
        ma = str(r["ma"])
        if ma in tim:
            gap[ma] = {"id": TIEN_TO_ID + ma, "chu": chu_vao(r), "dieu": nhan(r)}
            if len(gap) == len(tim):
                break
    thieu = tim - set(gap)
    if thieu:
        raise BaselineError(f"{p.name}: thiếu {len(thieu)} mã, ví dụ {sorted(thieu)[:3]}")
    return [gap[m] for m in can]


# --------------------------------------------------------------------------------------------------------------------
# Mô hình
# --------------------------------------------------------------------------------------------------------------------


def nhan_doi(chu: Sequence[str], y: Sequence[Sequence[str]]) -> tuple[list[int], list[str]]:
    """Văn bản nhiều Điều thành nhiều mẫu: (chỉ số văn bản của mỗi mẫu, Điều của mẫu)."""
    idx, lop = [], []
    for i, ds in enumerate(y):
        for d in ds:
            idx.append(i)
            lop.append(d)
    return idx, lop


class MoHinh:
    """TF-IDF trên đặc trưng băm (idf và chuẩn hoá L2 tự làm, để học theo từng khối) + SGDClassifier hinge có lấy trung bình."""

    def __init__(self, idf, clf):
        self.idf, self.clf = idf, clf
        self.classes_ = clf.classes_

    def bien_doi(self, chu: Sequence[str]):
        return tf_idf(dem_bam(chu), self.idf)


def bo_bam():
    import numpy as np
    from sklearn.feature_extraction.text import HashingVectorizer

    return HashingVectorizer(n_features=SO_CHIEU, ngram_range=NGRAM, alternate_sign=False, norm=None, lowercase=True,
                             token_pattern=r"(?u)\b\w+\b", dtype=np.float32)


def dem_bam(chu: Sequence[str]):
    return bo_bam().transform(chu)


def tf_idf(X, idf):
    """tf dưới tuyến tính (1 + log tf) × idf, rồi chuẩn hoá L2 từng dòng (như TfidfTransformer(sublinear_tf=True))."""
    import numpy as np
    from sklearn.preprocessing import normalize

    X = X.copy()
    X.data = (1.0 + np.log(X.data)).astype(X.dtype)
    X = X.multiply(idf).tocsr()
    return normalize(X, copy=False)


def hoc(chu: Sequence[str], y: Sequence[Sequence[str]], epoch: int = EPOCH, alpha: float = ALPHA, khoi: int = KHOI, bao=None):
    """Học theo khối để bộ nhớ không phụ thuộc số văn bản: xáo thứ tự (hạt cố định), băm từng khối, tính idf, rồi `epoch` lượt
    partial_fit (thứ tự khối và thứ tự dòng trong khối xáo lại mỗi lượt). Tham số cố định trước, không chọn theo điểm."""
    import numpy as np
    from sklearn.linear_model import SGDClassifier

    lop_tat_ca = sorted({d for ds in y for d in ds}, key=cd.khoa_so)
    if len(lop_tat_ca) < 2:
        raise BaselineError("cần ít nhất 2 Điều khác nhau để học")
    rng = np.random.RandomState(SEED)
    thu_tu = rng.permutation(len(chu))
    cac_khoi, nhan_khoi = [], []
    df = np.zeros(SO_CHIEU, dtype=np.int64)
    for a in range(0, len(thu_tu), khoi):
        idx = thu_tu[a:a + khoi]
        X = dem_bam([chu[i] for i in idx])
        df += np.bincount(X.indices, minlength=SO_CHIEU)
        cac_khoi.append(X)
        nhan_khoi.append([y[i] for i in idx])
    n = len(chu)
    idf = (np.log((1 + n) / (1 + df)) + 1).astype(np.float32)
    for k, X in enumerate(cac_khoi):
        cac_khoi[k] = tf_idf(X, idf)
    clf = SGDClassifier(loss="hinge", alpha=alpha, average=True, random_state=SEED, n_jobs=-1)
    lop = np.array(lop_tat_ca, dtype=object)
    for e in range(epoch):
        for k in rng.permutation(len(cac_khoi)):
            X, ys = cac_khoi[k], nhan_khoi[k]
            dong, nh = nhan_doi(range(X.shape[0]), ys)
            p = rng.permutation(len(dong))
            clf.partial_fit(X[np.asarray(dong)[p]], np.asarray(nh, dtype=object)[p], classes=lop)
        if bao:
            bao(f"  lượt {e + 1}/{epoch}")
    return MoHinh(idf, clf)


def xep_hang(mh: MoHinh, chu: Sequence[str], k: int = TOP_K, khoi: int = KHOI) -> list[list[str]]:
    ra = []
    for a in range(0, len(chu), khoi):
        ra += _xep_hang_khoi(mh.clf, mh.bien_doi(chu[a:a + khoi]), k)
    return ra


def _xep_hang_khoi(clf, X, k: int) -> list[list[str]]:
    import numpy as np

    diem = clf.decision_function(X)
    if diem.ndim == 1:                                  # hai lớp: sklearn trả một cột
        diem = np.stack([-diem, diem], axis=1)
    lop = [str(x) for x in clf.classes_]
    ra = []
    for hang in diem:
        thu_tu = sorted(range(len(lop)), key=lambda j: (-hang[j], cd.khoa_so(lop[j])))[:k]
        ra.append([lop[j] for j in thu_tu])
    return ra


# --------------------------------------------------------------------------------------------------------------------
# Chấm
# --------------------------------------------------------------------------------------------------------------------


def cham(dap_an: Sequence[str], hien_thi: Sequence[str]) -> dict:
    """Cùng định nghĩa với scripts/do_ban_an.py: tìm đủ, bao phủ, chính xác, khớp đúng."""
    g, p = set(dap_an), set(hien_thi)
    return {"tim_du": float(g <= p), "bao_phu": len(g & p) / len(g) if g else 0.0, "chinh_xac": len(g & p) / len(p) if p else 0.0,
            "so_hien_thi": len(p), "khop_dung": float(g == p), "thieu": cd.sap_xep(g - p)}


def chi_so(cap: Iterable[tuple[Sequence[str], Sequence[str]]]) -> dict:
    """Micro P/R/F1 trên tập Điều, khớp đúng, tìm đủ, số Điều hiển thị TB. cap = (đáp án, hiển thị)."""
    tp = fp = fn = em = du = n = sh = 0
    for g, p in cap:
        g, p = set(g), set(p)
        tp += len(g & p)
        fp += len(p - g)
        fn += len(g - p)
        em += g == p
        du += g <= p
        sh += len(p)
        n += 1
    P = tp / (tp + fp) if tp + fp else 0.0
    R = tp / (tp + fn) if tp + fn else 0.0
    return {"n": n, "micro_p": P, "micro_r": R, "micro_f1": 2 * P * R / (P + R) if P + R else 0.0,
            "khop_dung": em / n if n else 0.0, "tim_du": du / n if n else 0.0, "hien_thi_tb": sh / n if n else 0.0}


def recall_k(cap: Iterable[tuple[Sequence[str], Sequence[str]]], k: int) -> float:
    """Phần vụ có MỌI Điều đáp án trong top k của xếp hạng."""
    ds = [set(g) <= set(x[:k]) for g, x in cap]
    return sum(ds) / len(ds) if ds else 0.0


def mcnemar_p(thang: int, thua: int) -> float:
    n = thang + thua
    if n == 0:
        return 1.0
    k = min(thang, thua)
    return min(1.0, 2 * sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n)


# --------------------------------------------------------------------------------------------------------------------
# Báo cáo
# --------------------------------------------------------------------------------------------------------------------


def doc_ket_qua(p: Path) -> dict[str, dict]:
    return {r["id"]: r for r in doc_jsonl(p)} if p.exists() else {}


def dong_bang(ten: str, c: dict, extra: str = "") -> str:
    return (f"| {ten} | {c['n']} | {c['micro_p']:.3f} | {c['micro_r']:.3f} | {c['micro_f1']:.3f} | {c['khop_dung']:.1%} | "
            f"{c['tim_du']:.1%} | {c['hien_thi_tb']:.2f} |{extra}")


def bao_cao(ten: str, tap: str, dong: Sequence[dict], tk: dict, so_voi: dict[str, dict[str, dict]], giay: dict) -> str:
    cap = [(r["dieu"], r["hien_thi"]) for r in dong]
    cap_x = [(r["dieu"], r["xep_hang"]) for r in dong]
    c = chi_so(cap)
    l = [f"# Baseline {ten} trên {tap} — {len(dong)} vụ", "",
         f"TF-IDF (âm tiết 1–2 gram, băm 2^20) + SGD hinge có lấy trung bình (alpha={ALPHA}, {EPOCH} lượt); hiển thị top 1. Học trên {tk['giu']} văn bản "
         f"({json.dumps(tk, ensure_ascii=False)}). Học {giay['hoc']:.0f} giây, dự đoán {giay['du_doan']:.0f} giây.", "",
         "| cấu hình | n | micro P | micro R | micro F1 | khớp đúng | tìm đủ | Điều hiển thị TB |", "|---|---|---|---|---|---|---|---|",
         dong_bang(ten, c)]
    id_ta = {r["id"]: r for r in dong}
    so_sanh = []
    for ten_k, kq in so_voi.items():
        chung = [i for i in id_ta if i in kq]
        if not chung:
            continue
        ck = chi_so((kq[i]["dieu"], kq[i]["hien_thi"]) for i in chung)
        l.append(dong_bang(f"{ten_k} (cùng {len(chung)} vụ)", ck))
        ta_dung = {i: set(id_ta[i]["dieu"]) == set(id_ta[i]["hien_thi"]) for i in chung}
        ho_dung = {i: set(kq[i]["dieu"]) == set(kq[i]["hien_thi"]) for i in chung}
        thang = sum(ta_dung[i] and not ho_dung[i] for i in chung)
        thua = sum(ho_dung[i] and not ta_dung[i] for i in chung)
        so_sanh.append(f"| {ten} so với {ten_k} | {len(chung)} | {thang} / {thua} | {mcnemar_p(thang, thua):.4f} |")
    l += ["", "## Xếp hạng của bộ phân loại", "", "| Acc@1 | Recall@3 | Recall@5 | Recall@10 |", "|---|---|---|---|",
          f"| {recall_k(cap_x, 1):.1%} | {recall_k(cap_x, 3):.1%} | {recall_k(cap_x, 5):.1%} | {recall_k(cap_x, 10):.1%} |"]
    if so_sanh:
        l += ["", "## McNemar chính xác trên «khớp đúng»", "", "| so sánh | vụ chung | thắng / thua | p |", "|---|---|---|---|", *so_sanh]
    l += ["", "Chỉ mô tả. Không tham số nào ở đây được chọn theo điểm này."]
    return "\n".join(l) + "\n"


# --------------------------------------------------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--train", type=Path, default=ROOT / "inbox/cbba_blhs/train.jsonl.gz")
    ap.add_argument("--test", type=Path, default=ROOT / "inbox/cbba_blhs/test.jsonl.gz")
    ap.add_argument("--chon", type=Path, default=ROOT / "inbox/kaggle_cbba/chon_mau.json")
    ap.add_argument("--muc", choices=MUC, default="hoc")
    ap.add_argument("--tap", choices=TAP, default="dev_do")
    ap.add_argument("--da-chot", action="store_true", help="bắt buộc với --tap test: xác nhận giao thức đã khoá, test chạy một lần")
    ap.add_argument("--so-voi", type=Path, default=None, help="thư mục có C0.jsonl, L.jsonl cùng tập (vd. kết quả dev 100 từ Kaggle)")
    ap.add_argument("--ra", type=Path, default=None)
    a = ap.parse_args(argv)
    if a.tap == "test" and not a.da_chot:
        print("Từ chối: --tap test cần --da-chot (giao thức V3: test chỉ chạy một lần, sau khi khoá cấu hình).", file=sys.stderr)
        return 2
    chon = json.loads(a.chon.read_text(encoding="utf-8"))["id"]
    ten = f"T_{a.muc}"
    ra = a.ra or ROOT / "inbox/kaggle_ket_qua/baseline_T" / a.tap
    ra.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    chu, y, tk = doc_train(a.train, a.muc, set(map(str, chon["hoc"])), set(map(str, chon["dev"])))
    print(f"[1/3] đọc {tk['giu']} văn bản học ({time.time() - t0:.0f} giây): {tk}", flush=True)
    t1 = time.time()
    mh = hoc(chu, y, bao=lambda m: print(m, flush=True))
    del chu
    giay_hoc = time.time() - t1
    print(f"[2/3] học xong {len(mh.classes_)} Điều ({giay_hoc:.0f} giây)", flush=True)

    nguon = a.test if a.tap == "test" else a.train
    vu = doc_danh_gia(nguon, [str(m) for m in chon[a.tap]])
    t2 = time.time()
    hang = xep_hang(mh, [v["chu"] for v in vu])
    giay_dd = time.time() - t2
    dong = []
    for v, h in zip(vu, hang):
        hien = h[:1]
        dong.append({"id": v["id"], "cau_hinh": ten, "dieu": v["dieu"], "hien_thi": hien, "xep_hang": h, "cham": cham(v["dieu"], hien),
                     "loi": None, "giay": round(giay_dd / max(1, len(vu)), 4)})
    with open(ra / f"{ten}.jsonl", "w", encoding="utf-8", newline="\n") as f:
        for r in dong:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    so_voi = {}
    if a.so_voi:
        for k in ("C0", "L"):
            kq = doc_ket_qua(a.so_voi / f"{k}.jsonl")
            if kq:
                so_voi[k] = kq
    md = bao_cao(ten, a.tap, dong, tk, so_voi, {"hoc": giay_hoc, "du_doan": giay_dd})
    (ra / f"bao_cao_{ten}.md").write_text(md, encoding="utf-8")
    print(f"[3/3] ghi {ra / (ten + '.jsonl')}\n")
    print(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
