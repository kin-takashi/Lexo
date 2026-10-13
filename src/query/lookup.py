"""Tra cứu chính xác "Điều X <tên viết tắt> <năm>" tại một ngày (mặc định: hôm nay). Không dùng LLM, không dùng embedding.

Trả về phiên bản CÓ HIỆU LỰC tại ngày đó (đã áp các luật sửa đổi đã duyệt), kèm NGUỒN từng nút bị sửa: luật nào, Điều/khoản nào của luật
đó, hiệu lực từ ngày nào. Có thêm: lịch sử sửa đổi của một Điều, so sánh hai thời điểm, lý do khi Điều không có (đã bãi bỏ / chưa hiệu lực),
và nguyên văn các điều khoản hiệu lực - chuyển tiếp của luật sửa đổi (chỉ hiển thị, hệ thống không tự suy ra hồi tố).
"""
from __future__ import annotations

import difflib
import json
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import date

REF_RE = re.compile(r"^\s*Điều\s+(\d+[a-zđ]?)\s+([A-Za-zĐđ][A-Za-zĐđ0-9]*)(?:\s+(\d{4}))?\s*$", re.IGNORECASE)
_LOAI_VB = {"luat": "Luật", "bo_luat": "Bộ luật", "nghi_quyet": "Nghị quyết", "phap_lenh": "Pháp lệnh", "nghi_dinh": "Nghị định"}
_NAME = {"phan": "Phần", "chuong": "Chương", "muc": "Mục", "tieu_muc": "Tiểu mục", "dieu": "Điều", "khoan": "khoản", "diem": "điểm"}
_THAO_TAC = {"sua_doi": "sửa đổi, bổ sung", "bo_sung": "bổ sung", "bai_bo": "bãi bỏ", "thay_cum_tu": "sửa đổi từ ngữ",
             "danh_so_lai": "đánh số lại", "hoan_hieu_luc": "hoãn hiệu lực"}


def fmt_date(iso: str | None) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}" if iso else "?"


@dataclass
class Nguon:
    """Một lệnh sửa đổi đã tạo ra (hoặc đóng) một phiên bản."""
    lenh_id: int
    so_hieu: str
    ten_van_ban: str
    loai_van_ban: str
    ngay_ban_hanh: str | None
    vi_tri_nguon: str | None
    loai_thao_tac: str
    hieu_luc_tu: str | None
    can_cu_hieu_luc: str | None = None
    tao_moi: bool = False               # lệnh này TẠO nút (bổ sung) chứ không sửa nút có sẵn

    @property
    def ten_ngan(self) -> str:
        return f"{_LOAI_VB.get(self.loai_van_ban, 'Văn bản')} số {self.so_hieu}"

    def mo_ta(self) -> str:
        if self.tao_moi:
            kieu = "bổ sung"
        else:
            kieu = _THAO_TAC.get(self.loai_thao_tac, self.loai_thao_tac)
        pos = f" ({self.vi_tri_nguon})" if self.vi_tri_nguon else ""
        return f"{kieu} bởi {self.ten_ngan}{pos}, hiệu lực từ {fmt_date(self.hieu_luc_tu)}"


@dataclass
class UnitView:
    loai: str
    ky_hieu: str
    tieu_de: str | None
    noi_dung: str
    children: list[UnitView] = field(default_factory=list)
    hieu_luc_tu: str | None = None
    hieu_luc_den: str | None = None
    nguon: list[Nguon] = field(default_factory=list)      # rỗng = nguyên văn bản gốc; nhiều phần tử = nhiều lệnh cùng ngày nối nhau
    hieu_dinh: list[dict] = field(default_factory=list)   # các quy tắc hiệu đính kỹ thuật đã áp vào nút (id, tu_cu, thanh_moi, loai, nguon)

    def walk(self):
        yield self
        for c in self.children:
            yield from c.walk()

    @property
    def da_sua(self) -> bool:
        return bool(self.nguon)


def parse_reference(text: str) -> tuple[str, str, int | None] | None:
    """'Điều 173a BLHS 2015' -> ('173a', 'BLHS', 2015). None nếu không đúng dạng."""
    m = REF_RE.match(text)
    if not m:
        return None
    return m.group(1).lower(), m.group(2).upper(), int(m.group(3)) if m.group(3) else None


