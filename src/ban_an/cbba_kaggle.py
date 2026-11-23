"""Bộ cbba đã gán nhãn (scripts/xu_ly_cbba_blhs.py) -> mẫu con cho Kaggle (kế hoạch V3, kaggle/KE_HOACH_KAGGLE_V3.md).

Mọi bước chọn mẫu ở đây chỉ dựa vào siêu dữ liệu, băm và văn bản; KHÔNG bước nào nhìn điểm của một mô hình, nên có thể ghi
trước khi chạy (đăng ký trước). Tất cả xác định: cùng đầu vào + tham số ra cùng danh sách.

  lay_meta / doc_meta     siêu dữ liệu mỗi văn bản (mã, nhóm vụ, Điều, ngày, cấp, độ dài, băm) từ train.jsonl / test.jsonl.
  loc_pool                ngày hợp lệ (>= 2018, vì số Điều trước đó là BLHS 1999), Điều có trong chỉ mục tại ngày bản án, văn bản
                          train không quá dài, và loại mọi văn bản có chữ trùng hệt nhau giữa train và test.
  chon_dev                chia dev theo NHÓM VỤ từ pool train (nhóm vào trọn một bên), phân bố tự nhiên.
  chon_train              trần mỗi Điều: duyệt Điều hiếm trước, lấy theo thứ tự băm cho tới khi Điều đó đủ `tran` văn bản
                          (văn bản đã chọn vì Điều khác cũng được tính). Điều hiếm được giữ trọn.
  thu_tu_test             mỗi nhóm vụ của test một văn bản, xếp theo băm; test thật = tiền tố đầu tiên qua kiểm gần-trùng.
  ChiMucGanTrung          độ chứa 5-gram (như anle_hf.trung_voi) bằng chỉ mục ngược trên 5-gram hiếm: nhanh hơn so từng cặp.
  loc_gan_trung_test      bỏ văn bản test có bản gần-trùng trong train / dev (cổng G0).
  loc_giao_anle           tập học + dev không được chứa chữ gần-trùng với 99 vụ test án lệ (bộ test độc lập thứ hai, chưa dùng).
  mau_cbba                mẫu cùng dạng với goi_kaggle.mau_ban_an, để dùng lại goi_kaggle.dong_sft và scripts/do_ban_an.py.
"""
from __future__ import annotations

import hashlib
import json
import re
import zlib
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Iterator, Sequence
from datetime import date
from pathlib import Path

from src.ban_an import anle_hf as hf
from src.ban_an import chon_dieu as cd

NGUON_CBBA = "cbba_blhs"
TIEN_TO_ID = "cbba_"
SEED = 2026
TRAN_MOI_DIEU = 50
SO_DEV = 300                     # val loss trong gói học
SO_DEV_DO = 100                  # phần dev đi vào gói đo (G3 / G4 trên Ollama)
SO_TEST = 3000
TOI_DA_KY_TU = 7700              # train: bỏ ~10% văn bản dài nhất (p90 của đầu vào đã che); test không bỏ gì
NAM_TU, NAM_DEN = 2018, 2026
NGUONG_GAN_TRUNG = 0.5           # như goi_kaggle.kiem_giao
BIEN_AN_TEST = 1.15              # số ứng viên test đọc thêm để bù vụ bị loại vì gần-trùng
DF_TOI_DA = 64                   # 5-gram xuất hiện ở nhiều hơn số này văn bản bị bỏ qua khi tìm ứng viên (tính độ chứa vẫn dùng đủ)
CHUNG_TOI_THIEU = 3              # số 5-gram hiếm chung tối thiểu để một cặp được tính độ chứa chính xác
LY_DO = ("thieu_hoac_sai_ngay", "cap_khong_giu", "dieu_khong_co_trong_chi_muc", "qua_dai", "trung_chu_train_test")

_RE_MA = re.compile(r'^\{"ma": "([^"]+)"')
_RE_TU = re.compile(r"\w+")


class CbbaKaggleError(ValueError):
    pass


def bam(seed: int, khoa: str) -> str:
    return hashlib.sha256(f"{seed}:{khoa}".encode()).hexdigest()


# --------------------------------------------------------------------------------------------------------------------
# 1. Đọc
# --------------------------------------------------------------------------------------------------------------------


def lay_meta(r: dict) -> dict:
    van = r["dau_vao"]
    dieu = r["dieu"] if isinstance(r["dieu"], list) else [r["dieu"]]
    return {"ma": str(r["ma"]), "tap": r["tap"], "nhom_vu": str(r.get("nhom_vu") or r["ma"]), "dieu": cd.sap_xep(dieu),
            "ngay": r.get("ngay"), "cap": r.get("cap"), "n_ky_tu": len(van), "hash": hf.hash_van(van)}


