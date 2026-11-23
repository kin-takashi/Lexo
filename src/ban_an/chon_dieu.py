"""Việc «chọn Điều từ ứng viên» (Vòng 2 của kế hoạch train trên Kaggle): đọc sự việc + K Điều ứng viên do truy hồi đưa ra,
trả về các Điều tòa áp dụng.

Mọi bước dùng chung cho đóng gói (scripts/dong_goi_kaggle.py), notebook học và notebook đo (scripts/do_ban_an.py) đều ở đây,
để chữ đưa vào mô hình lúc học và lúc đo giống hệt nhau:

  cat_su_viec      cắt sự việc dài còn SO_TU_DAU từ đầu + SO_TU_CUOI từ cuối (bản án dài tới 36 nghìn từ).
  chia_doan        chia sự việc thành đoạn ~DOAN_TU từ để truy hồi (bge-m3 và FTS5 đều kém với truy vấn quá dài).
  xep_hang_dieu    mỗi đoạn tìm riêng, gộp hạng các đoạn bằng RRF; chỉ giữ Điều về tội phạm (108–425).
  dung_ung_vien    top K, xếp theo SỐ Điều (không theo hạng). Khi học: chèn đáp án còn thiếu thay cho ứng viên hạng thấp nhất,
                   giữ đúng K ứng viên, nên vị trí và số lượng không lộ Điều nào được chèn. Dev/test không bao giờ chèn.
  dung_tin_nhan    system + user; dich_chon: đáp án {"dieu": [...]} số tăng dần.
  doc_chon         đọc câu trả lời của mô hình, chỉ giữ Điều nằm trong danh sách ứng viên.
  ket_hop          gộp kết quả của mô hình gốc (C0) và LoRA (L) trên cùng một vụ: hợp, hoặc C0 làm nền rồi L lọc bớt.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Sequence

from src.ban_an.anle_hf import DIEU_TOI_PHAM_CUOI, DIEU_TOI_PHAM_DAU, _bam

SO_TU_DAU = 1400                  # từ giữ ở đầu sự việc
SO_TU_CUOI = 600                  # từ giữ ở cuối sự việc
DAU_LUOC = "[…]"                  # chèn vào chỗ đã lược
DOAN_TU = 300                     # từ mỗi đoạn khi truy hồi
RRF_K = 60
CHE_DO_UV = ("vector", "fts", "hybrid")
KS_RECALL = (3, 5, 10, 20, 30)
K_TOI_DA = 30
RECALL_MUC = 0.9                  # K = K nhỏ nhất có Recall@K >= mức này (trên 90 vụ train)
RECALL_SAN = 0.8                  # Recall@30 dưới sàn: bộ sinh ứng viên là nút thắt, chưa nên học Vòng 2
NGAY_BLHS_2015 = "2018-01-01"     # chỉ mục chỉ có BLHS 2015; bản án trước ngày này vẫn tra theo bản đầu tiên
TOI_DA_CHON = 6
CACH_KET_HOP = ("hop", "loc_l", "loc_c0")

HE_THONG_CHON = ("Bạn đọc một sự việc (tình huống đời thường hoặc phần sự việc của một bản án hình sự) và danh sách Điều ứng viên "
                 "của Bộ luật Hình sự. Chọn các Điều quy định tội mà người trong sự việc đã phạm, chỉ chọn trong danh sách ứng viên. "
                 "Mỗi tội một Điều; tình tiết tăng nặng của cùng một hành vi không tính là tội riêng. "
                 'Trả về đúng một JSON: {"dieu": ["số Điều", ...]}, số Điều xếp tăng dần.')
PHIEN_BAN_TIN_NHAN = "chon-dieu-v1"

_TU = re.compile(r"\S+")
_SO = re.compile(r"(\d+)([a-zđ]?)")
_THINK = re.compile(r"<think>.*?</think>", re.S)


class ChonError(ValueError):
    pass


# --------------------------------------------------------------------------------------------------------------------
# 1. Đầu vào
# --------------------------------------------------------------------------------------------------------------------


def cat_su_viec(chu: str, dau: int = SO_TU_DAU, cuoi: int = SO_TU_CUOI) -> tuple[str, bool]:
    """(chữ đã cắt, có cắt không). Cắt theo vị trí ký tự của từ nên giữ nguyên xuống dòng và dấu câu của phần còn lại."""
    tu = list(_TU.finditer(chu))
    if len(tu) <= dau + cuoi:
        return chu.strip(), False
    dau_chu = chu[:tu[dau - 1].end()].rstrip()
    cuoi_chu = chu[tu[len(tu) - cuoi].start():].strip() if cuoi else ""
    return (f"{dau_chu}\n{DAU_LUOC}\n{cuoi_chu}" if cuoi_chu else dau_chu), True


def chia_doan(chu: str, n_tu: int = DOAN_TU) -> list[str]:
    """Các đoạn liên tiếp, mỗi đoạn tối đa n_tu từ (đoạn cuối quá ngắn thì gộp vào đoạn trước)."""
    tu = list(_TU.finditer(chu))
    if not tu:
        return []
    moc = list(range(0, len(tu), n_tu))
    if len(moc) > 1 and len(tu) - moc[-1] < n_tu // 3:
        moc.pop()
    doan = []
    for i, a in enumerate(moc):
        b = moc[i + 1] if i + 1 < len(moc) else len(tu)
        doan.append(chu[tu[a].start():tu[b - 1].end()])
    return doan


def ngay_tra_cuu(ngay: str | None) -> str | None:
    """Ngày dùng để lọc hiệu lực khi tra: ngày bản án (không sớm hơn ngày BLHS 2015 có hiệu lực). None = hôm nay."""
    if not ngay:
        return None
    return max(ngay, NGAY_BLHS_2015)


# --------------------------------------------------------------------------------------------------------------------
# 2. Số Điều
# --------------------------------------------------------------------------------------------------------------------


def khoa_so(so: str) -> tuple[int, str]:
    m = _SO.fullmatch(so.strip().lower())
    if not m:
        raise ChonError(f"số Điều không hợp lệ: {so!r}")
    return int(m.group(1)), m.group(2)


def sap_xep(ds: Iterable[str]) -> list[str]:
    return sorted(dict.fromkeys(ds), key=khoa_so)


def la_dieu_toi_pham(so: str) -> bool:
    try:
        return DIEU_TOI_PHAM_DAU <= khoa_so(so)[0] <= DIEU_TOI_PHAM_CUOI
    except ChonError:
        return False


# --------------------------------------------------------------------------------------------------------------------
# 3. Truy hồi ứng viên
# --------------------------------------------------------------------------------------------------------------------


def gop_rrf(xep_hangs: Sequence[Sequence[str]], k: int = RRF_K) -> list[str]:
    """Gộp nhiều danh sách xếp hạng bằng RRF; hòa điểm thì xếp theo hạng tốt nhất rồi theo số Điều, để kết quả xác định."""
    diem: dict[str, float] = {}
    tot: dict[str, int] = {}
    for ds in xep_hangs:
        for hang, d in enumerate(dict.fromkeys(ds), 1):
            diem[d] = diem.get(d, 0.0) + 1.0 / (k + hang)
            tot[d] = min(tot.get(d, hang), hang)
    return sorted(diem, key=lambda d: (-diem[d], tot[d], khoa_so(d)))


def xep_hang_dieu(idx, emb, chu: str, ngay: str | None, n_giu: int = 50) -> dict[str, list[str]]:
    """{che_do: [số Điều tội phạm, xếp hạng giảm dần]} cho cả ba chế độ. Mỗi đoạn tìm riêng bằng vector và bằng FTS5;
    «vector» gộp các đoạn theo vector, «fts» gộp theo FTS5, «hybrid» gộp tất cả."""
    from src.index.search import gop_theo_dieu, tim
    from src.index.tim_du import so_dieu

    def mot(doan: str, che_do: str) -> list[str]:
        kq = tim(idx, doan, embedder=emb, ngay=ngay, k=300, che_do=che_do, n_ung_vien=300)
        return [s for s in (so_dieu(d.dieu) for d in gop_theo_dieu(kq.hits, 10_000)) if la_dieu_toi_pham(s)]

    doan = chia_doan(chu) or [chu]
    v = [mot(x, "vector") for x in doan]
    f = [mot(x, "fts") for x in doan]
    return {"vector": gop_rrf(v)[:n_giu], "fts": gop_rrf(f)[:n_giu], "hybrid": gop_rrf(v + f)[:n_giu]}


def tieu_de_dieu(idx, ngay: str | None) -> dict[str, str]:
    """{số Điều: 'Điều 173. Tội trộm cắp tài sản'} của các Điều tội phạm có hiệu lực tại ngày (None = hôm nay)."""
    from datetime import date

    from src.index.tim_du import so_dieu
    ngay = ngay or date.today().isoformat()
    ra: dict[str, str] = {}
    for r in idx.execute("""SELECT key, text FROM chunk WHERE loai = 'dieu' AND hieu_luc_tu <= ? AND (hieu_luc_den IS NULL OR ? < hieu_luc_den)""",
                         (ngay, ngay)):
        s = so_dieu(r["key"].split("/")[0])
        if la_dieu_toi_pham(s):
            ra[s] = r["text"].split("\n", 1)[0].strip()
    return ra


def recall(vang: Sequence[str], xep_hang: Sequence[str], k: int) -> tuple[float, bool]:
    """(phần Điều đáp án nằm trong top k, có đủ hết không)."""
    top = set(xep_hang[:k])
    co = sum(1 for d in vang if d in top)
    return co / len(vang), co == len(vang)


def bang_recall(mau: Sequence[dict], ks: Sequence[int] = KS_RECALL) -> dict[str, dict[int, dict[str, float]]]:
    """{che_do: {k: {'recall': TB phần Điều trúng, 'du': phần vụ trúng đủ}}}. Mỗi mẫu cần 'dieu' và 'xep_hang' {che_do: [...]}."""
    if not mau:
        raise ChonError("không có mẫu nào để tính Recall@K")
    ra: dict[str, dict[int, dict[str, float]]] = {}
    for cd in CHE_DO_UV:
        ra[cd] = {}
        for k in ks:
            r = [recall(x["dieu"], x["xep_hang"][cd], k) for x in mau]
            ra[cd][k] = {"recall": sum(a for a, _ in r) / len(r), "du": sum(b for _, b in r) / len(r)}
    return ra


def chon_k(bang: dict[str, dict[int, dict[str, float]]], muc: float = RECALL_MUC, k_toi_da: int = K_TOI_DA) -> dict:
    """Chọn chế độ + K theo «tìm đủ trong top K» (phần vụ có MỌI Điều đáp án trong top K) trên 90 vụ train:
    với mỗi chế độ, K nhỏ nhất (trong các mốc <= k_toi_da) đạt mức; chọn chế độ có K nhỏ nhất, hòa thì Recall@k_toi_da cao hơn,
    hòa nữa theo thứ tự CHE_DO_UV. Không chế độ nào đạt: K = k_toi_da với chế độ có Recall@k_toi_da cao nhất (dat = False)."""
    ung = []
    for i, cd in enumerate(CHE_DO_UV):
        ks = sorted(k for k in bang[cd] if k <= k_toi_da)
        k_dat = next((k for k in ks if bang[cd][k]["du"] >= muc), None)
        ung.append((k_dat if k_dat is not None else 10**9, -bang[cd][ks[-1]]["du"], i, cd, ks[-1]))
    k_dat, am_du, _, cd, k_cuoi = min(ung)
    dat = k_dat < 10**9
    return {"che_do": cd, "k": k_dat if dat else k_cuoi, "dat_muc": dat, "du_tai_k_toi_da": -am_du, "muc": muc, "k_toi_da": k_toi_da}


# --------------------------------------------------------------------------------------------------------------------
# 4. Tin nhắn
# --------------------------------------------------------------------------------------------------------------------


def dung_ung_vien(xep_hang: Sequence[str], k: int, vang: Sequence[str] | None = None) -> tuple[list[str], int]:
    """(K ứng viên xếp theo số Điều, số đáp án đã chèn). vang=None: không chèn (dev, test, lúc chạy thật)."""
    top = list(dict.fromkeys(xep_hang))[:k]
    chen = 0
    if vang:
        thieu = [d for d in dict.fromkeys(vang) if d not in top]
        if len(thieu) > k:
            raise ChonError(f"{len(thieu)} đáp án nhiều hơn K = {k}")
        for d in thieu:
            bo = next(i for i in range(len(top) - 1, -1, -1) if top[i] not in vang) if len(top) >= k else None
            if bo is None:
                top.append(d)
            else:
                top[bo] = d
            chen += 1
    return sap_xep(top), chen


def noi_dung_nguoi_dung(su_viec: str, ung_vien: Sequence[str], tieu_de: dict[str, str]) -> str:
    dong = []
    for d in ung_vien:
        if d not in tieu_de:
            raise ChonError(f"thiếu tiêu đề của Điều {d}")
        dong.append(tieu_de[d])
    return f"Sự việc:\n{su_viec.strip()}\n\nĐiều ứng viên:\n" + "\n".join(dong)


def dung_tin_nhan(su_viec: str, ung_vien: Sequence[str], tieu_de: dict[str, str]) -> list[dict]:
    return [{"role": "system", "content": HE_THONG_CHON}, {"role": "user", "content": noi_dung_nguoi_dung(su_viec, ung_vien, tieu_de)}]


def dich_chon(vang: Sequence[str]) -> str:
    return json.dumps({"dieu": sap_xep(vang)}, ensure_ascii=False)


def schema_chon(ung_vien: Sequence[str]) -> dict:
    """JSON schema ép đầu ra của Ollama: chỉ được chọn trong ứng viên."""
    return {"type": "object", "properties": {"dieu": {"type": "array", "items": {"type": "string", "enum": list(ung_vien)},
                                                      "minItems": 1, "maxItems": TOI_DA_CHON}}, "required": ["dieu"]}


def doc_chon(chu: str, ung_vien: Sequence[str]) -> list[str]:
    """Đọc {"dieu": [...]} (chịu được khối <think>, rào ```json, chữ thừa). Bỏ Điều ngoài ứng viên; rỗng thì lỗi."""
    chu = _THINK.sub("", chu or "").strip()
    chu = re.sub(r"^```(?:json)?\s*|\s*```$", "", chu).strip()
    obj = None
    for cand in (chu, *(m.group(0) for m in re.finditer(r"\{.*?\}", chu, re.S))):
        try:
            obj = json.loads(cand)
            break
        except ValueError:
            continue
    if not isinstance(obj, dict) or not isinstance(obj.get("dieu"), list):
        raise ChonError(f"không đọc được JSON có khóa dieu: {chu[:160]!r}")
    uv = set(ung_vien)
    ra = [s for s in dict.fromkeys(str(x).strip().lower().replace("điều", "").strip() for x in obj["dieu"]) if s in uv]
    if not ra:
        raise ChonError(f"không có Điều nào nằm trong ứng viên: {obj['dieu']!r}")
    return sap_xep(ra)[:TOI_DA_CHON]


def cham_chon(vang: Sequence[str], chon: Sequence[str]) -> dict:
    """Chấm một vụ: các số đo của src/index/tim_du.py (mỗi Điều chọn là một «hành vi» hiển thị 1 Điều) + khớp đúng tập."""
    from src.index.tim_du import cham
    r = cham(vang, [[d] for d in chon], m=1) if chon else {
        "bao_phu": 0.0, "tim_du": 0.0, "chinh_xac": 0.0, "so_hien_thi": 0, "thieu": list(vang)}
    return {"tim_du": r["tim_du"], "bao_phu": r["bao_phu"], "chinh_xac": r["chinh_xac"], "so_hien_thi": r["so_hien_thi"],
            "khop_dung": float(set(chon) == set(vang)), "thieu": r["thieu"]}


def ket_hop(c0: Sequence[str], l: Sequence[str], cach: str) -> tuple[list[str], bool]:
    """(Điều hiển thị, có phải lùi không). Hai bên chọn trên cùng K ứng viên của một vụ; bên lỗi coi như chọn rỗng.
      hop      C0 ∪ L: giữ độ phủ của cả hai, hiển thị nhiều hơn.
      loc_l    C0 ∩ L (giữ Điều C0 chọn mà L cũng chọn); giao rỗng thì lùi về L, L rỗng nữa thì về C0.
      loc_c0   C0 ∩ L; giao rỗng thì lùi về nguyên C0 (L không bỏ hết được), C0 rỗng thì về L.
    Giao luôn là tập con của L nên phần giao một mình không thể tìm đủ hơn L; chỉ phần lùi mới thêm được."""
    if cach not in CACH_KET_HOP:
        raise ChonError(f"cách kết hợp không hợp lệ: {cach!r}; chọn trong {CACH_KET_HOP}")
    a, b = list(dict.fromkeys(c0)), list(dict.fromkeys(l))
    if cach == "hop":
        return sap_xep(a + b), False
    giao = [d for d in a if d in set(b)]
    if giao:
        return sap_xep(giao), False
    lui = (b or a) if cach == "loc_l" else (a or b)
    return sap_xep(lui), bool(a or b)


# --------------------------------------------------------------------------------------------------------------------
# 5. Chia 90 vụ train thành học / dev
# --------------------------------------------------------------------------------------------------------------------


def chia_dev(ban_ghi: Sequence[dict], nhom: dict[str, str], so_dev: int = 20, seed: int = 2026) -> dict[str, str]:
    """ma -> 'hoc' | 'dev'. Xếp các nhóm vụ theo băm (seed), lấy lần lượt vào dev tới khi đủ so_dev vụ; mỗi nhóm vào trọn một bên.
    Không phân tầng theo Điều: phân tầng của anle_hf.chia_tap đẩy mọi Điều hiếm vào dev, làm tập học mất các Điều đó."""
    theo_nhom: dict[str, list[str]] = {}
    for b in ban_ghi:
        theo_nhom.setdefault(nhom[b["ma"]], []).append(b["ma"])
    ra = {b["ma"]: "hoc" for b in ban_ghi}
    dem = 0
    for g in sorted(theo_nhom, key=lambda g: _bam(seed, g)):
        if dem >= so_dev:
            break
        for m in theo_nhom[g]:
            ra[m] = "dev"
        dem += len(theo_nhom[g])
    return ra


def bam_chu(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()