def find_van_ban(conn: sqlite3.Connection, viet_tat: str, nam: int | None = None) -> list[sqlite3.Row]:
    rows = conn.execute(
        "SELECT * FROM van_ban WHERE upper(ten_viet_tat) = upper(?) ORDER BY ngay_ban_hanh", (viet_tat,)
    ).fetchall()
    if nam is None:
        return rows
    out = []
    for r in rows:
        year = int(r["ngay_ban_hanh"][:4]) if r["ngay_ban_hanh"] else None
        if year == nam or f"/{nam}/" in r["so_hieu"]:
            out.append(r)
    return out


# ---------------------------------------------------------------------------------------------------------------------
# Nguồn (provenance)

class _Prov:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self._cache: dict[int, Nguon] = {}
        self._hd: dict[int, dict] = {}

    def lenh(self, lenh_id: int, tao_moi: bool = False) -> Nguon:
        key = lenh_id * 2 + int(tao_moi)
        if key not in self._cache:
            r = self.conn.execute(
                """SELECT l.id, l.vi_tri_nguon, l.loai_thao_tac, l.hieu_luc_tu, l.can_cu_hieu_luc,
                          v.so_hieu, v.ten_day_du, v.loai, v.ngay_ban_hanh
                   FROM lenh_sua_doi l JOIN van_ban v ON v.id = l.van_ban_nguon_id WHERE l.id = ?""", (lenh_id,)).fetchone()
            self._cache[key] = Nguon(r["id"], r["so_hieu"], r["ten_day_du"], r["loai"], r["ngay_ban_hanh"], r["vi_tri_nguon"],
                                     r["loai_thao_tac"], r["hieu_luc_tu"], r["can_cu_hieu_luc"], tao_moi)
        return self._cache[key]

    def hieu_dinh(self, ids_json: str | None) -> list[dict]:
        out = []
        for i in json.loads(ids_json) if ids_json else []:
            if i not in self._hd:
                r = self.conn.execute("SELECT * FROM hieu_dinh WHERE id = ?", (i,)).fetchone()
                bc = json.loads(r["bang_chung_json"]) if r else {}
                nguon = [x.get("nguon", "") for x in bc.get("xac_minh", [])]
                dong = [k for k, v in (bc.get("tham_chieu") or {}).items() if v == "cung_sua"]
                self._hd[i] = {"id": i, "tu_cu": r["tu_cu"], "thanh_moi": r["thanh_moi"], "loai": r["loai"], "khoa": r["khoa"],
                               "nguoi_duyet": r["nguoi_duyet"], "ngay_duyet": r["ngay_duyet"],
                               "nguon_so_sanh": bc.get("nguon_so_sanh", ""), "dong_thuan": dong, "da_kiem_nguon": nguon} if r else {"id": i}
            out.append(self._hd[i])
        return out

    def chain(self, don_vi_id: int, hieu_luc_tu: str, lenh_id: int | None, node_lenh_tao: int | None) -> list[Nguon]:
        """Các lệnh dẫn tới phiên bản đang hiển thị: những phiên bản trung gian có khoảng rỗng cùng ngày (nhiều lệnh cùng ngày) rồi tới lệnh hiện tại."""
        if lenh_id is None:
            return []
        ids = [r[0] for r in self.conn.execute(
            "SELECT lenh_tao_ra_id FROM phien_ban_noi_dung WHERE don_vi_id = ? AND hieu_luc_tu = ? AND hieu_luc_den = ? "
            "AND lenh_tao_ra_id IS NOT NULL ORDER BY id", (don_vi_id, hieu_luc_tu, hieu_luc_tu))]
        ids.append(lenh_id)
        return [self.lenh(i, tao_moi=(i == node_lenh_tao)) for i in ids]