def doc_meta(p: Path) -> Iterator[dict]:
    with open(p, encoding="utf-8") as f:
        for dong in f:
            if dong.strip():
                yield lay_meta(json.loads(dong))


def doc_van_ban(p: Path, can: set[str]) -> dict[str, str]:
    """{mã: đầu vào đã che} của các mã trong `can`. Bỏ qua nhanh dòng không cần (không phân tích JSON của chúng)."""
    ra: dict[str, str] = {}
    if not can:
        return ra
    with open(p, encoding="utf-8") as f:
        for dong in f:
            m = _RE_MA.match(dong)
            if m is not None and m.group(1) not in can:
                continue
            r = json.loads(dong)
            if str(r["ma"]) in can:
                ra[str(r["ma"])] = r["dau_vao"]
                if len(ra) == len(can):
                    break
    thieu = can - set(ra)
    if thieu:
        raise CbbaKaggleError(f"{p.name}: không thấy {len(thieu)} mã cần đọc, ví dụ {sorted(thieu)[:3]}")
    return ra


# --------------------------------------------------------------------------------------------------------------------
# 2. Pool
# --------------------------------------------------------------------------------------------------------------------


def ngay_hop_le(ngay: str | None, nam_tu: int = NAM_TU, nam_den: int = NAM_DEN) -> bool:
    try:
        d = date.fromisoformat(ngay or "")
    except ValueError:
        return False
    return nam_tu <= d.year <= nam_den


def loc_pool(metas: Iterable[dict], *, nam_tu: int = NAM_TU, nam_den: int = NAM_DEN, toi_da_ky_tu: int | None = TOI_DA_KY_TU,
             cap_giu: set[str] | None = None,
             tra_cuu_duoc: Callable[[Sequence[str], str | None], bool] = lambda dieu, ngay: True,
             ) -> tuple[dict[str, list[dict]], dict[str, Counter]]:
    """({'train': [...], 'test': [...]}, {'train': Counter(lý do), 'test': Counter(lý do)}).
    Mỗi văn bản bị loại được tính đúng một lý do (theo thứ tự của LY_DO). `toi_da_ky_tu` chỉ áp dụng cho train.
    `tra_cuu_duoc(dieu, ngay_tra_cuu)`: mọi Điều đáp án có tiêu đề trong chỉ mục tại ngày đó (không thì nhãn không dựng được lời nhắc)."""
    pool: dict[str, list[dict]] = {"train": [], "test": []}
    loai: dict[str, Counter] = {"train": Counter(), "test": Counter()}
    for m in metas:
        t = m["tap"]
        if t not in pool:
            raise CbbaKaggleError(f"{m['ma']}: tap = {t!r}")
        if not ngay_hop_le(m["ngay"], nam_tu, nam_den):
            ly_do = LY_DO[0]
        elif cap_giu is not None and m["cap"] not in cap_giu:
            ly_do = LY_DO[1]
        elif not tra_cuu_duoc(m["dieu"], cd.ngay_tra_cuu(m["ngay"])):
            ly_do = LY_DO[2]
        elif t == "train" and toi_da_ky_tu and m["n_ky_tu"] > toi_da_ky_tu:
            ly_do = LY_DO[3]
        else:
            pool[t].append(m)
            continue
        loai[t][ly_do] += 1
    chung = {m["hash"] for m in pool["train"]} & {m["hash"] for m in pool["test"]}
    if chung:
        for t in pool:
            giu = []
            for m in pool[t]:
                if m["hash"] in chung:
                    loai[t][LY_DO[4]] += 1
                else:
                    giu.append(m)
            pool[t] = giu
    return pool, loai


# --------------------------------------------------------------------------------------------------------------------
# 3. Chọn
# --------------------------------------------------------------------------------------------------------------------


def chon_dev(pool_train: Sequence[dict], so_dev: int = SO_DEV, seed: int = SEED) -> list[dict]:
    """Nhóm vụ xếp theo băm, lấy lần lượt vào dev tới khi đủ `so_dev` văn bản (mỗi nhóm vào trọn dev, nên có thể hơn một chút)."""
    theo_nhom: dict[str, list[dict]] = defaultdict(list)
    for m in pool_train:
        theo_nhom[m["nhom_vu"]].append(m)
    dev: list[dict] = []
    for g in sorted(theo_nhom, key=lambda g: bam(seed, "dev|" + g)):
        if len(dev) >= so_dev:
            break
        dev += sorted(theo_nhom[g], key=lambda m: m["ma"])
    return dev


