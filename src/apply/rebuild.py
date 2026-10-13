"""Engine áp lệnh sửa đổi: dựng lại phien_ban_noi_dung của một văn bản gốc bằng cách PHÁT LẠI (replay) các lệnh.

phien_ban_noi_dung của các nút do lệnh tạo ra là DỮ LIỆU DẪN XUẤT: rebuild() xoá hết rồi dựng lại từ
  (bản gốc do code parse) + (các lệnh trong lenh_sua_doi theo thứ tự hiệu lực).
Nhờ vậy sửa một lệnh sai hay đổi ngày hiệu lực chỉ cần chạy lại rebuild, không phải vá tay từng phiên bản.

Quy ước (xem đầu schema.sql):
  * khoảng hiệu lực nửa mở [hieu_luc_tu, hieu_luc_den), hieu_luc_den NULL = đang hiệu lực;
  * lệnh có hiệu lực từ ngày D: đóng bản đang mở của nút (hieu_luc_den = D, lenh_dong_id) và mở bản mới từ D (lenh_tao_ra_id);
  * hai lệnh cùng ngày cùng nút: bản trung gian có khoảng rỗng [D, D) — không bao giờ hiện ra khi tra theo ngày nhưng còn dấu vết;
  * thứ tự phát lại: hieu_luc_tu, ngày ban hành văn bản nguồn, văn bản nguồn, thứ tự trong văn bản;
  * mỗi lệnh chạy trong một SAVEPOINT: lệnh lỗi thì hoàn tác riêng lệnh đó.
    strict=True (dùng thật): có lệnh lỗi thì hoàn tác toàn bộ và ném RebuildError. strict=False (xem trước): bỏ qua lệnh lỗi, báo cáo.

Không suy ra "điều nào áp dụng cho hành vi nào" (hồi tố, chuyển tiếp): đó là giới hạn đã biết, chỉ lưu nguyên văn ở dieu_khoan_van_ban.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

from src.apply import hieu_dinh as hd
from src.apply.text_ops import apply_phrase
from src.parse.fragment import Fragment, locate, parse_fragment
from src.parse.model import Node

LOI, CANH_BAO = "LỖI", "CẢNH BÁO"
STEP = 1000
TITLED = ("phan", "chuong", "muc", "tieu_muc", "dieu")
NAME = {"phan": "Phần", "chuong": "Chương", "muc": "Mục", "tieu_muc": "Tiểu mục", "dieu": "Điều", "khoan": "khoản", "diem": "điểm"}
DEFAULT_TRANG_THAI = ("da_duyet", "da_sua")


class CommandError(Exception):
    """Lệnh không áp được (đích không có, xung đột ký hiệu, ...). Chỉ hoàn tác lệnh đó."""


class RebuildError(Exception):
    def __init__(self, report: "RebuildReport"):
        self.report = report
        bad = [r for r in report.results if not r.ok]
        super().__init__(f"{len(bad)} lệnh không áp được, đã hoàn tác toàn bộ. Đầu tiên: " +
                         "; ".join(f"#{r.lenh_id} {r.vi_tri_nguon}: {r.problems[0].message}" for r in bad[:3]))


@dataclass
class Problem:
    level: str
    message: str


@dataclass
class CommandResult:
    lenh_id: int
    vi_tri_nguon: str | None
    loai_thao_tac: str
    hieu_luc_tu: str | None
    trang_thai_duyet: str = ""
    problems: list[Problem] = field(default_factory=list)
    versions_created: int = 0
    versions_closed: int = 0
    nodes_created: int = 0
    replacements: int = 0

    @property
    def ok(self) -> bool:
        return not any(p.level == LOI for p in self.problems)


@dataclass
class RebuildReport:
    van_ban_id: int
    ngay_hieu_luc_goc: str
    results: list[CommandResult]
    hieu_dinh: hd.BaoCaoHieuDinh = field(default_factory=hd.BaoCaoHieuDinh)     # kết quả áp hiệu đính (sau khi phát lại các lệnh)

    @property
    def n_ok(self) -> int:
        return sum(1 for r in self.results if r.ok)

    @property
    def n_loi(self) -> int:
        return sum(1 for r in self.results if not r.ok)

    def problems(self, level: str | None = None) -> list[tuple[CommandResult, Problem]]:
        return [(r, p) for r in self.results for p in r.problems if level is None or p.level == level]


# ---------------------------------------------------------------------------------------------------------------------
# Đọc cây hiện có

def _open_row(conn: sqlite3.Connection, don_vi_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """SELECT d.id AS don_vi_id, d.cha_id, d.loai, p.id AS pb_id, p.ky_hieu, p.thu_tu, p.tieu_de, p.noi_dung, p.hieu_luc_tu
           FROM don_vi_luat d JOIN phien_ban_noi_dung p ON p.don_vi_id = d.id AND p.hieu_luc_den IS NULL
           WHERE d.id = ?""", (don_vi_id,)).fetchone()


def _open_children(conn: sqlite3.Connection, cha_id: int) -> list[sqlite3.Row]:
    return conn.execute(
        """SELECT d.id AS don_vi_id, d.cha_id, d.loai, p.id AS pb_id, p.ky_hieu, p.thu_tu, p.tieu_de, p.noi_dung, p.hieu_luc_tu
           FROM don_vi_luat d JOIN phien_ban_noi_dung p ON p.don_vi_id = d.id AND p.hieu_luc_den IS NULL
           WHERE d.cha_id = ? ORDER BY p.thu_tu, d.id""", (cha_id,)).fetchall()


def _label(conn: sqlite3.Connection, don_vi_id: int | None) -> str:
    """'điểm a khoản 1 Điều 5' — dùng trong thông báo lỗi."""
    parts = []
    while don_vi_id:
        r = conn.execute(
            """SELECT d.cha_id, d.loai, p.ky_hieu FROM don_vi_luat d JOIN phien_ban_noi_dung p ON p.don_vi_id = d.id
               WHERE d.id = ? ORDER BY p.hieu_luc_tu DESC, p.id DESC LIMIT 1""", (don_vi_id,)).fetchone()
        if r is None:
            break
        parts.append(f"{NAME[r['loai']]} {r['ky_hieu']}")
        don_vi_id = r["cha_id"]
    return " ".join(parts) or "?"


def _path_text(path: list[tuple[str, str]]) -> str:
    return " ".join(f"{NAME.get(l, l)} {k}" for l, k in reversed(path)) or "(toàn văn bản)"


def _parse_path(raw) -> list[tuple[str, str]]:
    try:
        return [(str(e["loai"]), str(e["ky_hieu"])) for e in raw]
    except (TypeError, KeyError) as e:
        raise CommandError(f"đường dẫn đích không hợp lệ: {raw!r}") from e


def _resolve(conn: sqlite3.Connection, van_ban_id: int, path: list[tuple[str, str]]) -> int:
    """don_vi_id của nút ĐANG MỞ ứng với đường dẫn. Phần tử đầu tìm trên toàn văn bản (phải duy nhất), các phần tử sau là con trực tiếp."""
    if not path:
        raise CommandError("đường dẫn đích rỗng")
    loai, ky = path[0]
    rows = conn.execute(
        """SELECT d.id FROM don_vi_luat d JOIN phien_ban_noi_dung p ON p.don_vi_id = d.id AND p.hieu_luc_den IS NULL
           WHERE d.van_ban_id = ? AND d.loai = ? AND p.ky_hieu = ?""", (van_ban_id, loai, ky)).fetchall()
    if not rows:
        raise CommandError(f"không tìm thấy {_path_text(path[:1])} đang có hiệu lực (chưa có, hoặc đã bị bãi bỏ)")
    if len(rows) > 1:
        raise CommandError(f"{_path_text(path[:1])} không duy nhất trong văn bản ({len(rows)} nút); cần đường dẫn đầy đủ từ Chương")
    cur = rows[0]["id"]
    for i, (loai, ky) in enumerate(path[1:], start=1):
        kids = [r for r in _open_children(conn, cur) if r["loai"] == loai and r["ky_hieu"] == ky]
        if not kids:
            raise CommandError(f"không tìm thấy {_path_text(path[:i + 1])} đang có hiệu lực")
        cur = kids[0]["don_vi_id"]
    return cur


# ---------------------------------------------------------------------------------------------------------------------
# Ghi

class _Ctx:
    def __init__(self, conn, cmd: sqlite3.Row, res: CommandResult):
        self.conn, self.cmd, self.res = conn, cmd, res
        self.ngay = cmd["hieu_luc_tu"]
        self.van_ban_id = cmd["van_ban_dich_id"]


def _close_version(cx: _Ctx, row: sqlite3.Row) -> None:
    if cx.ngay < row["hieu_luc_tu"]:
        raise CommandError(f"ngày hiệu lực {cx.ngay} sớm hơn phiên bản hiện tại của {_label(cx.conn, row['don_vi_id'])} "
                           f"(từ {row['hieu_luc_tu']})")
    cx.conn.execute("UPDATE phien_ban_noi_dung SET hieu_luc_den = ?, lenh_dong_id = ? WHERE id = ?",
                    (cx.ngay, cx.cmd["id"], row["pb_id"]))
    cx.res.versions_closed += 1


def _new_version(cx: _Ctx, don_vi_id: int, ky: str, thu_tu: int, tieu_de: str | None, noi_dung: str, loai: str) -> None:
    cx.conn.execute(
        """INSERT INTO phien_ban_noi_dung (don_vi_id, ky_hieu, thu_tu, tieu_de, noi_dung, hieu_luc_tu, hieu_luc_den,
               van_ban_tao_ra_id, lenh_tao_ra_id, lenh_dong_id, doi_chieu_hop_nhat, nguoi_duyet, ngay_duyet)
           VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, NULL, 'chua_doi_chieu', ?, ?)""",
        (don_vi_id, ky, thu_tu, (tieu_de or None) if loai in TITLED else None, noi_dung or "", cx.ngay,
         cx.cmd["van_ban_nguon_id"], cx.cmd["id"], cx.cmd["nguoi_duyet"], cx.cmd["ngay_duyet"]))
    cx.res.versions_created += 1


def _close_subtree(cx: _Ctx, don_vi_id: int) -> None:
    row = _open_row(cx.conn, don_vi_id)
    if row is not None:
        _close_version(cx, row)
    for (kid,) in cx.conn.execute("SELECT id FROM don_vi_luat WHERE cha_id = ?", (don_vi_id,)).fetchall():
        _close_subtree(cx, kid)


def _create_subtree(cx: _Ctx, cha_id: int, node: Node, thu_tu: int) -> None:
    dv = cx.conn.execute("INSERT INTO don_vi_luat (van_ban_id, cha_id, loai, lenh_tao_ra_id) VALUES (?, ?, ?, ?)",
                         (cx.van_ban_id, cha_id, node.loai, cx.cmd["id"])).lastrowid
    _new_version(cx, dv, node.ky_hieu, thu_tu, node.tieu_de, node.noi_dung, node.loai)
    cx.res.nodes_created += 1
    for k, child in enumerate(node.children, start=1):
        _create_subtree(cx, dv, child, k * STEP)


def _alloc_thu_tu(fixed: list[int | None]) -> list[int]:
    """Cho danh sách vị trí, phần tử None là nút mới: gán thu_tu nằm giữa hai nút anh em đã có, giữ nguyên thứ tự."""
    out: list[int] = []
    i = 0
    while i < len(fixed):
        if fixed[i] is not None:
            out.append(fixed[i])
            i += 1
            continue
        j = i
        while j < len(fixed) and fixed[j] is None:
            j += 1
        m = j - i
        prev = out[-1] if out else None
        nxt = fixed[j] if j < len(fixed) else None
        if prev is not None and nxt is not None:
            if nxt - prev <= m:
                raise CommandError("không còn chỗ trống để chèn nút mới giữa hai nút anh em (thu_tu quá sát nhau)")
            out.extend(prev + (nxt - prev) * k // (m + 1) for k in range(1, m + 1))
        elif prev is not None:
            out.extend(prev + STEP * k for k in range(1, m + 1))
        elif nxt is not None:
            out.extend(nxt - STEP * (m - k + 1) for k in range(1, m + 1))
        else:
            out.extend(STEP * k for k in range(1, m + 1))
        i = j
    return out


def _replace(cx: _Ctx, don_vi_id: int, frag: Node, *, mode: str = "toan_bo") -> None:
    """mode: toan_bo = thay tiêu đề, nội dung và cả các nút con; tieu_de = chỉ tiêu đề; chi_noi_dung = chỉ văn bản riêng của nút (giữ nút con)."""
    cur = _open_row(cx.conn, don_vi_id)
    where = _label(cx.conn, don_vi_id)
    if cur is None:
        raise CommandError(f"{where} không có phiên bản đang hiệu lực")
    if frag.loai != cur["loai"]:
        raise CommandError(f"khối trích dẫn có {NAME[frag.loai]} {frag.ky_hieu} nhưng đích là {where}")
    if frag.ky_hieu != cur["ky_hieu"]:
        raise CommandError(f"khối trích dẫn ghi ký hiệu {frag.ky_hieu} khác ký hiệu đích ({where}); đánh số lại chưa được hỗ trợ")
    if mode == "tieu_de" and cur["loai"] not in TITLED:
        raise CommandError(f"{where} không có tiêu đề để sửa")
    old_title = (cur["tieu_de"] or None) if cur["loai"] in TITLED else None
    new_title = old_title if mode == "chi_noi_dung" else ((frag.tieu_de or None) if cur["loai"] in TITLED else None)
    new_nd = cur["noi_dung"] if mode == "tieu_de" else frag.noi_dung
    if (new_title, new_nd) != (old_title, cur["noi_dung"]):
        _close_version(cx, cur)
        _new_version(cx, don_vi_id, cur["ky_hieu"], cur["thu_tu"], new_title, new_nd, cur["loai"])
    if mode == "toan_bo":
        _sync_children(cx, don_vi_id, frag.children)


def _sync_children(cx: _Ctx, cha_id: int, frag_children: list[Node]) -> None:
    existing = _open_children(cx.conn, cha_id)
    by_key = {(r["loai"], r["ky_hieu"]): r for r in existing}
    keys, plan = set(), []
    for fc in frag_children:
        key = (fc.loai, fc.ky_hieu)
        if key in keys:
            raise CommandError(f"khối trích dẫn có hai {NAME[fc.loai]} {fc.ky_hieu} cùng cấp")
        keys.add(key)
        plan.append((fc, by_key.get(key)))
    for r in existing:
        if (r["loai"], r["ky_hieu"]) not in keys:
            _close_subtree(cx, r["don_vi_id"])                    # khối trích dẫn không còn nút này = nút bị bỏ
    matched = [r["thu_tu"] if r else None for _, r in plan]
    thu_tu = _alloc_thu_tu(matched)
    for (fc, r), tt in zip(plan, thu_tu):
        if r is None:
            _create_subtree(cx, cha_id, fc, tt)
        else:
            _replace(cx, r["don_vi_id"], fc, mode="toan_bo")


def _fragment(cx: _Ctx) -> Fragment:
    text = cx.cmd["noi_dung_moi_duyet"] or cx.cmd["noi_dung_moi"]
    if not text or not text.strip():
        raise CommandError("lệnh cần khối trích dẫn (noi_dung_moi) nhưng đang rỗng")
    frag = parse_fragment(text)
    if not frag.nodes:
        raise CommandError("khối trích dẫn không có Điều/khoản/điểm nào đọc được")
    if frag.preamble:
        cx.res.problems.append(Problem(CANH_BAO, f"khối trích dẫn có đoạn không ký hiệu bị bỏ qua: {frag.preamble[0][:60]!r}"))
    return frag


def _spec(cx: _Ctx) -> dict:
    try:
        spec = json.loads(cx.cmd["dich_json"]) if cx.cmd["dich_json"] else {}
    except json.JSONDecodeError as e:
        raise CommandError(f"dich_json không đọc được: {e}") from e
    return spec


# ---------------------------------------------------------------------------------------------------------------------
# Các thao tác

def _op_sua_doi(cx: _Ctx) -> None:
    spec = _spec(cx)
    targets = spec.get("muc_tieu") or []
    if not targets:
        raise CommandError("sua_doi: thiếu muc_tieu")
    frag = _fragment(cx)
    consumed: set[int] = set()
    for t in targets:
        path = _parse_path(t.get("duong_dan"))
        phan = t.get("phan", "toan_bo")
        if phan not in ("toan_bo", "tieu_de", "chi_noi_dung"):
            raise CommandError(f"sua_doi: phan không hợp lệ: {phan!r}")
        node = locate(frag.nodes, path)
        if node is None:
            raise CommandError(f"khối trích dẫn không chứa {_path_text(path)}")
        _replace(cx, _resolve(cx.conn, cx.van_ban_id, path), node, mode=phan)
        consumed.update(id(n) for n in (node.walk() if phan == "toan_bo" else [node]))
    covered = set(consumed)                                       # cha của nút đã dùng cũng tính là đã dùng
    def mark(n: Node) -> bool:
        used = id(n) in consumed
        for c in n.children:
            used = mark(c) or used
        if used:
            covered.add(id(n))
        return used
    for n in frag.nodes:
        mark(n)
    left = [n for n in frag.walk() if id(n) not in covered]
    if left:
        cx.res.problems.append(Problem(CANH_BAO, "khối trích dẫn có phần không thuộc đích nào: " +
                                       ", ".join(f"{NAME[n.loai]} {n.ky_hieu}" for n in left[:5])))
    if cx.res.versions_created == 0:
        cx.res.problems.append(Problem(CANH_BAO, "lệnh không làm đổi nội dung nào (khối trích dẫn trùng bản hiện tại)"))


def _op_bo_sung(cx: _Ctx) -> None:
    spec = _spec(cx)
    frag = _fragment(cx)
    sau_raw, cha_raw = spec.get("sau"), spec.get("cha")
    if sau_raw:
        sau_path = _parse_path(sau_raw)
        sau_id = _resolve(cx.conn, cx.van_ban_id, sau_path)
        sau_row = _open_row(cx.conn, sau_id)
        cha_id = sau_row["cha_id"]
        if cha_id is None:
            raise CommandError("bổ sung nút gốc (Phần) chưa được hỗ trợ")
        if cha_raw and _resolve(cx.conn, cx.van_ban_id, _parse_path(cha_raw)) != cha_id:
            raise CommandError(f"'sau' ({_path_text(sau_path)}) không nằm trong 'cha' đã ghi")
    elif cha_raw:
        cha_id, sau_row = _resolve(cx.conn, cx.van_ban_id, _parse_path(cha_raw)), None
    else:
        raise CommandError("bo_sung: cần 'sau' hoặc 'cha'")
    first = frag.nodes[0]
    if spec.get("loai") and (spec["loai"], str(spec.get("ky_hieu", first.ky_hieu))) != (first.loai, first.ky_hieu):
        raise CommandError(f"bo_sung: lệnh nói {spec.get('loai')} {spec.get('ky_hieu')} nhưng khối trích dẫn mở đầu bằng "
                           f"{first.loai} {first.ky_hieu}")
    siblings = _open_children(cx.conn, cha_id)
    taken = {(r["loai"], r["ky_hieu"]) for r in siblings}
    for n in frag.nodes:
        if (n.loai, n.ky_hieu) in taken:
            raise CommandError(f"{NAME[n.loai]} {n.ky_hieu} đã có trong {_label(cx.conn, cha_id)}; muốn thay nội dung thì dùng sua_doi")
        if sau_row is not None and n.loai != sau_row["loai"]:
            raise CommandError(f"bổ sung {NAME[n.loai]} {n.ky_hieu} sau {NAME[sau_row['loai']]} {sau_row['ky_hieu']}: khác cấp")
    if sau_row is None:
        pos = _pos_by_key(siblings, first)
    else:
        pos = 1 + next(i for i, r in enumerate(siblings) if r["don_vi_id"] == sau_row["don_vi_id"])
    fixed = [r["thu_tu"] for r in siblings[:pos]] + [None] * len(frag.nodes) + [r["thu_tu"] for r in siblings[pos:]]
    tt = _alloc_thu_tu(fixed)[pos:pos + len(frag.nodes)]
    for n, t in zip(frag.nodes, tt):
        _create_subtree(cx, cha_id, n, t)


def _sort_key(loai: str, ky: str):
    """Khoá thứ tự của ký hiệu: '3' < '3a' < '4'; điểm theo bảng chữ cái VN. None = không so sánh được (vd số La Mã)."""
    import re as _re
    from src.parse.model import VN_LETTERS

    m = _re.fullmatch(r"(\d+)([a-zđ]?)", ky)
    if m and loai != "diem":
        return (int(m.group(1)), VN_LETTERS.find(m.group(2)) + 1 if m.group(2) else 0)
    if loai == "diem" and len(ky) == 1 and ky in VN_LETTERS:
        return (VN_LETTERS.index(ky), 0)
    return None


def _pos_by_key(siblings: list[sqlite3.Row], first: Node) -> int:
    """Vị trí chèn khi lệnh không nói 'vào sau ...': ngay sau nút anh em có ký hiệu lớn nhất mà vẫn nhỏ hơn ký hiệu mới
    (hết chỗ so sánh được thì chèn cuối)."""
    new = _sort_key(first.loai, first.ky_hieu)
    keys = [_sort_key(r["loai"], r["ky_hieu"]) if r["loai"] == first.loai else None for r in siblings]
    if new is None or any(k is None for k in keys):
        return len(siblings)
    smaller = [i for i, k in enumerate(keys) if k < new]
    return smaller[-1] + 1 if smaller else 0


def _op_bai_bo(cx: _Ctx) -> None:
    targets = _spec(cx).get("muc_tieu") or []
    if not targets:
        raise CommandError("bai_bo: thiếu muc_tieu")
    for raw in targets:
        _close_subtree(cx, _resolve(cx.conn, cx.van_ban_id, _parse_path(raw)))


def _subtree_open(conn: sqlite3.Connection, don_vi_id: int) -> list[sqlite3.Row]:
    out = []
    row = _open_row(conn, don_vi_id)
    if row is not None:
        out.append(row)
    for (kid,) in conn.execute("SELECT id FROM don_vi_luat WHERE cha_id = ?", (don_vi_id,)).fetchall():
        out.extend(_subtree_open(conn, kid))
    return out


def _op_thay_cum_tu(cx: _Ctx) -> None:
    cmd = cx.cmd
    kieu = _spec(cx).get("kieu")
    cu, moi = cmd["cum_tu_cu"], cmd["cum_tu_moi"]
    try:
        apply_phrase("x", kieu, cu or "x", moi)                    # chỉ để kiểm tra 'kieu'
    except ValueError as e:
        raise CommandError(f"thay_cum_tu: {e}") from e
    if kieu not in ("chen_dau", "chen_cuoi") and not cu:
        raise CommandError(f"thay_cum_tu: kiểu {kieu} cần cum_tu_cu")
    if kieu in ("chen_sau", "chen_truoc", "chen_dau", "chen_cuoi") and not moi:
        raise CommandError(f"thay_cum_tu: kiểu {kieu} cần cum_tu_moi")
    toan_van_ban = cmd["pham_vi"] == "toan_van_ban"
    targets = _spec(cx).get("muc_tieu") or []
    if not toan_van_ban and not targets:
        raise CommandError("thay_cum_tu: thiếu muc_tieu")
    groups: list[tuple[str, list[sqlite3.Row]]] = []
    if toan_van_ban:
        rows = cx.conn.execute(
            """SELECT d.id AS don_vi_id, d.cha_id, d.loai, p.id AS pb_id, p.ky_hieu, p.thu_tu, p.tieu_de, p.noi_dung, p.hieu_luc_tu
               FROM don_vi_luat d JOIN phien_ban_noi_dung p ON p.don_vi_id = d.id AND p.hieu_luc_den IS NULL
               WHERE d.van_ban_id = ? ORDER BY d.id""", (cx.van_ban_id,)).fetchall()
        groups.append(("toàn văn bản", rows))
    else:
        for raw in targets:
            phan = "toan_bo"
            if isinstance(raw, dict):
                phan, raw = raw.get("phan", "toan_bo"), raw.get("duong_dan")
            path = _parse_path(raw)
            root = _resolve(cx.conn, cx.van_ban_id, path)
            if phan == "tieu_de":                                   # "tại tên điều Điều N": chỉ tiêu đề của chính Điều
                row = _open_row(cx.conn, root)
                if row is None or row["tieu_de"] is None:
                    raise CommandError(f"{_path_text(path)} không có tiêu đề")
                groups.append((_path_text(path) + " (tên điều)", [dict(row) | {"chi_tieu_de": True}]))
            else:
                groups.append((_path_text(path), _subtree_open(cx.conn, root)))
    seen: set[tuple[int, bool]] = set()
    for label, rows in groups:
        hits = 0
        for r in rows:
            title_only = bool(isinstance(r, dict) and r.get("chi_tieu_de"))
            if (r["don_vi_id"], title_only) in seen:
                continue
            title_new, n_t = ((r["tieu_de"], 0)
                              if r["tieu_de"] is None or r["loai"] not in TITLED or kieu in ("chen_dau", "chen_cuoi")
                              else apply_phrase(r["tieu_de"], kieu, cu, moi))
            if title_only:
                body_new, n_b = r["noi_dung"], 0
            elif kieu in ("chen_dau", "chen_cuoi") and r["don_vi_id"] != rows[0]["don_vi_id"]:
                body_new, n_b = r["noi_dung"], 0                  # chèn đầu/cuối chỉ áp cho chính đích, không áp cho nút con
            else:
                body_new, n_b = apply_phrase(r["noi_dung"], kieu, cu, moi)
            if n_t + n_b:
                seen.add((r["don_vi_id"], title_only))
                hits += n_t + n_b
                if (title_new, body_new) != (r["tieu_de"], r["noi_dung"]):
                    _close_version(cx, r)
                    _new_version(cx, r["don_vi_id"], r["ky_hieu"], r["thu_tu"], title_new, body_new, r["loai"])
                else:
                    cx.res.problems.append(Problem(CANH_BAO, f"{_label(cx.conn, r['don_vi_id'])}: cụm từ cũ và mới giống nhau"))
        if hits == 0:
            raise CommandError(f"không tìm thấy cụm từ {cu!r} trong {label}")
        cx.res.replacements += hits


def _op_khong_ap(cx: _Ctx) -> None:
    raise CommandError(f"thao tác {cx.cmd['loai_thao_tac']} chưa được hỗ trợ")


_OPS = {"sua_doi": _op_sua_doi, "bo_sung": _op_bo_sung, "bai_bo": _op_bai_bo, "thay_cum_tu": _op_thay_cum_tu,
        "danh_so_lai": _op_khong_ap, "hoan_hieu_luc": lambda cx: None}   # hoan_hieu_luc đã xử lý ở _reset (ngày hiệu lực của bản gốc)


# ---------------------------------------------------------------------------------------------------------------------
# Rebuild

def _load_commands(conn: sqlite3.Connection, van_ban_id: int, trang_thai: tuple[str, ...]) -> list[sqlite3.Row]:
    ph = ",".join("?" * len(trang_thai))
    return conn.execute(
        f"""SELECT l.*, v.ngay_ban_hanh AS nguon_ngay_ban_hanh FROM lenh_sua_doi l JOIN van_ban v ON v.id = l.van_ban_nguon_id
            WHERE l.van_ban_dich_id = ? AND l.trang_thai_duyet IN ({ph})
            ORDER BY COALESCE(l.hieu_luc_tu, '9999-12-31'), v.ngay_ban_hanh, l.van_ban_nguon_id, l.thu_tu, l.id""",
        (van_ban_id, *trang_thai)).fetchall()


def _base_date(conn: sqlite3.Connection, van_ban_id: int, cmds: list[sqlite3.Row]) -> str:
    row = conn.execute("SELECT ngay_hieu_luc_theo_van_ban FROM van_ban WHERE id = ?", (van_ban_id,)).fetchone()
    if row is None:
        raise ValueError(f"không có van_ban id={van_ban_id}")
    date = row[0]
    for c in cmds:                       # lệnh hoãn/dời hiệu lực đứng sau (theo thứ tự phát lại) thắng
        if c["loai_thao_tac"] == "hoan_hieu_luc" and c["ngay_hieu_luc_moi"]:
            date = c["ngay_hieu_luc_moi"]
    return date


def _reset(conn: sqlite3.Connection, van_ban_id: int, base_date: str) -> None:
    own = "(SELECT id FROM don_vi_luat WHERE van_ban_id = ?)"
    hd.khoi_phuc(conn, van_ban_id)                       # bản gốc trở lại văn bản như luật ban hành, rồi mới phát lại lệnh
    conn.execute(f"DELETE FROM phien_ban_noi_dung WHERE lenh_tao_ra_id IS NOT NULL AND don_vi_id IN {own}", (van_ban_id,))
    conn.execute("DELETE FROM don_vi_luat WHERE van_ban_id = ? AND lenh_tao_ra_id IS NOT NULL", (van_ban_id,))
    conn.execute(f"UPDATE phien_ban_noi_dung SET hieu_luc_tu = ?, hieu_luc_den = NULL, lenh_dong_id = NULL "
                 f"WHERE lenh_tao_ra_id IS NULL AND don_vi_id IN {own}", (base_date, van_ban_id))
    conn.execute("UPDATE van_ban SET ngay_hieu_luc = ? WHERE id = ?", (base_date, van_ban_id))


def clear_derived(conn: sqlite3.Connection, van_ban_id: int) -> None:
    """Xoá mọi phiên bản/nút dẫn xuất, trả văn bản gốc về nguyên trạng. Phải gọi TRƯỚC khi xoá dòng lenh_sua_doi
    (các phiên bản dẫn xuất tham chiếu tới lệnh), rồi rebuild lại. Không commit."""
    base = conn.execute("SELECT ngay_hieu_luc_theo_van_ban FROM van_ban WHERE id = ?", (van_ban_id,)).fetchone()[0]
    _reset(conn, van_ban_id, base)


def rebuild(
    conn: sqlite3.Connection,
    van_ban_id: int,
    *,
    trang_thai: tuple[str, ...] = DEFAULT_TRANG_THAI,
    strict: bool = True,
    commit: bool = True,
    hieu_dinh: tuple[str, ...] = hd.DA_DUYET,
) -> RebuildReport:
    """Dựng lại toàn bộ phiên bản dẫn xuất của văn bản `van_ban_id` từ bản gốc + lệnh có trang_thai_duyet thuộc `trang_thai`.
    Tất định: cùng dữ liệu vào, cùng kết quả. Nguyên tử: lỗi (strict) thì CSDL về đúng như trước khi gọi.
    commit=True: commit khi thành công.
    hieu_dinh: trạng thái của các quy tắc hiệu đính (bảng hieu_dinh) được áp SAU khi phát lại lệnh; mặc định chỉ quy tắc đã duyệt."""
    conn.execute("SAVEPOINT rebuild")
    try:
        cmds = _load_commands(conn, van_ban_id, trang_thai)
        base_date = _base_date(conn, van_ban_id, cmds)
        _reset(conn, van_ban_id, base_date)
        results: list[CommandResult] = []
        for c in cmds:
            res = CommandResult(c["id"], c["vi_tri_nguon"], c["loai_thao_tac"], c["hieu_luc_tu"], c["trang_thai_duyet"])
            conn.execute("SAVEPOINT cmd")
            try:
                if not c["hieu_luc_tu"]:
                    raise CommandError("lệnh chưa có hieu_luc_tu")
                _OPS[c["loai_thao_tac"]](_Ctx(conn, c, res))
            except CommandError as e:
                res.problems.append(Problem(LOI, str(e)))
            except sqlite3.DatabaseError as e:
                res.problems.append(Problem(LOI, f"CSDL từ chối: {e}"))
            if not res.ok:
                conn.execute("ROLLBACK TO cmd")
                res.versions_created = res.versions_closed = res.nodes_created = res.replacements = 0
            conn.execute("RELEASE cmd")
            results.append(res)
        report = RebuildReport(van_ban_id, base_date, results)
        if not report.n_loi or not strict:
            report.hieu_dinh = hd.ap_dung(conn, van_ban_id, hieu_dinh)
        if strict and report.n_loi:
            raise RebuildError(report)
        conn.execute("RELEASE rebuild")
        if commit:
            conn.commit()
        return report
    except BaseException:
        conn.execute("ROLLBACK TO rebuild")
        conn.execute("RELEASE rebuild")
        raise


def preview(conn: sqlite3.Connection, van_ban_id: int, *, trang_thai: tuple[str, ...] = ("cho_duyet", "da_duyet", "da_sua"),
            hieu_dinh: tuple[str, ...] = ("cho_duyet", "da_duyet")):
    """Chạy thử trên BẢN SAO trong bộ nhớ (kể cả lệnh chưa duyệt và, mặc định, đề xuất hiệu đính chưa duyệt); CSDL thật không bị đụng tới.
    Trả về (báo cáo, kết nối tới bản sao để xem kết quả); người gọi đóng kết nối bản sao."""
    from src.store import connect

    mem = connect(":memory:")
    if conn.in_transaction:                      # sqlite3.backup chờ mãi nếu nguồn còn giao dịch ghi dở
        conn.commit()
    conn.backup(mem)
    return rebuild(mem, van_ban_id, trang_thai=trang_thai, strict=False, hieu_dinh=hieu_dinh), mem