def _select(nguyen_van: bool) -> str:
    """nguyen_van=True: lấy văn bản NHƯ LUẬT BAN HÀNH (trước hiệu đính kỹ thuật) thay vì bản đã hiệu đính."""
    td, nd = ("COALESCE(pb.tieu_de_goc, pb.tieu_de)", "COALESCE(pb.noi_dung_goc, pb.noi_dung)") if nguyen_van else ("pb.tieu_de", "pb.noi_dung")
    return f"""SELECT dv.id, dv.loai, dv.lenh_tao_ra_id AS dv_lenh, pb.ky_hieu, {td} AS tieu_de, {nd} AS noi_dung, pb.hieu_luc_tu, pb.hieu_luc_den,
                      pb.lenh_tao_ra_id, pb.hieu_dinh_json
               FROM don_vi_luat dv JOIN phien_ban_noi_dung pb ON pb.don_vi_id = dv.id"""


_SELECT = _select(False)


def _view(prov: _Prov, r: sqlite3.Row, children: list[UnitView], nguyen_van: bool = False) -> UnitView:
    return UnitView(r["loai"], r["ky_hieu"], r["tieu_de"], r["noi_dung"], children, r["hieu_luc_tu"], r["hieu_luc_den"],
                    prov.chain(r["id"], r["hieu_luc_tu"], r["lenh_tao_ra_id"], r["dv_lenh"]),
                    [] if nguyen_van else prov.hieu_dinh(r["hieu_dinh_json"]))


def _load_children(conn: sqlite3.Connection, prov: _Prov, parent_id: int, ngay: str, nguyen_van: bool = False) -> list[UnitView]:
    rows = conn.execute(
        _select(nguyen_van) + """ WHERE dv.cha_id = :p AND pb.hieu_luc_tu <= :d AND (pb.hieu_luc_den IS NULL OR :d < pb.hieu_luc_den)
                      ORDER BY pb.thu_tu, dv.id""", {"p": parent_id, "d": ngay}).fetchall()
    return [_view(prov, r, _load_children(conn, prov, r["id"], ngay, nguyen_van), nguyen_van) for r in rows]


def get_dieu(conn: sqlite3.Connection, van_ban_id: int, ky_hieu: str, ngay: str | None = None, nguyen_van: bool = False) -> UnitView | None:
    """Điều `ky_hieu` của văn bản tại ngày `ngay` (ISO; mặc định hôm nay). None nếu không có/không có hiệu lực tại ngày đó.
    nguyen_van=True: văn bản như luật ban hành, KHÔNG kèm hiệu đính kỹ thuật (bảng hieu_dinh)."""
    ngay = ngay or date.today().isoformat()
    row = conn.execute(
        _select(nguyen_van) + """ WHERE dv.van_ban_id = :vb AND dv.loai = 'dieu' AND pb.ky_hieu = :k
                      AND pb.hieu_luc_tu <= :d AND (pb.hieu_luc_den IS NULL OR :d < pb.hieu_luc_den)""",
        {"vb": van_ban_id, "k": ky_hieu, "d": ngay}).fetchone()
    if row is None:
        return None
    prov = _Prov(conn)
    return _view(prov, row, _load_children(conn, prov, row["id"], ngay, nguyen_van), nguyen_van)


def get_cay(conn: sqlite3.Connection, van_ban_id: int, ngay: str | None = None, nguyen_van: bool = False) -> list[UnitView]:
    """Toàn bộ cây (Phần/Chương/Mục/Điều/khoản/điểm) của văn bản tại ngày `ngay` (mặc định hôm nay), đúng thứ tự trong văn bản,
    mỗi nút kèm nguồn sửa đổi và hiệu đính như get_dieu. Dùng để xuất bản hợp nhất."""
    ngay = ngay or date.today().isoformat()
    rows = conn.execute(
        _select(nguyen_van) + """ WHERE dv.van_ban_id = :vb AND dv.cha_id IS NULL AND pb.hieu_luc_tu <= :d AND (pb.hieu_luc_den IS NULL OR :d < pb.hieu_luc_den)
                      ORDER BY pb.thu_tu, dv.id""", {"vb": van_ban_id, "d": ngay}).fetchall()
    prov = _Prov(conn)
    return [_view(prov, r, _load_children(conn, prov, r["id"], ngay, nguyen_van), nguyen_van) for r in rows]