def chon_train(pool: Sequence[dict], tran: int = TRAN_MOI_DIEU, seed: int = SEED) -> list[dict]:
    """Trần `tran` văn bản mỗi Điều. Duyệt Điều từ hiếm tới phổ biến (hòa thì theo số Điều); mỗi Điều lấy văn bản theo thứ tự băm
    cho tới khi số văn bản đã chọn có Điều đó đạt `tran`. Văn bản nhiều Điều được chọn vì một Điều thì cũng tính cho các Điều còn lại,
    nên Điều phổ biến có thể vượt `tran` chút ít. Điều có ít hơn `tran` văn bản được lấy hết. Trả về theo mã."""
    if tran < 1:
        raise CbbaKaggleError("tran phải >= 1")
    tong: Counter = Counter(d for m in pool for d in m["dieu"])
    theo_dieu: dict[str, list[dict]] = defaultdict(list)
    for m in sorted(pool, key=lambda m: bam(seed, "hoc|" + m["ma"])):
        for d in m["dieu"]:
            theo_dieu[d].append(m)
    chon: dict[str, dict] = {}
    dem: Counter = Counter()
    for d in sorted(tong, key=lambda d: (tong[d], cd.khoa_so(d))):
        for m in theo_dieu[d]:
            if dem[d] >= tran:
                break
            if m["ma"] in chon:
                continue
            chon[m["ma"]] = m
            for x in m["dieu"]:
                dem[x] += 1
    return sorted(chon.values(), key=lambda m: m["ma"])


def thu_tu_test(pool_test: Sequence[dict], seed: int = SEED) -> list[dict]:
    """Mỗi nhóm vụ một văn bản (băm nhỏ nhất), xếp theo băm. Test thật lấy tiền tố đầu tiên qua kiểm gần-trùng,
    nên đổi cỡ test chỉ cắt ngắn / kéo dài cùng một danh sách."""
    tot: dict[str, tuple[str, dict]] = {}
    for m in pool_test:
        k = bam(seed, "test|" + m["ma"])
        if m["nhom_vu"] not in tot or k < tot[m["nhom_vu"]][0]:
            tot[m["nhom_vu"]] = (k, m)
    return [m for _, m in sorted(tot.values(), key=lambda t: t[0])]


def chon_so_bo(pool: dict[str, list[dict]], *, tran: int = TRAN_MOI_DIEU, so_dev: int = SO_DEV, seed: int = SEED) -> dict[str, list[dict]]:
    """{'hoc', 'dev', 'ung_test'}: dev tách trước (theo nhóm vụ), học chọn từ phần còn lại."""
    dev = chon_dev(pool["train"], so_dev, seed)
    nhom_dev = {m["nhom_vu"] for m in dev}
    hoc = chon_train([m for m in pool["train"] if m["nhom_vu"] not in nhom_dev], tran, seed)
    return {"hoc": hoc, "dev": dev, "ung_test": thu_tu_test(pool["test"], seed)}


# --------------------------------------------------------------------------------------------------------------------
# 4. Gần-trùng
# --------------------------------------------------------------------------------------------------------------------


def tap_bam_5gram(van: str, n: int = 5) -> frozenset[int]:
    """Tập băm (crc32, ổn định giữa các lần chạy) của các n-gram từ; cùng cách tách từ và chuẩn hóa với anle_hf._shingle."""
    tu = _RE_TU.findall(hf.chuan_van(van))
    if not tu:
        return frozenset()
    gram = [" ".join(tu[i:i + n]) for i in range(max(1, len(tu) - n + 1))]
    return frozenset(zlib.crc32(g.encode("utf-8")) for g in gram)


def do_chua(a: frozenset[int], b: frozenset[int]) -> float:
    return len(a & b) / min(len(a), len(b)) if a and b else 0.0


