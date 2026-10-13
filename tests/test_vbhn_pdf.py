"""Trích văn bản hợp nhất từ PDF kiểu Công báo (src/ingest/vbhn_pdf.py) trên một PDF giả lập sinh ngay trong test.
Cần pdfplumber + reportlab + một phông có tiếng Việt (DejaVu); thiếu thì bỏ qua."""
import json
from pathlib import Path

import pytest

from src.ingest.vbhn_pdf import _END, _FRONT, _TRAILER, VbhnText, extract_vbhn

FONTS = ["/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf", "/usr/share/fonts/dejavu/DejaVuSerif.ttf",
         "C:/Windows/Fonts/times.ttf", "/Library/Fonts/Times New Roman.ttf", "/System/Library/Fonts/Supplemental/Times New Roman.ttf"]


def test_regex_nhan_dien_dong_dau_cuoi():
    assert _END.search("VĂN PHÒNG QUỐC HỘI XÁC THỰC VĂN BẢN HỢP NHẤT") and _END.search("XÁC THỰC VĂN BẢN HỢP NHẤT")
    assert not _END.search("Văn bản này xác thực văn bản hợp nhất của Chính phủ.")
    assert _TRAILER.match("(Xem tiếp Công báo số 1273 + 1274)") and not _TRAILER.match("Xem tiếp Công báo số 1273")
    for t in ("VĂN BẢN PHÁP LUẬT KHÁC", "Bộ luật Hình sự", "Văn bản hợp nhất số 135/VBHN-VPQH", "(Tiếp theo Công báo số 1271 + 1272)"):
        assert _FRONT.match(t), t
    assert not _FRONT.match("Điều 1. Nhiệm vụ của Bộ luật Hình sự")


def test_vbhn_text_to_dict_from_dict_khu_hoi():
    v = VbhnText(["a", "b"], {1: [3, 4]}, {3: "ba", 4: "bốn"}, ["tiêu đề"], [(1, 1), (1, 2)], [{"name": "x.pdf", "sha256": "0"}])
    d = json.loads(json.dumps(v.to_dict(), ensure_ascii=False))
    w = VbhnText.from_dict(d)
    assert (w.lines, w.marks, w.footnotes, w.preamble, w.pages, w.sources) == (v.lines, v.marks, v.footnotes, v.preamble, v.pages, v.sources)