def dieu_status(conn: sqlite3.Connection, van_ban_id: int, ky_hieu: str, ngay: str | None = None) -> str:
    """Giải thích vì sao KHÔNG có Điều tại ngày: chưa từng có / chưa có hiệu lực / đã bị bãi bỏ (bởi luật nào)."""
    ngay = ngay or date.today().isoformat()
    rows = conn.execute(
        """SELECT pb.hieu_luc_tu, pb.hieu_luc_den, pb.lenh_dong_id, pb.lenh_tao_ra_id, dv.lenh_tao_ra_id AS dv_lenh
           FROM don_vi_luat dv JOIN phien_ban_noi_dung pb ON pb.don_vi_id = dv.id
           WHERE dv.van_ban_id = ? AND dv.loai = 'dieu' AND pb.ky_hieu = ? AND pb.hieu_luc_tu < COALESCE(pb.hieu_luc_den, '9999-12-31')
           ORDER BY pb.hieu_luc_tu""", (van_ban_id, ky_hieu)).fetchall()
    if not rows:
        return f"Điều {ky_hieu} chưa từng có trong văn bản này."
    prov = _Prov(conn)
    first = rows[0]
    if ngay < first["hieu_luc_tu"]:
        if first["dv_lenh"]:
            return f"Điều {ky_hieu} được thêm vào từ {fmt_date(first['hieu_luc_tu'])} ({prov.lenh(first['dv_lenh'], True).mo_ta()}); chưa có tại ngày {fmt_date(ngay)}."
        return f"Văn bản chưa có hiệu lực tại ngày {fmt_date(ngay)} (hiệu lực từ {fmt_date(first['hieu_luc_tu'])})."
    last = rows[-1]
    if last["hieu_luc_den"] and ngay >= last["hieu_luc_den"]:
        who = f" bởi {prov.lenh(last['lenh_dong_id']).ten_ngan} ({prov.lenh(last['lenh_dong_id']).vi_tri_nguon})" if last["lenh_dong_id"] else ""
        return f"Điều {ky_hieu} đã hết hiệu lực từ {fmt_date(last['hieu_luc_den'])}{who}."
    return f"Điều {ky_hieu} không có hiệu lực tại ngày {fmt_date(ngay)}."


# ---------------------------------------------------------------------------------------------------------------------
# Hiển thị

def nhan_duyet(r: dict) -> str:
    """'duyệt: TÊN' hoặc 'CHƯA DUYỆT' (quy tắc chỉ có trong bản xem trước)."""
    return f"duyệt: {r['nguoi_duyet']}" if r.get("nguoi_duyet") else "CHƯA DUYỆT"


def _note_hieu_dinh(u: UnitView) -> str:
    if not u.hieu_dinh:
        return ""
    parts = []
    for r in u.hieu_dinh:
        base = (r.get("nguon_so_sanh") or "").split(" (")[0]
        kiem = ", đã kiểm Công báo" if r.get("da_kiem_nguon") else ""
        parts.append(f"“{r.get('tu_cu', '?')}” → “{r.get('thanh_moi', '?')}” (theo {base or 'văn bản hợp nhất'}{kiem}; {nhan_duyet(r)})")
    return "  [hiệu đính kỹ thuật: " + "; ".join(parts) + "]"


def _note(u: UnitView, parent_nguon: tuple[int, ...] = ()) -> str:
    """Ghi chú nguồn của nút; bỏ qua nếu nút cùng nguồn với nút cha (đã ghi ở cha, tránh lặp ở từng khoản/điểm con)."""
    hd = _note_hieu_dinh(u)
    if not u.nguon or tuple(n.lenh_id for n in u.nguon) == parent_nguon:
        return hd
    return "  [" + "; rồi ".join(n.mo_ta() for n in u.nguon) + "]" + hd