class ChiMucGanTrung:
    """Chỉ mục ngược 5-gram -> văn bản. `tim(van)` trả các văn bản đã thêm có độ chứa 5-gram >= ngưỡng (độ chứa chính xác,
    như anle_hf.do_chua: tỉ lệ 5-gram của văn bản NGẮN HƠN nằm trong văn bản kia). Ứng viên chỉ được tìm qua 5-gram hiếm
    (<= df_toi_da văn bản), vì 5-gram phổ biến («bị cáo đã khai nhận ...») làm chậm mà không giúp tìm bản sao."""

    def __init__(self, df_toi_da: int = DF_TOI_DA, chung_toi_thieu: int = CHUNG_TOI_THIEU):
        self.df_toi_da, self.chung_toi_thieu = df_toi_da, chung_toi_thieu
        self.ma: list[str] = []
        self.tap: list[frozenset[int]] = []
        self.nghich: dict[int, list[int]] = defaultdict(list)

    def __len__(self) -> int:
        return len(self.ma)

    def them(self, ma: str, van: str) -> None:
        s = tap_bam_5gram(van)
        i = len(self.ma)
        self.ma.append(ma)
        self.tap.append(s)
        for h in s:
            self.nghich[h].append(i)

    def tim(self, van: str, nguong: float = NGUONG_GAN_TRUNG) -> list[tuple[str, float]]:
        s = tap_bam_5gram(van)
        dem: Counter = Counter()
        for h in s:
            ds = self.nghich.get(h)
            if ds is not None and len(ds) <= self.df_toi_da:
                dem.update(ds)
        ra = []
        for i, c in dem.items():
            if c < self.chung_toi_thieu:
                continue
            dc = do_chua(s, self.tap[i])
            if dc >= nguong:
                ra.append((self.ma[i], round(dc, 3)))
        return sorted(ra, key=lambda t: (-t[1], t[0]))


def them_ca_nhom(chi_muc: ChiMucGanTrung, ma_va_van: Iterable[tuple[str, str]]) -> None:
    for ma, van in ma_va_van:
        chi_muc.them(ma, van)


def loc_dev_gan_trung(dev: Sequence[dict], van: dict[str, str], chi_muc_hoc: ChiMucGanTrung,
                      nguong: float = NGUONG_GAN_TRUNG) -> tuple[list[dict], list[dict]]:
    """(dev giữ lại, [{ma, ma_hoc, do_chua}] của dev bị bỏ vì có bản gần-trùng trong tập học)."""
    giu, bo = [], []
    for m in dev:
        kq = chi_muc_hoc.tim(van[m["ma"]], nguong)
        if kq:
            bo.append({"ma": m["ma"], "ma_hoc": kq[0][0], "do_chua": kq[0][1]})
        else:
            giu.append(m)
    return giu, bo


def loc_gan_trung_test(ung_test: Sequence[dict], van: dict[str, str], chi_muc: ChiMucGanTrung, so_test: int,
                       nguong: float = NGUONG_GAN_TRUNG) -> tuple[list[dict], list[dict]]:
    """(test = `so_test` văn bản đầu tiên của `ung_test` không có bản gần-trùng trong chi_muc, [{ma, ma_hoc, do_chua}] của vụ bị bỏ).
    Chỉ xét các ứng viên cho tới khi đủ `so_test`; không đủ thì báo lỗi."""
    giu, bo = [], []
    for m in ung_test:
        if len(giu) >= so_test:
            break
        kq = chi_muc.tim(van[m["ma"]], nguong)
        if kq:
            bo.append({"ma": m["ma"], "ma_hoc": kq[0][0], "do_chua": kq[0][1]})
        else:
            giu.append(m)
    if len(giu) < so_test:
        raise CbbaKaggleError(f"chỉ có {len(giu)} văn bản test sạch (cần {so_test}); giảm --so-test")
    return giu, bo


def loc_giao_anle(chi_muc: ChiMucGanTrung, vu_anle: dict[str, str], nguong: float = NGUONG_GAN_TRUNG) -> dict[str, dict]:
    """{mã văn bản trong chỉ mục: {ma_anle, do_chua}} cho văn bản (học / dev) gần-trùng với một vụ test án lệ (độ chứa 5-gram >= ngưỡng).
    Bộ 99 vụ test án lệ giữ làm test độc lập thứ hai nên không được lọt vào dữ liệu học."""
    ra: dict[str, dict] = {}
    for ma_anle, van in vu_anle.items():
        for ma, dc in chi_muc.tim(van, nguong):
            if ma not in ra or dc > ra[ma]["do_chua"]:
                ra[ma] = {"ma_anle": ma_anle, "do_chua": dc}
    return ra


def kiem_giao_cbba(test: Sequence[dict], hoc: Sequence[dict], chi_muc_hoc: ChiMucGanTrung | None = None,
                   van_test: dict[str, str] | None = None, nguong: float = NGUONG_GAN_TRUNG) -> list[str]:
    """Cổng G0 trên mẫu đã dựng (cùng dạng mau_cbba): lỗi rò rỉ giữa test và mọi mẫu vào gói học (rỗng = sạch):
    trùng id, trùng nhóm vụ, trùng băm đầu vào, và (nếu có chỉ mục + văn bản) độ chứa 5-gram >= ngưỡng."""
    loi = []
    id_hoc = {x["id"] for x in hoc}
    nhom_hoc = {x["nhom_vu"] for x in hoc}
    bam_hoc = {x["hash_dau_vao"] for x in hoc}
    for t in test:
        if t["id"] in id_hoc:
            loi.append(f"{t['id']}: id vụ test nằm trong gói học")
        if t["nhom_vu"] in nhom_hoc:
            loi.append(f"{t['id']}: nhóm vụ {t['nhom_vu']} có mặt ở cả test và gói học")
        if t["hash_dau_vao"] in bam_hoc:
            loi.append(f"{t['id']}: trùng băm đầu vào với một mẫu của gói học")
        if chi_muc_hoc is not None and van_test is not None:
            for ma_hoc, dc in chi_muc_hoc.tim(van_test[t["id"]], nguong)[:1]:
                loi.append(f"{t['id']}: trùng với {ma_hoc} (độ chứa 5-gram {dc})")
    return loi


