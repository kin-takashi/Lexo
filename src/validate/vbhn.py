"""Đối chiếu bản hệ thống dựng lại (SQLite, tại một ngày) với VĂN BẢN HỢP NHẤT chính thức, theo từng nút Phần/Chương/Mục/Điều/Khoản/Điểm.

Không dùng LLM. Hai bên được đưa về cùng dạng {khoá đường dẫn: (tiêu đề, nội dung)} rồi so sánh sau khi chuẩn hoá giống hệt nhau
(NFC, Ð→Đ, gộp khoảng trắng). Văn bản hợp nhất vẫn GIỮ chỗ của phần đã bãi bỏ bằng "(được bãi bỏ)"; bản hệ thống thì không có nút đó,
nên nút "(được bãi bỏ)" của văn bản hợp nhất được coi là *không có*.

Loại sai khác:
  thieu_o_ta     văn bản hợp nhất có nút mà bản hệ thống không có
  thua_o_ta      bản hệ thống có nút mà văn bản hợp nhất không có (hoặc ghi "được bãi bỏ")
  khac_noi_dung  cùng nút nhưng chữ khác nhau (sau khi bỏ khác biệt chỉ về trình bày, xem fold())
  khac_tieu_de   cùng nút nhưng tiêu đề khác
  khac_trinh_bay cùng nút, chỉ khác cách trình bày: viết hoa, vị trí dấu thanh (oá/óa), sỹ/sĩ, dấu câu, khoảng trắng.
                 KHÔNG tính là sai khác nội dung (n_khop_chuan_hoa), nhưng vẫn được liệt kê để người xem biết.
  khac_vi_tri    cùng nút nhưng nằm dưới Chương/Mục khác, hoặc thứ tự anh em khác
"""
from __future__ import annotations

import difflib
import re
import sqlite3
import unicodedata
from dataclasses import dataclass, field

from src.parse.model import Node
from src.parse.text import normalize_text

REPEALED = re.compile(r"^\(?\s*(?:được\s+)?bãi bỏ\s*\)?\.?$", re.IGNORECASE)
_NAME = {"phan": "Phần", "chuong": "Chương", "muc": "Mục", "tieu_muc": "Tiểu mục", "dieu": "Điều", "khoan": "khoản", "diem": "điểm"}


@dataclass
class Item:
    key: str
    loai: str
    ky_hieu: str
    tieu_de: str
    noi_dung: str
    cha: str | None            # khoá của nút cha (chỉ cần để biết Điều nằm dưới Chương/Mục nào)
    thu_tu: int                # thứ tự trong anh em
    src: object = None         # nút nguồn (Node của văn bản hợp nhất hoặc id trong CSDL)