def render(unit: UnitView, depth: int = 0, ghi_chu: bool = False, _parent: tuple[int, ...] = ()) -> str:
    """Văn bản đọc được của một đơn vị và các đơn vị con. ghi_chu=True: kèm nguồn sửa đổi sau từng nút đã bị sửa
    (nút con cùng nguồn với nút cha thì không lặp lại ghi chú)."""
    pad = "  " * max(0, depth - 1)
    note = _note(unit, _parent) if ghi_chu else ""
    if unit.loai == "dieu":
        head = f"Điều {unit.ky_hieu}. {unit.tieu_de or ''}".rstrip()
    elif unit.loai == "khoan":
        head = f"{unit.ky_hieu}. {unit.noi_dung}".rstrip() if unit.noi_dung else f"{unit.ky_hieu}."
    elif unit.loai == "diem":
        head = f"{unit.ky_hieu}) {unit.noi_dung}".rstrip() if unit.noi_dung else f"{unit.ky_hieu})"
    else:
        head = f"{unit.loai} {unit.ky_hieu}. {unit.tieu_de or ''}".rstrip()
    lines = [pad + head + (note if unit.loai != "dieu" or not unit.noi_dung else "")]
    if unit.loai == "dieu" and unit.noi_dung:
        lines.append(unit.noi_dung + note)
    for child in unit.children:
        lines.append(render(child, depth + 1, ghi_chu, tuple(n.lenh_id for n in unit.nguon)))
    return "\n".join(lines)


def tom_tat_nguon(unit: UnitView) -> list[Nguon]:
    """Các lệnh (không trùng) đã tác động lên cây con của unit, theo ngày hiệu lực."""
    seen: dict[int, Nguon] = {}
    for u in unit.walk():
        for n in u.nguon:
            seen.setdefault(n.lenh_id, n)
    return sorted(seen.values(), key=lambda n: (n.hieu_luc_tu or "", n.lenh_id))


# ---------------------------------------------------------------------------------------------------------------------
# Lịch sử và so sánh

@dataclass
class SuKien:
    ngay: str
    so_hieu: str
    ten_ngan: str
    vi_tri_nguon: str | None
    loai_thao_tac: str
    nut: list[str]                  # các nút bị tác động, vd ['khoản 2 (sửa đổi)', 'điểm c khoản 1 (bãi bỏ)']

    def mo_ta(self, toi_da: int = 10) -> str:
        nut = self.nut if len(self.nut) <= toi_da else self.nut[:toi_da] + [f"… và {len(self.nut) - toi_da} nút khác"]
        return f"{self.ten_ngan}" + (f" ({self.vi_tri_nguon})" if self.vi_tri_nguon else "") + ": " + "; ".join(nut)