# --------------------------------------------------------------------------------------------------------------------
# 5. Mẫu
# --------------------------------------------------------------------------------------------------------------------


def mau_cbba(m: dict, van: str, tap: str, dieu_da_hoc: set[str] | None = None) -> dict:
    """Mẫu cùng dạng goi_kaggle.mau_ban_an (tap 'hoc' | 'dev' | 'test'). `nguon` = 'ban_an' để notebook học nhận đúng loại mẫu;
    `dieu_chua_gap` (chỉ test): có Điều nào không xuất hiện trong tập học + dev."""
    if tap not in ("hoc", "dev", "test"):
        raise CbbaKaggleError(f"tap = {tap!r}")
    sv, da_cat = cd.cat_su_viec(van)
    return {"id": TIEN_TO_ID + m["ma"], "nguon": "ban_an", "tap": tap, "su_viec": sv, "da_cat": da_cat, "so_tu_goc": len(van.split()),
            "dieu": list(m["dieu"]), "nhom_vu": m["nhom_vu"], "ngay": m["ngay"], "ngay_tra_cuu": cd.ngay_tra_cuu(m["ngay"]),
            "ten_toi_trong_loi_ke": 0, "dieu_chua_gap": tap == "test" and dieu_da_hoc is not None and any(d not in dieu_da_hoc for d in m["dieu"]),
            "hash_dau_vao": m["hash"], "dau_vao_goc": van, "cap": m["cap"], "nam": int(m["ngay"][:4])}


def gan_tan_suat(mau: Sequence[dict], dem_dieu_hoc: Counter) -> None:
    """mau[i]['tan_suat_dieu_hoc'] = số văn bản học có Điều hiếm nhất của mẫu (0 = chưa gặp); để báo cáo theo độ hiếm."""
    for x in mau:
        x["tan_suat_dieu_hoc"] = min(dem_dieu_hoc.get(d, 0) for d in x["dieu"])


class CacheXepHang(dict):
    """Cache {khóa: kết quả} ghi nối vào một file JSONL: dừng giữa chừng thì chạy lại tiếp từ chỗ dừng, không phải ghi lại cả file."""

    def __init__(self, duong_dan: Path):
        super().__init__()
        self.duong_dan = duong_dan
        if duong_dan.exists():
            for dong in duong_dan.read_text(encoding="utf-8").splitlines():
                try:
                    o = json.loads(dong)
                except ValueError:
                    continue                                   # dòng cuối ghi dở khi bị ngắt
                dict.__setitem__(self, o["k"], o["v"])
        duong_dan.parent.mkdir(parents=True, exist_ok=True)
        dang_do = False
        if duong_dan.exists() and duong_dan.stat().st_size:
            with duong_dan.open("rb") as f:
                f.seek(-1, 2)
                dang_do = f.read(1) != b"\n"
        self._f = duong_dan.open("a", encoding="utf-8", newline="\n")
        if dang_do:
            self._f.write("\n")                                   # kết thúc dòng ghi dở, để kết quả mới không dính vào nó

    def __setitem__(self, khoa, gia_tri) -> None:
        super().__setitem__(khoa, gia_tri)
        self._f.write(json.dumps({"k": khoa, "v": gia_tri}, ensure_ascii=False) + "\n")

    def flush(self) -> None:
        self._f.flush()

    def dong(self) -> None:
        self._f.close()


def phan_bo(dem: Counter) -> dict:
    """Mô tả phân bố số văn bản mỗi Điều (để ghi vào báo cáo)."""
    if not dem:
        return {"so_dieu": 0}
    v = sorted(dem.values())
    return {"so_dieu": len(v), "nho_nhat": v[0], "trung_vi": v[len(v) // 2], "lon_nhat": v[-1],
            "top5": [(d, n) for d, n in dem.most_common(5)], "duoi_10": sum(1 for x in v if x < 10)}
