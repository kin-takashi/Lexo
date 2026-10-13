"""Bộ trích lệnh sửa đổi bằng REGEX/văn phạm (baseline, không LLM): amending.json -> danh sách lệnh có cấu trúc.

Hai họ câu lệnh:
  1. Lệnh có KHỐI TRÍCH DẪN ("Sửa đổi, bổ sung khoản 2 Điều 5 như sau: “...”", "Bổ sung Điều 256a vào sau Điều 256 như sau: “...”",
     "Bãi bỏ chương XII"): nội dung mới do code gắn từ khối trích dẫn, không ai chép lại.
  2. Lệnh thay/bổ sung/bỏ CỤM TỪ nằm ngay trong câu ("Thay thế cụm từ “A” bằng cụm từ “B” tại điểm b khoản 2 Điều 29; ..."):
     tách theo dấu ';', ', cụm từ', 'và cụm từ' thành từng mệnh đề, mệnh đề không ghi động từ thì kế thừa mệnh đề trước.

Nguyên tắc: hoặc hiểu TRỌN một mục (mọi cụm trong “ ” đều được dùng đúng một lần, mọi tham chiếu đều có ngữ cảnh) hoặc đưa mục đó vào
danh sách `unparsed` kèm lý do — để người duyệt hoặc LLM xử lý; không đoán. Độ phủ (số mục hiểu được / tổng số mục) được báo cáo.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from src.extract.refs import PathT, RefGroup, Target, context_path, find_groups, path_to_json, resolve_targets
from src.parse.amending import AmendingLaw, Item
from src.parse.fragment import locate, parse_fragment
from src.parse.model import VN_LETTERS

NAME = {"chuong": "Chương", "muc": "Mục", "dieu": "Điều", "khoan": "khoản", "diem": "điểm"}
_VERB = r"(?:thay thế|thay|bổ sung|bỏ)"
_WORD = r"(?:cụm từ|từ|dấu)"
_RE_Q = re.compile(r"“([^”]*)”")
_RE_LEAD = re.compile(r"^(Sửa đổi, bổ sung|Sửa đổi|Bổ sung|Bãi bỏ|Thay thế|Bỏ)\b")
_RE_QUOTE_HEAD = re.compile(r"^(Sửa đổi, bổ sung|Sửa đổi|Thay thế|Bổ sung)\s+(?P<body>.+?)\s+như sau\s*:?$")
_SPLIT_COMMA = re.compile(rf",\s+(?=(?:{_VERB}\s+)?{_WORD}\s+⟦)", re.I)
_SPLIT_VA = re.compile(rf"\s+và\s+(?=(?:{_VERB}\s+)?{_WORD}\s+⟦)", re.I)
_SPLIT_ANCHOR = re.compile(rf"(?:,\s*|\s+và\s+)?(?=(?:trước|sau)\s+{_WORD}\s+⟦)", re.I)
_LEFTOVER = re.compile(r"⟪\d+⟫|\btại\b|\bvà\b|[,.;]", re.I)


def path_text(path: PathT) -> str:
    return " ".join(f"{NAME.get(l, l)} {k}" for l, k in reversed(path))


@dataclass
class ExtractedCommand:
    loai_thao_tac: str
    item_id: str
    vi_tri_nguon: str
    tham_chieu_dich: str
    dich: dict | None
    noi_dung_moi: str | None = None
    cum_tu_cu: str | None = None
    cum_tu_moi: str | None = None
    pham_vi: str | None = None
    quote_ids: list[str] = field(default_factory=list)
    nguon_dong_tu: int = 0
    nguon_dong_den: int = 0

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class Unparsed:
    item_id: str
    vi_tri_nguon: str
    text: str
    reason: str
    dong: int = 0

    def to_dict(self) -> dict:
        return dict(self.__dict__)


@dataclass
class ExtractionResult:
    so_hieu_nguon: str | None
    commands: list[ExtractedCommand] = field(default_factory=list)
    unparsed: list[Unparsed] = field(default_factory=list)
    containers: list[str] = field(default_factory=list)          # mục cha chỉ chứa mục con, không tự sinh lệnh
    n_leaf: int = 0                                              # số mục lá trong phạm vi

    @property
    def n_parsed_leaf(self) -> int:
        return self.n_leaf - len(self.unparsed)

    def coverage(self) -> float:
        return self.n_parsed_leaf / self.n_leaf if self.n_leaf else 1.0

    def to_dict(self) -> dict:
        return {"so_hieu_nguon": self.so_hieu_nguon, "n_leaf": self.n_leaf, "n_parsed_leaf": self.n_parsed_leaf,
                "coverage": round(self.coverage(), 4), "containers": self.containers,
                "commands": [c.to_dict() for c in self.commands], "unparsed": [u.to_dict() for u in self.unparsed]}


class _Fail(Exception):
    pass


def _one_line(text: str) -> str:
    return " ".join(text.split())


# ---------------------------------------------------------------------------------------------------------------------
# Họ 1: lệnh có khối trích dẫn / bãi bỏ

def _targets(body: str, inherited: PathT | None) -> list[Target]:
    groups = find_groups(body)
    if not groups:
        raise _Fail(f"không thấy tham chiếu Điều/khoản/điểm trong {body[:60]!r}")
    targets, complete = resolve_targets(groups, body, inherited)
    if not complete or not targets:
        raise _Fail(f"thiếu ngữ cảnh (Điều) cho tham chiếu {body[:60]!r}")
    return targets


def _quote_text(law: AmendingLaw, item: Item) -> str:
    return "\n".join(law.quote(q).text for q in item.quote_ids)


def _from_quote(law: AmendingLaw, item: Item, text: str, ctx: PathT | None) -> list[ExtractedCommand]:
    m = _RE_QUOTE_HEAD.match(text)
    if not m:
        raise _Fail("câu lệnh có khối trích dẫn nhưng không theo mẫu '<Sửa đổi/Bổ sung> ... như sau:'")
    verb, body = m.group(1), m.group("body")
    quote = _quote_text(law, item)
    frag = parse_fragment(quote)
    if not frag.nodes:
        raise _Fail("khối trích dẫn không đọc được thành Điều/khoản/điểm")
    base = dict(item_id=item.id, vi_tri_nguon=item.vi_tri_nguon, tham_chieu_dich=body, noi_dung_moi=quote,
                quote_ids=list(item.quote_ids), nguon_dong_tu=item.line_start, nguon_dong_den=item.line_end)
    if verb in ("Sửa đổi, bổ sung", "Sửa đổi", "Thay thế"):
        targets = _targets(body, ctx)
        for t in targets:
            if locate(frag.nodes, t.path) is None:
                raise _Fail(f"khối trích dẫn không chứa {path_text(t.path)}")
        left = {id(n) for n in frag.walk()}
        muc_tieu = [{"duong_dan": path_to_json(t.path), "phan": t.phan} for t in targets]
        return [ExtractedCommand("sua_doi", dich={"muc_tieu": muc_tieu}, **base)]
    # Bổ sung: "<mới> vào sau <X>" / "<mới> vào <cha>" / "<mới>" (cha = ngữ cảnh)
    sau_txt = cha_txt = None
    if " vào sau " in body:
        new_txt, sau_txt = body.split(" vào sau ", 1)
    elif " vào " in body:
        new_txt, cha_txt = body.split(" vào ", 1)
    else:
        new_txt = body
    ng = find_groups(new_txt)
    if len(ng) != 1 or ng[0].level == "ten":
        raise _Fail(f"không xác định được nút mới trong {body[:60]!r}")
    level, keys = ng[0].level, ng[0].keys
    for k in keys:
        if not any(n.loai == level and n.ky_hieu == k for n in frag.nodes):
            raise _Fail(f"khối trích dẫn không mở đầu bằng {NAME[level]} {k}")
    sau = cha = None
    if sau_txt is not None:
        ts = _targets(sau_txt, ctx)
        if len(ts) != 1:
            raise _Fail(f"'vào sau' phải chỉ một nút, thấy {len(ts)}")
        sau = ts[0].path
    elif cha_txt is not None:
        ts = _targets(cha_txt, ctx)
        if len(ts) != 1:
            raise _Fail(f"'vào' phải chỉ một nút cha, thấy {len(ts)}")
        cha = ts[0].path
    elif level == "dieu" and re.fullmatch(r"\d+[a-zđ]", keys[0]):        # "Bổ sung Điều 217a như sau": vị trí là ngay sau nút liền trước
        prev = keys[0][:-1] if keys[0][-1] == "a" else keys[0][:-1] + VN_LETTERS[VN_LETTERS.index(keys[0][-1]) - 1]
        sau = [("dieu", prev)]
    elif ctx:
        cha = list(ctx)
    else:
        raise _Fail("bổ sung nhưng không biết vào đâu (thiếu 'vào ...' và thiếu ngữ cảnh)")
    dich = {"cha": path_to_json(cha) if cha else None, "sau": path_to_json(sau) if sau else None, "loai": level, "ky_hieu": keys[0]}
    return [ExtractedCommand("bo_sung", dich=dich, **base)]


def _bai_bo(item: Item, body: str, ctx: PathT | None, pos: tuple[int, int] | None = None) -> ExtractedCommand:
    targets = _targets(body, ctx)
    return ExtractedCommand("bai_bo", item_id=item.id, vi_tri_nguon=item.vi_tri_nguon, tham_chieu_dich=body,
                            dich={"muc_tieu": [path_to_json(t.path) for t in targets]}, nguon_dong_tu=item.line_start,
                            nguon_dong_den=item.line_end)


# ---------------------------------------------------------------------------------------------------------------------
# Họ 2: thay / bổ sung / bỏ cụm từ

def _anchored(verb: str, a: str, b: str | None, pos: str, c: str) -> tuple[str, str, str]:
    """Thay hoặc bỏ `a` đang đứng liền trước/sau cụm neo `c`: trả về (kieu, cu, moi) dạng thay cụm."""
    punct = a[:1] in ",;:."
    if pos == "trước":
        cu = f"{a} {c}"
        moi = (f" {b} {c}" if punct else f"{b} {c}") if verb == "thay thế" else (f" {c}" if punct else c)
    else:
        cu = f"{c}{a}" if punct else f"{c} {a}"
        moi = f"{c} {b}" if verb == "thay thế" else c
    return "thay", cu, moi


def _from_phrases(item: Item, text: str, ctx: PathT | None, ctx_verb: str | None) -> list[ExtractedCommand]:
    phrases: list[str] = []

    def tok(m):
        phrases.append(m.group(1))
        return f"⟦{len(phrases) - 1}⟧"

    sk = _RE_Q.sub(tok, text)
    if not phrases and not re.match(r"^(?:bỏ|bãi bỏ)\s+(?:các\s+)?(?:điều|khoản|điểm|chương|mục)\b", sk, re.I):
        raise _Fail("không có cụm từ trong “ ” và không phải lệnh bãi bỏ")
    groups = find_groups(sk)
    targets, complete = resolve_targets(groups, sk, ctx)
    # thay mỗi nhóm tham chiếu bằng ⟪i⟫ (từ cuối lên đầu để không lệch vị trí)
    parts, last = [], len(sk)
    for i in range(len(groups) - 1, -1, -1):
        parts.append(sk[groups[i].end:last])
        parts.append(f"⟪{i}⟫")
        last = groups[i].start
    parts.append(sk[:last])
    ref_sk = "".join(reversed(parts))
    by_group: dict[int, list[Target]] = {}
    for t in targets:
        by_group.setdefault(t.group, []).append(t)

    segments = [s.strip() for s in ref_sk.split(";") if s.strip(" .")]
    clauses: list[str] = []
    for seg in segments:
        for a in _SPLIT_COMMA.split(seg):
            clauses.extend(x for x in _SPLIT_VA.split(a) if x.strip(" ."))

    def clause_targets(s: str) -> list[Target]:
        out = []
        for gi in re.findall(r"⟪(\d+)⟫", s):
            out.extend(by_group.get(int(gi), []))
        return out

    used_phrases: set[int] = set()
    verb = ctx_verb
    ops: list[tuple[str, str, str | None, str | None, list[Target] | None, str | None, str]] = []
    # (verb, kind, a, b, targets|None, pos, extra) — targets None = mượn của mệnh đề sau
    for cl in clauses:
        cl = cl.strip(" .")
        m = re.match(rf"^(?P<v>{_VERB})\s+(?P<rest>.+)$", cl, re.I)
        if m:
            verb, body = m.group("v").lower(), m.group("rest")
            if verb == "thay":                                          # "Thay cụm từ …" = "Thay thế cụm từ …"
                verb = "thay thế"
        else:
            body = cl
        if verb is None:
            raise _Fail(f"mệnh đề không có động từ: {cl[:50]!r}")
        if re.match(r"^⟪\d+⟫", body):                                   # "Bỏ điểm đ khoản 2, ... Điều 172"
            if verb != "bỏ":
                raise _Fail(f"tham chiếu không kèm cụm từ sau động từ '{verb}': {cl[:50]!r}")
            ops.append((verb, "bai_bo", None, None, clause_targets(body) or None, None, body))
            continue
        if verb == "thay thế":
            mm = re.match(rf"^{_WORD}\s+⟦(\d+)⟧\s+bằng\s+{_WORD}\s+⟦(\d+)⟧(?P<rest>.*)$", body, re.I)
            if not mm:
                raise _Fail(f"mệnh đề thay thế không theo mẫu: {cl[:60]!r}")
            a, b, rest = int(mm.group(1)), int(mm.group(2)), mm.group("rest")
            used_phrases.update((a, b))
            pieces = _anchor_pieces(rest, used_phrases)
            if pieces is None:
                tg = clause_targets(rest)
                ops.append((verb, "thay", phrases[a], phrases[b], tg or None, None, rest))
            else:
                for pos, c, r in pieces:
                    k, cu, moi = _anchored(verb, phrases[a], phrases[b], pos, phrases[c])
                    ops.append((verb, k, cu, moi, clause_targets(r) or None, pos, r))
            continue
        if verb == "bổ sung":
            mm = re.match(rf"^{_WORD}\s+⟦(\d+)⟧\s+vào\s+(?P<pos>đầu|cuối|sau|trước)(?P<rest>.*)$", body, re.I)
            if not mm:
                raise _Fail(f"mệnh đề bổ sung không theo mẫu: {cl[:60]!r}")
            a, pos, rest = int(mm.group(1)), mm.group("pos").lower(), mm.group("rest")
            used_phrases.add(a)
            if pos in ("đầu", "cuối"):
                ops.append((verb, "chen_dau" if pos == "đầu" else "chen_cuoi", None, phrases[a],
                            clause_targets(rest) or None, pos, rest))
                continue
            m1 = re.match(rf"^\s*{_WORD}\s+⟦(\d+)⟧(?P<r>.*)$", rest, re.I)
            if not m1:
                raise _Fail(f"thiếu cụm neo sau 'vào {pos}': {cl[:60]!r}")
            first_c, r1 = int(m1.group(1)), m1.group("r")
            pieces = _anchor_pieces(r1, used_phrases)
            kind = "chen_sau" if pos == "sau" else "chen_truoc"
            used_phrases.add(first_c)
            if pieces is None:
                ops.append((verb, kind, phrases[first_c], phrases[a], clause_targets(r1) or None, pos, r1))
            else:
                head, tail = _split_head(r1)
                ops.append((verb, kind, phrases[first_c], phrases[a], clause_targets(head) or None, pos, head))
                for p2, c2, r2 in pieces:
                    ops.append((verb, "chen_sau" if p2 == "sau" else "chen_truoc", phrases[c2], phrases[a],
                                clause_targets(r2) or None, p2, r2))
            continue
        # verb == 'bỏ'
        mm = re.match(rf"^{_WORD}\s+⟦(\d+)⟧(?P<rest>.*)$", body, re.I)
        if not mm:
            raise _Fail(f"mệnh đề bỏ không theo mẫu: {cl[:60]!r}")
        a, rest = int(mm.group(1)), mm.group("rest")
        used_phrases.add(a)
        pieces = _anchor_pieces(rest, used_phrases)
        if pieces is None:
            ops.append((verb, "bo", phrases[a], None, clause_targets(rest) or None, None, rest))
        else:
            for pos, c, r in pieces:
                k, cu, moi = _anchored(verb, phrases[a], None, pos, phrases[c])
                ops.append((verb, k, cu, moi, clause_targets(r) or None, pos, r))

    if used_phrases != set(range(len(phrases))):
        raise _Fail(f"không dùng hết các cụm trong “ ”: còn {sorted(set(range(len(phrases))) - used_phrases)}")

    # mệnh đề không ghi nơi áp dụng thì mượn nơi áp dụng của mệnh đề kế tiếp có ghi
    resolved: list[list[Target]] = []
    nxt: list[Target] | None = None
    for op in reversed(ops):
        tg = op[4] if op[4] else nxt
        if not tg:
            raise _Fail("có mệnh đề không xác định được nơi áp dụng")
        resolved.append(tg)
        nxt = tg
    resolved.reverse()
    if not complete:
        raise _Fail("có tham chiếu thiếu ngữ cảnh (Điều)")

    out: list[ExtractedCommand] = []
    for (v, kind, a, b, _tg, _pos, _extra), tg in zip(ops, resolved):
        base = dict(item_id=item.id, vi_tri_nguon=item.vi_tri_nguon, nguon_dong_tu=item.line_start, nguon_dong_den=item.line_end,
                    tham_chieu_dich="; ".join(path_text(t.path) + (" (tên điều)" if t.phan == "tieu_de" else "") for t in tg))
        if kind == "bai_bo":
            out.append(ExtractedCommand("bai_bo", dich={"muc_tieu": [path_to_json(t.path) for t in tg]}, **base))
            continue
        muc_tieu = [{"duong_dan": path_to_json(t.path), "phan": t.phan} for t in tg]
        if kind in ("thay", "bo", "chen_sau", "chen_truoc"):
            cu, moi = (a, b)
        else:
            cu, moi = None, b
        out.append(ExtractedCommand("thay_cum_tu", dich={"muc_tieu": muc_tieu, "kieu": kind}, cum_tu_cu=cu, cum_tu_moi=moi,
                                    pham_vi="don_vi", **base))
    return out


def _anchor_pieces(rest: str, used: set[int]) -> list[tuple[str, int, str]] | None:
    """Tách "... trước cụm từ ⟦c⟧ tại R1, trước cụm từ ⟦d⟧ tại R2" thành [(pos, c, phần tham chiếu R)]; None nếu không có neo."""
    parts = [p for p in _SPLIT_ANCHOR.split(rest) if p.strip(" ,")]
    pieces = []
    for p in parts:
        mm = re.match(rf"^\s*(trước|sau)\s+{_WORD}\s+⟦(\d+)⟧(?P<r>.*)$", p, re.I)
        if mm:
            c = int(mm.group(2))
            used.add(c)
            pieces.append((mm.group(1).lower(), c, mm.group("r")))
        elif pieces:
            return _fail_piece(p)
        else:
            return None if len(parts) <= 1 else _fail_piece(p)
    return pieces or None


def _fail_piece(p: str):
    raise _Fail(f"không hiểu đoạn: {p[:50]!r}")


def _split_head(r1: str) -> tuple[str, str]:
    m = _SPLIT_ANCHOR.search(r1)
    return (r1[: m.start()], r1[m.start():]) if m else (r1, "")


# ---------------------------------------------------------------------------------------------------------------------
# Duyệt cây mục lệnh

def extract_commands(law: AmendingLaw) -> ExtractionResult:
    res = ExtractionResult(so_hieu_nguon=law.meta.so_hieu)

    def leaf(item: Item, ctx: PathT | None, ctx_verb: str | None) -> None:
        res.n_leaf += 1
        text = _one_line(item.text)
        try:
            if item.quote_ids:
                cmds = _from_quote(law, item, text, ctx)
            else:
                m = _RE_LEAD.match(text)
                if m and m.group(1) == "Bãi bỏ":
                    cmds = [_bai_bo(item, text[m.end():].strip(" .;"), ctx)]
                else:
                    cmds = _from_phrases(item, text, ctx, ctx_verb)
        except _Fail as e:
            res.unparsed.append(Unparsed(item.id, item.vi_tri_nguon, text, str(e), item.line_start))
            return
        res.commands.extend(cmds)

    def walk(item: Item, ctx: PathT | None, ctx_verb: str | None) -> None:
        if item.pham_vi != "trong":
            return
        if not item.children:
            leaf(item, ctx, ctx_verb)
            return
        res.containers.append(item.id)
        text = _one_line(item.text)
        if item.quote_ids:
            res.n_leaf += 1
            res.unparsed.append(Unparsed(item.id, item.vi_tri_nguon, text, "mục cha vừa có khối trích dẫn vừa có mục con", item.line_start))
        clean = _RE_Q.sub(" ", text)
        new_ctx = context_path(find_groups(clean)) or ctx
        m = re.match(rf"^({_VERB}|sửa đổi)\b", clean, re.I)
        verb = m.group(1).lower() if m else None
        verb = "thay thế" if verb == "thay" else (verb if verb in ("thay thế", "bổ sung", "bỏ") else None)
        for ch in item.children:
            walk(ch, new_ctx, verb or (ctx_verb if ctx_verb else None))

    for d in law.dieu_sua_doi:
        for it in d.items:
            walk(it, None, None)
    return res