def lich_su_dieu(conn: sqlite3.Connection, van_ban_id: int, ky_hieu: str) -> list[SuKien]:
    """Mọi sửa đổi từng tác động lên Điều (kể cả khoản, điểm của nó), theo thứ tự ngày hiệu lực. Không tính bản gốc."""
    roots = [r[0] for r in conn.execute(
        "SELECT DISTINCT dv.id FROM don_vi_luat dv JOIN phien_ban_noi_dung pb ON pb.don_vi_id = dv.id "
        "WHERE dv.van_ban_id = ? AND dv.loai = 'dieu' AND pb.ky_hieu = ?", (van_ban_id, ky_hieu))]
    if not roots:
        return []
    ph = ",".join("?" * len(roots))
    sub = conn.execute(
        f"""WITH RECURSIVE t(id, cha_id, loai) AS (
                SELECT id, cha_id, loai FROM don_vi_luat WHERE id IN ({ph})
                UNION ALL SELECT d.id, d.cha_id, d.loai FROM don_vi_luat d JOIN t ON d.cha_id = t.id)
            SELECT id, cha_id, loai FROM t""", roots).fetchall()
    info = {r["id"]: r for r in sub}
    ky = {}
    for did in info:
        ky[did] = conn.execute("SELECT ky_hieu FROM phien_ban_noi_dung WHERE don_vi_id = ? ORDER BY hieu_luc_tu DESC, id DESC LIMIT 1", (did,)).fetchone()[0]

    def label(did: int) -> str:
        parts, cur = [], did
        while cur in info and info[cur]["loai"] != "dieu":
            parts.append(f"{_NAME[info[cur]['loai']]} {ky[cur]}")
            cur = info[cur]["cha_id"]
        return " ".join(parts) or f"Điều {ky[did]}"

    ids = list(info)
    ph2 = ",".join("?" * len(ids))
    rows = conn.execute(
        f"""SELECT pb.don_vi_id, pb.hieu_luc_tu, pb.hieu_luc_den, pb.lenh_tao_ra_id, pb.lenh_dong_id, dv.lenh_tao_ra_id AS dv_lenh
            FROM phien_ban_noi_dung pb JOIN don_vi_luat dv ON dv.id = pb.don_vi_id
            WHERE pb.don_vi_id IN ({ph2}) AND (pb.lenh_tao_ra_id IS NOT NULL OR pb.lenh_dong_id IS NOT NULL)""", ids).fetchall()
    prov = _Prov(conn)
    events: dict[int, dict] = {}

    def add(lenh_id: int, ngay: str, did: int, what: str) -> None:
        e = events.setdefault(lenh_id, {"ngay": ngay, "nut": {}})
        e["nut"].setdefault(did, what)

    closed_by: dict[int, set[int]] = {}
    for r in rows:
        if r["lenh_tao_ra_id"] and r["hieu_luc_tu"] < (r["hieu_luc_den"] or "9999-12-31"):
            add(r["lenh_tao_ra_id"], r["hieu_luc_tu"], r["don_vi_id"], "bổ sung" if r["dv_lenh"] == r["lenh_tao_ra_id"] else "sửa đổi")
        if r["lenh_dong_id"]:
            still_open_or_replaced = conn.execute(
                "SELECT 1 FROM phien_ban_noi_dung WHERE don_vi_id = ? AND hieu_luc_tu = ? AND hieu_luc_den IS NOT hieu_luc_tu AND lenh_tao_ra_id = ?",
                (r["don_vi_id"], r["hieu_luc_den"], r["lenh_dong_id"])).fetchone()
            if not still_open_or_replaced:
                closed_by.setdefault(r["lenh_dong_id"], set()).add(r["don_vi_id"])
                events.setdefault(r["lenh_dong_id"], {"ngay": r["hieu_luc_den"], "nut": {}})
    for lenh_id, dids in closed_by.items():                 # chỉ ghi nút gốc của cụm bị bãi bỏ, không liệt kê từng nút con
        for did in dids:
            if info[did]["cha_id"] not in dids:
                events[lenh_id]["nut"].setdefault(did, "bãi bỏ")
    out = []
    for lenh_id, e in events.items():
        n = prov.lenh(lenh_id)
        # nút mới tạo dưới một nút cũng bị tác động trong cùng lệnh (Điều 3a mới; khoản viết lại kèm điểm mới): chỉ ghi nút gốc
        hien = {d: w for d, w in e["nut"].items() if not (w == "bổ sung" and info[d]["cha_id"] in e["nut"])}
        out.append((e["ngay"], n, hien))
    gop: dict[tuple, dict] = {}                      # gộp các lệnh cùng ngày, cùng luật, cùng vị trí nguồn thành một dòng lịch sử
    for ngay, n, hien in out:
        g = gop.setdefault((ngay, n.so_hieu, n.vi_tri_nguon or ""), {"n": n, "nut": {}})
        g["nut"].update(hien)
    res = [SuKien(k[0], g["n"].so_hieu, g["n"].ten_ngan, g["n"].vi_tri_nguon, g["n"].loai_thao_tac,
                  [f"{label(d)} ({w})" for d, w in sorted(g["nut"].items())]) for k, g in gop.items()]
    return sorted(res, key=lambda s: (s.ngay, s.so_hieu, s.vi_tri_nguon or ""))


def so_sanh(conn: sqlite3.Connection, van_ban_id: int, ky_hieu: str, ngay_a: str, ngay_b: str) -> str:
    """Khác biệt (dạng unified diff theo dòng) của Điều giữa hai ngày. Chuỗi rỗng nếu giống nhau."""
    a, b = get_dieu(conn, van_ban_id, ky_hieu, ngay_a), get_dieu(conn, van_ban_id, ky_hieu, ngay_b)
    ta = render(a).splitlines() if a else []
    tb = render(b).splitlines() if b else []
    return "\n".join(difflib.unified_diff(ta, tb, fromfile=f"Điều {ky_hieu} @ {fmt_date(ngay_a)}", tofile=f"Điều {ky_hieu} @ {fmt_date(ngay_b)}", lineterm=""))