def tao_pdf(path: Path) -> list[str]:
    pytest.importorskip("pdfplumber")
    pytest.importorskip("reportlab")
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen import canvas

    font = next((f for f in FONTS if Path(f).exists()), None)
    if font is None:
        pytest.skip("không có phông tiếng Việt để sinh PDF thử")
    pdfmetrics.registerFont(TTFont("VN", font))
    W, H, LE, THUT = 595, 842, 72, 20
    # (văn bản, thụt, số chú thích gắn ở cuối dòng đầu của đoạn); đoạn dài 2 dòng: dòng đầu thụt, dòng sau đúng lề
    paras: list[tuple[str, str, int | None]] = [
        ("Phần thứ nhất", "gữa", None), ("NHỮNG QUY ĐỊNH CHUNG", "giữa", None), ("Chương I", "giữa", None), ("ĐIỀU KHOẢN CƠ BẢN", "giữa", None),
        ("Điều 1. Nhiệm vụ của Bộ luật", "thụt", 1), ("Bộ luật này có nhiệm vụ bảo vệ chủ quyền, an ninh quốc gia, chế độ xã hội chủ nghĩa", "thụt", None),
        ("Điều 2. Cơ sở của trách nhiệm hình sự", "thụt", None),
    ]
    paras += [(f"{i}. Khoản số {i} có nội dung thử nghiệm đủ dài để phải xuống dòng khi in ra trang giấy khổ A4 của Công báo", "thụt", None)
              for i in range(1, 31)]
    paras += [("Điều 3. Điều khoản thi hành", "thụt", None), ("Bộ luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2018.", "thụt", 2)]
    c = canvas.Canvas(str(path), pagesize=(W, H))
    pages: list[list[tuple[str, float, float, int]]] = [[]]
    y = H - 100
    foot: dict[int, str] = {1: "Điều này được sửa đổi theo Luật số 12/2017/QH14.", 2: "Điều này có hiệu lực theo nghị quyết riêng."}
    nums_on_page: list[list[int]] = [[]]
    for text, kieu, note in paras:
        words, lines, cur = text.split(), [], ""
        for w in words:                                                    # ngắt dòng ~ 62 ký tự
            if len(cur) + len(w) + 1 > 62 and cur:
                lines.append(cur)
                cur = w
            else:
                cur = (cur + " " + w).strip()
        lines.append(cur)
        for k, ln in enumerate(lines):
            if y < 140:
                pages.append([])
                nums_on_page.append([])
                y = H - 100
            x = 230 if kieu == "giữa" else (LE + THUT if k == 0 else LE)
            pages[-1].append((ln, x, y, note if (note and k == len(lines) - 1) else 0))
            if note and k == len(lines) - 1:
                nums_on_page[-1].append(note)
            y -= 20
    # khối xác thực + chữ ký (bị bỏ) + chú thích 2 nằm SAU khối xác thực
    if y < 200:
        pages.append([])
        nums_on_page.append([])
        y = H - 100
    pages[-1].append(("VĂN PHÒNG QUỐC HỘI XÁC THỰC VĂN BẢN HỢP NHẤT", LE, y - 10, 0))
    pages[-1].append(("Nguyễn Văn Thử", LE + 200, y - 40, 0))
    for p, lines in enumerate(pages):
        c.setFont("VN", 10)
        c.drawString(LE, H - 45, f"CÔNG BÁO/Số 1 + 2/Ngày 01-01-2026   {p + 1}")                  # dòng đầu trang (cao hơn mọi dòng thân)
        for text, x, yy, note in lines:
            c.setFont("VN", 14)
            c.drawString(x, yy, text)
            if note:
                c.setFont("VN", 8)
                c.drawString(x + c.stringWidth(text, "VN", 14), yy + 5, str(note))
        fy = 110
        for n in (nums_on_page[p] + ([2] if p == len(pages) - 1 and 2 not in nums_on_page[p] else [])):
            c.setFont("VN", 8)
            c.drawString(LE, fy + 4, str(n))
            c.setFont("VN", 12)
            c.drawString(LE + 8, fy, foot[n])
            fy -= 16
        c.showPage()
    c.save()
    return [t for t, _, _ in paras]


def test_extract_vbhn_pdf_gia_lap(tmp_path):
    pdf = tmp_path / "vbhn.pdf"
    tao_pdf(pdf)
    v = extract_vbhn([pdf])
    assert v.lines[0] == "Phần thứ nhất" and v.lines[1:4] == ["NHỮNG QUY ĐỊNH CHUNG", "Chương I", "ĐIỀU KHOẢN CƠ BẢN"]
    assert v.lines[4] == "Điều 1. Nhiệm vụ của Bộ luật"
    assert v.lines[5] == "Bộ luật này có nhiệm vụ bảo vệ chủ quyền, an ninh quốc gia, chế độ xã hội chủ nghĩa"      # hai dòng PDF nối thành một đoạn
    assert v.lines[6] == "Điều 2. Cơ sở của trách nhiệm hình sự"
    assert v.lines[7].startswith("1. Khoản số 1 có nội dung") and v.lines[7].endswith("Công báo")
    assert v.lines[-2] == "Điều 3. Điều khoản thi hành" and v.lines[-1] == "Bộ luật này có hiệu lực thi hành từ ngày 01 tháng 01 năm 2018."
    assert not any("XÁC THỰC" in x or "Nguyễn Văn Thử" in x or "CÔNG BÁO" in x for x in v.lines)               # đầu trang, khối xác thực, chữ ký đều bị bỏ
    assert all("⟦" not in x for x in v.lines) and len(v.lines) == 7 + 30 + 2
    assert v.marks == {4: [1], len(v.lines) - 1: [2]}                                                          # số chú thích gắn đúng đoạn, đã gỡ khỏi chữ
    assert v.footnotes == {1: "Điều này được sửa đổi theo Luật số 12/2017/QH14.", 2: "Điều này có hiệu lực theo nghị quyết riêng."}
    assert v.sources[0]["name"] == "vbhn.pdf" and len(v.sources[0]["sha256"]) == 64 and len(v.pages) == len(v.lines)
    # đi tiếp vào bộ phân tích cây như luồng thật
    from src.parse.base_law import parse_body
    from src.validate.vbhn import items_from_nodes
    items, repealed = items_from_nodes(parse_body(v.lines)[0])
    assert repealed == [] and {"dieu 1", "dieu 2", "dieu 2/khoan 30", "dieu 3"} <= set(items)
