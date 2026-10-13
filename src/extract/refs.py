"""Đọc THAM CHIẾU ĐÍCH trong câu lệnh sửa đổi ("điểm a khoản 1 Điều 5", "các khoản 1, 2 và 3 Điều 195", "tên điều và khoản 1"...)
thành đường dẫn có cấu trúc [(loai, ky_hieu), ...] — cùng dạng dich_json của lenh_sua_doi.

Văn phong pháp luật viết từ nhỏ đến lớn và chỉ ghi Điều một lần ở cuối ("điểm a khoản 1, điểm b khoản 2 Điều 5"),
nên mỗi nhóm lấy ngữ cảnh từ nhóm LỚN HƠN GẦN NHẤT ở bên phải; nhóm cuối cùng không có nhóm lớn hơn thì dùng ngữ cảnh kế thừa
(vd câu con "Sửa đổi, bổ sung khoản 2 như sau" dưới câu cha "Sửa đổi, bổ sung Điều 40 như sau").
Không đoán: thiếu ngữ cảnh thì trả về None để người/LLM xử lý.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

PathT = list[tuple[str, str]]
RANK = {"chuong": 0, "muc": 1, "dieu": 2, "khoan": 3, "ten": 3, "diem": 4}
_KEY = {"dieu": r"\d+[a-zđ]?", "khoan": r"\d+[a-zđ]?", "diem": r"[a-zđ]", "chuong": r"[IVXLC]+", "muc": r"\d+|[IVXLC]+"}
_SEP = r"(?:\s*,\s*và\s+|\s*,\s*|\s+và\s+)"
_WORD = {"dieu": "điều", "khoan": "khoản", "diem": "điểm", "chuong": "chương", "muc": "mục"}


def _build() -> re.Pattern:
    alts = ["(?P<ten>(?i:tên điều))(?!\\w)"]
    for loai, word in _WORD.items():
        k = _KEY[loai]
        alts.append(rf"(?:(?i:các\s+)?(?i:{word})\s+(?P<{loai}>{k}(?:{_SEP}(?:{k}))*)(?!\w))")
    return re.compile("|".join(alts))


RE_GROUP = _build()
_RE_SPLIT = re.compile(_SEP)
_RE_JOIN = re.compile(r"^\s*(?:,\s*và|,|và)?\s*$")


@dataclass
class RefGroup:
    level: str                  # dieu | khoan | diem | chuong | muc | ten
    keys: list[str]             # 'ten' không có khoá
    start: int
    end: int


@dataclass
class Target:
    path: PathT
    phan: str = "toan_bo"       # 'tieu_de' cho "tên điều"
    group: int = -1             # chỉ số nhóm nguồn (để biết đích thuộc mệnh đề nào)


def find_groups(text: str) -> list[RefGroup]:
    groups = []
    for m in RE_GROUP.finditer(text):
        level = m.lastgroup
        if level == "ten":
            groups.append(RefGroup("ten", [], m.start(), m.end()))
        else:
            keys = [k for k in _RE_SPLIT.split(m.group(level).strip()) if k]
            groups.append(RefGroup(level, keys, m.start(), m.end()))
    return groups


def resolve_targets(groups: list[RefGroup], text: str, inherited: PathT | None = None) -> tuple[list[Target], bool]:
    """(các đích, đủ_ngữ_cảnh). Nhóm nào làm ngữ cảnh cho nhóm nhỏ hơn thì không tự thành đích."""
    n = len(groups)
    ctx_idx: list[int | None] = [None] * n
    for i, g in enumerate(groups):
        if g.level in ("dieu", "chuong"):
            continue
        for j in range(i + 1, n):
            if RANK[groups[j].level] < RANK[g.level]:
                ctx_idx[i] = j
                break
    used = {j for j in ctx_idx if j is not None}
    complete = True

    memo: dict[int, list[PathT] | None] = {}

    def paths_of(j: int) -> list[PathT] | None:
        if j in memo:
            return memo[j]
        g = groups[j]
        if g.level in ("dieu", "chuong"):
            base: list[PathT] | None = [[]]
        elif ctx_idx[j] is not None:
            base = paths_of(ctx_idx[j])
        else:
            base = [list(inherited)] if inherited else None
        out = None if base is None else [b + [(g.level, k)] for b in base for k in g.keys]
        memo[j] = out
        return out

    targets: list[Target] = []
    # "tên điều" đứng liền trước danh sách Điều ("tại tên điều Điều 220 và Điều 221"): tiêu đề của TỪNG Điều trong danh sách
    ten_run: dict[int, str] = {}
    for i, g in enumerate(groups):
        if g.level == "ten" and i + 1 < n and groups[i + 1].level == "dieu" and text[g.end:groups[i + 1].start].strip() == "":
            j = i + 1
            ten_run[j] = "tieu_de"
            while j + 1 < n and groups[j + 1].level == "dieu" and _RE_JOIN.match(text[groups[j].end:groups[j + 1].start]):
                j += 1
                ten_run[j] = "tieu_de"
    for j, phan in ten_run.items():
        for p in paths_of(j) or []:
            targets.append(Target(p, phan, j))
    ten_skip = {i - 1 for i in ten_run}
    for i, g in enumerate(groups):
        if i in ten_skip or i in ten_run:
            continue
        if g.level == "ten":
            j = next((jj for jj in range(i + 1, n) if groups[jj].level == "dieu"), None)
            if j is not None:
                used.add(j)
                for p in paths_of(j) or []:
                    targets.append(Target(p, "tieu_de", i))
            elif inherited and inherited[-1][0] == "dieu":
                targets.append(Target(list(inherited), "tieu_de", i))
            else:
                complete = False
            continue
        if i in used:
            continue
        ps = paths_of(i)
        if ps is None:
            complete = False
            continue
        for p in ps:
            targets.append(Target(p, "toan_bo", i))
    return targets, complete


def context_path(groups: list[RefGroup]) -> PathT | None:
    """Ngữ cảnh kế thừa cho câu con: Điều duy nhất trong câu cha (Điều cuối cùng nếu có nhiều nhóm)."""
    for g in reversed(groups):
        if g.level == "dieu":
            return [("dieu", g.keys[0])] if len(g.keys) == 1 else None
    return None


def path_to_json(path: PathT) -> list[dict]:
    return [{"loai": l, "ky_hieu": k} for l, k in path]