def dieu_khoan_lien_quan(conn: sqlite3.Connection, van_ban_id: int) -> list[sqlite3.Row]:
    """Điều khoản hiệu lực / chuyển tiếp (nguyên văn) của các luật đã sửa đổi văn bản này, theo thứ tự thời gian."""
    return conn.execute(
        """SELECT v.so_hieu, v.ten_day_du, v.loai AS loai_van_ban, v.ngay_ban_hanh, v.ngay_hieu_luc, k.loai, k.vi_tri, k.noi_dung
           FROM quan_he_van_ban q JOIN van_ban v ON v.id = q.van_ban_a_id JOIN dieu_khoan_van_ban k ON k.van_ban_id = v.id
           WHERE q.van_ban_b_id = ? AND q.loai_quan_he = 'sua_doi'
           ORDER BY v.ngay_hieu_luc, v.so_hieu, k.loai DESC, k.thu_tu""", (van_ban_id,)).fetchall()


def luu_y_hieu_luc(conn: sqlite3.Connection, van_ban_id: int) -> str | None:
    """Cảnh báo khi ngày bắt đầu hiệu lực của văn bản gốc chưa được đối chiếu với nghị quyết hoãn/lùi hiệu lực (nếu có).
    None nếu văn bản có lệnh hoan_hieu_luc đã duyệt (ngày đã được điều chỉnh) hoặc không xác định được ngày hiệu lực."""
    vb = conn.execute("SELECT ngay_hieu_luc, ngay_hieu_luc_theo_van_ban FROM van_ban WHERE id = ?", (van_ban_id,)).fetchone()
    if vb is None or vb["ngay_hieu_luc"] is None:
        return None
    n = conn.execute("SELECT COUNT(*) FROM lenh_sua_doi WHERE van_ban_dich_id = ? AND loai_thao_tac = 'hoan_hieu_luc' "
                     "AND trang_thai_duyet IN ('da_duyet', 'da_sua')", (van_ban_id,)).fetchone()[0]
    if n:
        return None
    return (f"Lưu ý: hệ thống đang lấy ngày bắt đầu hiệu lực của văn bản là {fmt_date(vb['ngay_hieu_luc'])} (theo chính văn bản) và "
            "chưa nạp nghị quyết hoãn/lùi hiệu lực nào; nếu có thì kết quả tra ở các ngày trước mốc thực tế là chưa chính xác.")


def so_lenh_cho_duyet(conn: sqlite3.Connection, van_ban_id: int) -> int:
    """Số lệnh sửa đổi đã nạp nhưng chưa duyệt (nên CHƯA được áp vào kết quả tra cứu)."""
    return conn.execute("SELECT COUNT(*) FROM lenh_sua_doi WHERE van_ban_dich_id = ? AND trang_thai_duyet = 'cho_duyet'",
                        (van_ban_id,)).fetchone()[0]


def so_hieu_dinh_cho_duyet(conn: sqlite3.Connection, van_ban_id: int) -> int:
    """Số đề xuất hiệu đính kỹ thuật đã nạp nhưng chưa được duyệt (chưa ảnh hưởng văn bản hiển thị)."""
    return conn.execute("SELECT COUNT(*) FROM hieu_dinh WHERE van_ban_id = ? AND trang_thai_duyet = 'cho_duyet'", (van_ban_id,)).fetchone()[0]


def hieu_dinh_cho_duyet_dieu(conn: sqlite3.Connection, van_ban_id: int, ky_hieu: str) -> list[sqlite3.Row]:
    """Đề xuất hiệu đính chờ duyệt thuộc Điều `ky_hieu` (kể cả khoản/điểm của Điều)."""
    return conn.execute(
        "SELECT * FROM hieu_dinh WHERE van_ban_id = ? AND trang_thai_duyet = 'cho_duyet' AND (khoa = ? OR khoa LIKE ?) ORDER BY id",
        (van_ban_id, f"dieu {ky_hieu}", f"dieu {ky_hieu}/%")).fetchall()