@dataclass
class Diff:
    kind: str
    key: str
    ours: str = ""
    theirs: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class CompareResult:
    n_ours: int
    n_theirs: int
    n_match: int                      # nút giống hệt (sau normalize_text)
    diffs: list[Diff] = field(default_factory=list)
    repealed_theirs: list[str] = field(default_factory=list)
    n_match_fold: int = 0             # nút giống hệt HOẶC chỉ khác trình bày (fold)

    @property
    def n_match_pct(self) -> float:
        return self.n_match / max(self.n_theirs, 1)

    @property
    def n_khop_chuan_hoa_pct(self) -> float:
        return self.n_match_fold / max(self.n_theirs, 1)

    def by_kind(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for d in self.diffs:
            out[d.kind] = out.get(d.kind, 0) + 1
        return out

    def dieu_with_diffs(self, kem_trinh_bay: bool = False) -> list[str]:
        """Các Điều có sai khác nội dung (mặc định bỏ khác biệt chỉ về trình bày)."""
        return sorted({d.key.split("/")[0] if d.key.startswith("dieu") else d.key
                       for d in self.diffs if kem_trinh_bay or d.kind != "khac_trinh_bay"}, key=_natural)


def _natural(k: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", k)]


def _norm(text: str | None) -> str:
    return normalize_text(text or "")


def key_of(loai: str, ky_hieu: str, parent_key: str | None) -> str:
    here = f"{loai} {ky_hieu}"
    if loai == "dieu":
        return here                                    # số Điều là duy nhất trong bộ luật
    return f"{parent_key}/{here}" if parent_key else here


def items_from_nodes(roots: list[Node]) -> tuple[dict[str, Item], list[str]]:
    """Từ cây parse của văn bản hợp nhất. Trả về (các nút, khoá các nút ghi '(được bãi bỏ)' — không đưa vào dict)."""
    out: dict[str, Item] = {}
    repealed: list[str] = []

    def walk(node: Node, parent_key: str | None, container: str | None, order: int) -> None:
        key = key_of(node.loai, node.ky_hieu, parent_key)
        td, nd = _norm(node.tieu_de), _norm(node.noi_dung)
        if REPEALED.match(td) or REPEALED.match(nd) and not node.children:
            repealed.append(key)
            return
        out[key] = Item(key, node.loai, node.ky_hieu, td, nd, container, order, node)
        next_container = key if node.loai in ("phan", "chuong", "muc", "tieu_muc") else container
        for i, ch in enumerate(node.children):
            walk(ch, key, next_container, i)

    for i, r in enumerate(roots):
        walk(r, None, None, i)
    return out, repealed


def items_from_db(conn: sqlite3.Connection, van_ban_id: int, ngay: str) -> dict[str, Item]:
    rows = conn.execute(
        """SELECT d.id, d.cha_id, d.loai, p.ky_hieu, p.tieu_de, p.noi_dung, p.thu_tu
           FROM don_vi_luat d JOIN phien_ban_noi_dung p ON p.don_vi_id = d.id
           WHERE d.van_ban_id = :vb AND p.hieu_luc_tu <= :d AND (p.hieu_luc_den IS NULL OR :d < p.hieu_luc_den)
           ORDER BY p.thu_tu, d.id""", {"vb": van_ban_id, "d": ngay}).fetchall()
    by_id = {r["id"]: r for r in rows}
    keys: dict[int, str] = {}

    def key(r) -> str:
        if r["id"] not in keys:
            parent = by_id.get(r["cha_id"]) if r["cha_id"] else None
            keys[r["id"]] = key_of(r["loai"], r["ky_hieu"], key(parent) if parent is not None else None)
        return keys[r["id"]]

    sib_order: dict[object, int] = {}
    out: dict[str, Item] = {}
    for r in rows:
        k = key(r)
        parent = by_id.get(r["cha_id"]) if r["cha_id"] else None
        container = None
        cur = parent
        while cur is not None and container is None:
            if cur["loai"] in ("phan", "chuong", "muc", "tieu_muc"):
                container = key(cur)
            cur = by_id.get(cur["cha_id"]) if cur["cha_id"] else None
        n = sib_order.get(r["cha_id"], 0)
        sib_order[r["cha_id"]] = n + 1
        if k in out:
            raise ValueError(f"CSDL có hai nút trùng khoá {k} tại {ngay}")
        out[k] = Item(k, r["loai"], r["ky_hieu"], _norm(r["tieu_de"]), _norm(r["noi_dung"]), container, n, r["id"])
    return out


def _brief_diff(a: str, b: str, width: int = 40) -> str:
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    parts = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        ctx = a[max(0, i1 - width // 2): i1]
        parts.append(f"…{ctx}[{a[i1:i2]}→{b[j1:j2]}]")
        if len(parts) >= 3:
            break
    return " ".join(parts)


def compare(ours: dict[str, Item], theirs: dict[str, Item], repealed_theirs: list[str] | None = None) -> CompareResult:
    res = CompareResult(len(ours), len(theirs), 0, repealed_theirs=sorted(repealed_theirs or [], key=_natural))
    rep = set(repealed_theirs or [])
    for k in sorted(set(ours) | set(theirs), key=_natural):
        o, t = ours.get(k), theirs.get(k)
        if t is None:
            note = "văn bản hợp nhất ghi '(được bãi bỏ)'" if k in rep else ""
            res.diffs.append(Diff("thua_o_ta", k, ours=(o.tieu_de + " | " + o.noi_dung)[:200], note=note))
            continue
        if o is None:
            res.diffs.append(Diff("thieu_o_ta", k, theirs=(t.tieu_de + " | " + t.noi_dung)[:200]))
            continue
        ok = ok_fold = True
        for field_name, kind, a, b in (("tieu_de", "khac_tieu_de", o.tieu_de, t.tieu_de), ("noi_dung", "khac_noi_dung", o.noi_dung, t.noi_dung)):
            if a == b:
                continue
            ok = False
            if fold(a) == fold(b):
                res.diffs.append(Diff("khac_trinh_bay", k, a, b, _brief_diff(a, b)))
            else:
                ok_fold = False
                res.diffs.append(Diff(kind, k, a, b, _brief_diff(a, b)))
        if o.cha != t.cha and t.loai == "dieu":
            ok = ok_fold = False
            res.diffs.append(Diff("khac_vi_tri", k, str(o.cha), str(t.cha), "nằm dưới Chương/Mục khác"))
        res.n_match += ok
        res.n_match_fold += ok_fold
    # thứ tự anh em: so sánh dãy ký hiệu theo thứ tự xuất hiện, trong từng nhóm cha, chỉ trên các nút có ở cả hai bên
    def seq(items: dict[str, Item]) -> dict[str | None, list[str]]:
        g: dict[str | None, list[str]] = {}
        for it in sorted(items.values(), key=lambda i: (i.cha or "", i.thu_tu)):
            g.setdefault(it.key.rsplit("/", 1)[0] if "/" in it.key else (it.cha if it.loai != "dieu" else it.cha), []).append(it.key)
        return g

    common = set(ours) & set(theirs)
    go, gt = seq({k: v for k, v in ours.items() if k in common}), seq({k: v for k, v in theirs.items() if k in common})
    for g, ks in gt.items():
        if go.get(g) != ks:
            res.diffs.append(Diff("khac_vi_tri", f"thứ tự anh em dưới {g}", ", ".join(go.get(g, []))[:150], ", ".join(ks)[:150], "thứ tự khác"))
    return res


# ---------------------------------------------------------------------------------------------------------------------
# Khác biệt trình bày và đề xuất sửa chữ

# Dấu thanh đặt kiểu cũ -> kiểu mới (hoà/hòa, thuỷ/thủy, khoẻ/khỏe...) và vài cặp chính tả đồng nghĩa. Danh sách CỐ ĐỊNH và ngắn:
# chỉ những khác biệt thật sự không đổi nghĩa mới được coi là "tương đương"; thêm cặp mới phải có chủ ý (và test).
_TONE = {"oá": "óa", "oà": "òa", "oả": "ỏa", "oã": "õa", "oạ": "ọa", "oé": "óe", "oè": "òe", "oẻ": "ỏe", "oẽ": "õe", "oẹ": "ọe",
         "uý": "úy", "uỳ": "ùy", "uỷ": "ủy", "uỹ": "ũy", "uỵ": "ụy"}
_VARIANTS = (("sỹ", "sĩ"), ("hàng tháng", "hằng tháng"), ("hàng năm", "hằng năm"), ("hàng ngày", "hằng ngày"))
_PUNCT = re.compile(r"[\s.,;:!?“”\"'‘’()\[\]\-–—]+")


def fold(text: str | None) -> str:
    """Dạng so sánh 'bỏ trình bày': NFC, chữ thường, dấu thanh về một kiểu, bỏ khoảng trắng và dấu câu.
    Hai văn bản có fold() giống nhau chỉ khác cách trình bày; KHÔNG bỏ chữ số, chữ cái hay từ."""
    s = unicodedata.normalize("NFC", normalize_text(text or "")).lower()
    for a, b in _TONE.items():
        s = s.replace(a, b)
    for a, b in _VARIANTS:
        s = s.replace(a, b)
    s = re.sub(r"(?<![\d.,])0+(?=\d)", "", s)          # 07 ~ 7 (số 0 đứng đầu số); "0,05" giữ nguyên
    return _PUNCT.sub("", s)


@dataclass
class Edit:
    """Một sửa chữ nhỏ: thay đúng MỘT chỗ xuất hiện của tu_cu bằng thanh_moi (cả hai kèm vài từ ngữ cảnh để duy nhất)."""
    tu_cu: str
    thanh_moi: str
    loai: str          # loi_go (<=4 từ lệch) | nhieu_chu (nhiều từ hơn) | sai_so_lieu (có chữ số)
    da_xoa: str = ""   # các từ bên ta bị bỏ/thay (để hiển thị)
    da_them: str = ""  # các từ bên văn bản hợp nhất

    def to_dict(self) -> dict:
        return dict(self.__dict__)


_TOKEN = re.compile(r"\d+(?:[.,]\d+)*|\w+|[^\w\s]", re.UNICODE)    # số có dấu chấm/phẩy (1.000.000.000, 0,05) là MỘT từ


def _keys(words: list[str]) -> list[str]:
    """Khoá so sánh từng từ: fold(), và cặp từ đồng nghĩa chính tả hai chữ ('hàng tháng' ~ 'hằng tháng') cũng về một khoá."""
    keys = [fold(w) for w in words]            # fold() cũng bỏ số 0 đầu số: 07 ~ 7
    low = [w.lower() for w in words]
    for a, b in _VARIANTS:
        pa, pb = a.split(), b.split()
        if len(pa) == 2:
            for i in range(len(low) - 1):
                if low[i] == pa[0] and low[i + 1] == pa[1]:
                    keys[i], keys[i + 1] = fold(pb[0]), fold(pb[1])
    return keys


def _toks(s: str) -> list[tuple[str, int, int, bool]]:
    return [(m.group(), m.start(), m.end(), m.group()[0].isalnum() or m.group()[0] == "_") for m in _TOKEN.finditer(s)]


def de_xuat_sua(ours: str, theirs: str, *, gop_neu_cach: int = 2, ngu_canh_toi_da: int = 8) -> tuple[list[Edit], bool]:
    """Các sửa chữ để đưa `ours` về `theirs` ở mức TỪ (bỏ qua khác biệt trình bày). Trả về (danh sách, đã_kiểm_chứng).
    đã_kiểm_chứng: áp lần lượt từng Edit lên `ours` (mỗi tu_cu xuất hiện đúng 1 lần) thì ra văn bản có fold() bằng fold(theirs).
    Giữ nguyên cách trình bày của `ours` ở phần không sai khác."""
    ours, theirs = normalize_text(ours or ""), normalize_text(theirs or "")
    if fold(ours) == fold(theirs):
        return [], True
    ot, tt = _toks(ours), _toks(theirs)
    ow = [i for i, t in enumerate(ot) if t[3]]
    tw = [i for i, t in enumerate(tt) if t[3]]
    if not ow or not tw:                       # một bên không có chữ nào: không có điểm tựa để đặt sửa chữ nhỏ -> để người xem
        return [], False
    ok_ = _keys([ot[i][0] for i in ow])
    tk_ = _keys([tt[i][0] for i in tw])
    ops = [o for o in difflib.SequenceMatcher(None, ok_, tk_, autojunk=False).get_opcodes() if o[0] != "equal"]
    groups: list[list[int]] = []
    for _, i1, i2, j1, j2 in ops:
        if groups and i1 - groups[-1][1] <= gop_neu_cach:
            groups[-1][1], groups[-1][3] = i2, j2
        else:
            groups.append([i1, i2, j1, j2])
    edits: list[Edit] = []
    for i1, i2, j1, j2 in groups:
        removed = [ot[ow[i]][0] for i in range(i1, i2)]
        added = [tt[tw[j]][0] for j in range(j1, j2)]
        their = theirs[tt[tw[j1]][1]: tt[tw[j2 - 1]][2]] if j2 > j1 else ""
        e: Edit | None = None
        for k in range(1, ngu_canh_toi_da + 1):
            lo, hi = max(0, i1 - k), min(len(ow), i2 + k)
            ws = ot[ow[lo]][1] if lo < len(ow) else 0
            we = ot[ow[hi - 1]][2] if hi > lo else len(ours)
            if i2 > i1:
                a, b = ot[ow[i1]][1], ot[ow[i2 - 1]][2]
                if j2 > j1:
                    new = ours[ws:a] + their + ours[b:we]
                else:                                                         # bên ta thừa chữ
                    left, right = ours[ws:a].rstrip(), ours[b:we].lstrip()
                    new = left + (" " if left and right and right[0].isalnum() else "") + right
            elif i1 < len(ow):                                                # bên ta thiếu chữ
                pos, pos_end = ot[ow[i1]][1], ot[ow[i1]][2]
                prev_end = ot[ow[i1 - 1]][2] if i1 > 0 else None
                gap_o = ours[prev_end:pos].strip() if prev_end is not None else ""
                gap_t = theirs[tt[tw[j2 - 1]][2]: tt[tw[j2]][1] if j2 < len(tw) else len(theirs)].strip()
                if gap_o and gap_t and gap_o[0] == gap_t[0] and not gap_o[0].isalnum():
                    # văn bản hợp nhất đặt chữ thiếu TRƯỚC dấu câu ("... phạm bị. Ngày"): chèn ngay sau từ đứng trước dấu câu
                    new = ours[ws:prev_end] + " " + their + ours[prev_end:we]
                else:
                    # chèn ngay trước từ i1 (giữ dấu câu đứng trước nó); từ đứng ngay sau chỗ chèn lấy cách viết (hoa/thường) của
                    # văn bản hợp nhất, vì chỗ chèn có thể làm nó thôi đứng đầu câu
                    nxt = tt[tw[j2]][0] if j2 < len(tw) else ours[pos:pos_end]
                    new = ours[ws:pos] + their + " " + nxt + ours[pos_end:we]
            else:                                                             # thiếu ở cuối: chèn ngay sau từ cuối, trước dấu câu kết thúc
                end = ot[ow[i1 - 1]][2]
                new = ours[ws:end] + " " + their + ours[end:we]
            old = ours[ws:we]
            if ours.count(old) == 1 and old != new:
                digits = any(ch.isdigit() for ch in "".join(removed + added))
                loai = "sai_so_lieu" if digits else ("loi_go" if len(removed) + len(added) <= 4 else "nhieu_chu")
                e = Edit(old, new, loai, " ".join(removed), " ".join(added))
                break
        if e is None:
            return edits, False
        edits.append(e)
    out = ours
    for e in edits:
        if out.count(e.tu_cu) != 1:
            return edits, False
        out = out.replace(e.tu_cu, e.thanh_moi, 1)
    return edits, fold(out) == fold(theirs)


def ap_dung_sua(text: str, tu_cu: str, thanh_moi: str) -> str | None:
    """Thay đúng một chỗ xuất hiện; None nếu tu_cu không có hoặc có nhiều hơn một chỗ (mơ hồ)."""
    return text.replace(tu_cu, thanh_moi, 1) if text.count(tu_cu) == 1 else None


def _trang_thai_tham_chieu(it: Item | None, f: str, o: str, t: str) -> str:
    if it is None:
        return "khong_co_nut"
    x = getattr(it, f)
    if fold(x) == fold(t):
        return "cung_sua"                    # bản tham chiếu viết giống văn bản hợp nhất đang so (tức đồng thuận với việc sửa)
    if fold(x) == fold(o):
        return "giong_ban_he_thong"
    return "khac"                            # khác cả hai (thường do luật sửa đổi ở giữa hai mốc)


def lap_de_xuat(ours: dict[str, Item], theirs: dict[str, Item], tham_chieu: dict[str, dict[str, Item]],
                xac_minh: dict[str, list[dict]] | None = None, *, nhan_nguon: str, chi_nut_xac_minh: bool = False) -> tuple[list[dict], list[dict]]:
    """Từ các nút khác nhau (sau khi bỏ khác biệt trình bày) lập đề xuất hiệu đính {khoa, truong, tu_cu, thanh_moi, loai, bang_chung}.

    Điều kiện để ĐỀ XUẤT một nút: (1) sửa được bằng các thay đổi mức từ mà áp lên bản ta ra đúng văn bản hợp nhất (de_xuat_sua đã kiểm chứng);
    (2) có bằng chứng ngoài chính văn bản hợp nhất đang so: ít nhất một bản tham chiếu khác viết giống nó ('cung_sua'),
    hoặc có xác minh nguồn chính thức do người đối chiếu ghi (xac_minh[khoa]). Nút không đạt (2) hoặc (1) vào danh sách thứ hai (không đề xuất).
    chi_nut_xac_minh: chỉ xét các nút có xac_minh (dùng cho so sánh mốc lịch sử, nơi chỉ muốn sửa những chỗ đã kiểm nguồn)."""
    xac_minh = xac_minh or {}
    de_xuat: list[dict] = []
    khong: list[dict] = []
    for k in sorted(set(ours) & set(theirs), key=_natural):
        o, t = ours[k], theirs[k]
        for f in ("tieu_de", "noi_dung"):
            a, b = getattr(o, f), getattr(t, f)
            if a == b or fold(a) == fold(b):
                continue
            if chi_nut_xac_minh and k not in xac_minh:
                continue
            edits, ok = de_xuat_sua(a, b)
            if not ok or not edits:
                khong.append({"khoa": k, "truong": f, "ly_do": "khong_tu_dong", "ours": a, "theirs": b})
                continue
            tc = {name: _trang_thai_tham_chieu(items.get(k), f, a, b) for name, items in tham_chieu.items()}
            if not (any(v == "cung_sua" for v in tc.values()) or k in xac_minh):
                khong.append({"khoa": k, "truong": f, "ly_do": "thieu_bang_chung", "ours": a, "theirs": b, "tham_chieu": tc})
                continue
            bc = {"nguon_so_sanh": nhan_nguon, "tham_chieu": tc}
            if k in xac_minh:
                bc["xac_minh"] = xac_minh[k]
            for e in edits:
                de_xuat.append({"khoa": k, "truong": f, "tu_cu": e.tu_cu, "thanh_moi": e.thanh_moi, "loai": e.loai,
                                "bang_chung": bc, "da_xoa": e.da_xoa, "da_them": e.da_them})
    return de_xuat, khong


def nap_vbhn_json(path) -> tuple[dict[str, Item], list[str]]:
    """Đọc vbhn.json (do scripts/doi_chieu_vbhn.py trich tạo) rồi parse thành các nút để so sánh."""
    import json
    from pathlib import Path

    from src.ingest.vbhn_pdf import VbhnText
    from src.parse.base_law import parse_body

    v = VbhnText.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
    roots, _pre, _warn = parse_body(v.lines)
    return items_from_nodes(roots)

