# Ô thêm cho notebook lexo_do_ban_an: kết hợp C0 và L trên dev (HOP, LOC, LOC0) từ C0.jsonl, L.jsonl đã đo.
# Không gọi Ollama, không cần GPU. Chạy sau ô cấu hình, ô hàm chung và ô 1 (gói đo, định nghĩa LEXO và DU_LIEU).
#   HOP  = C0 ∪ L
#   LOC  = C0 ∩ L (C0 làm nền, L lọc); giao rỗng thì giữ L
#   LOC0 = C0 ∩ L; giao rỗng thì giữ nguyên C0
import json, sys, zipfile
from pathlib import Path

WORK, INPUT = Path("/kaggle/working"), Path("/kaggle/input")
sys.path.insert(0, str(LEXO / "scripts"))
import do_ban_an as db                                                   # tong_hop, dong_bang, so_cap, doc_jsonl của gói
from src.ban_an import chon_dieu as cd

DEV = {x["id"] for x in DU_LIEU["mau"] if x["tap"] == "dev"}


def du_dev(thu_muc):
    return all(DEV <= {r["id"] for r in db.doc_jsonl(thu_muc / f"{c}.jsonl")} for c in ("C0", "L"))


def tim_ket_qua():
    """Thư mục có C0.jsonl và L.jsonl đủ mọi vụ dev: trong /kaggle/working (phiên vừa đo), trong Input,
    hoặc giải nén từ ket_qua_dev_*.zip (Output của lần đo trước, gắn vào làm Input)."""
    for goc in (WORK, INPUT):
        for p in sorted(goc.rglob("L.jsonl")):
            if du_dev(p.parent):
                return p.parent
    for z in sorted(INPUT.rglob("ket_qua_dev_*.zip")) + sorted(WORK.glob("ket_qua_dev_*.zip")):
        ra = WORK / "giai_nen" / z.stem
        zipfile.ZipFile(z).extractall(ra)
        for p in sorted(ra.rglob("L.jsonl")):
            if du_dev(p.parent):
                return p.parent
    raise SystemExit("Không thấy C0.jsonl + L.jsonl đủ vụ dev: gắn Output có ket_qua_dev_<mô hình>.zip vào Input rồi chạy lại ô này")


def ket_hop(c0, l, cach):
    """(Điều hiển thị, có phải lùi không). Giống src/ban_an/chon_dieu.ket_hop ở E:\\Lexo."""
    a, b = list(dict.fromkeys(c0)), list(dict.fromkeys(l))
    if cach == "hop":
        return cd.sap_xep(a + b), False
    giao = [d for d in a if d in set(b)]
    if giao:
        return cd.sap_xep(giao), False
    lui = (b or a) if cach == "loc_l" else (a or b)
    return cd.sap_xep(lui), bool(a or b)


NGUON = tim_ket_qua()
print("Đọc kết quả từ", NGUON)
kq = {c: [r for r in db.doc_jsonl(NGUON / f"{c}.jsonl") if r["id"] in DEV] for c in ("C0", "L")}
theo_l = {r["id"]: r for r in kq["L"]}
for ten, cach in (("HOP", "hop"), ("LOC", "loc_l"), ("LOC0", "loc_c0")):
    kq[ten] = []
    for a in kq["C0"]:
        b = theo_l[a["id"]]
        hien, lui = ket_hop(a["hien_thi"], b["hien_thi"], cach)
        kq[ten].append({"id": a["id"], "cau_hinh": ten, "dieu": a["dieu"], "tu": {"C0": a["hien_thi"], "L": b["hien_thi"]},
                        "hien_thi": hien, "lui": lui, "cham": cd.cham_chon(a["dieu"], hien),
                        "loi": "; ".join(f"{r['cau_hinh']}: {r['loi']}" for r in (a, b) if r.get("loi")) or None,
                        "giay": (a.get("giay") or 0) + (b.get("giay") or 0),
                        "co_the_bi_cat": bool(a.get("co_the_bi_cat") or b.get("co_the_bi_cat")),
                        "co_think": bool(a.get("co_think") or b.get("co_think"))})

RA = WORK / "ket_hop_dev"
RA.mkdir(exist_ok=True)
tom = {c: db.tong_hop(v) for c, v in kq.items()}
dong = [f"# Kết hợp C0 và L trên dev — {len(kq['C0'])} vụ", "", f"Nguồn: {NGUON}", "",
        "| cấu hình | tìm đủ | bao phủ | chính xác | khớp đúng | Điều hiển thị TB | số hành vi TB | đúng số hành vi | lỗi | có thể bị cắt | giây/vụ |",
        "|---|---|---|---|---|---|---|---|---|---|---|"]
dong += [db.dong_bang(c, tb) for c, tb in tom.items()]
dong += ["", "HOP = C0 ∪ L. LOC = C0 ∩ L, giao rỗng thì giữ L. LOC0 = C0 ∩ L, giao rỗng thì giữ C0. Số vụ giao rỗng (phải lùi): "
         + ", ".join(f"{c} {sum(r['lui'] for r in kq[c])}/{len(kq[c])}" for c in ("LOC", "LOC0")) + "."]
dong += ["", "## So sánh cặp (McNemar chính xác trên «tìm đủ»)", "", "| so sánh | vụ khác nhau | thắng / thua | p |", "|---|---|---|---|"]
for a, b in (("L", "C0"), ("HOP", "C0"), ("LOC", "C0"), ("LOC0", "C0"), ("LOC", "L"), ("LOC0", "L")):
    n, at, bt, p = db.so_cap(kq[a], kq[b])
    dong.append(f"| {a} so với {b} | {n} | {at} / {bt} | {p:.3f} |")
dong += ["", "## Từng vụ", "", "| vụ | đáp án | C0 | L | HOP | LOC | LOC0 |", "|---|---|---|---|---|---|---|"]
for i, a in enumerate(kq["C0"]):
    o = [f"{','.join(kq[c][i]['hien_thi']) or '-'}{' ✓' if kq[c][i]['cham']['tim_du'] else ''}" for c in ("C0",)]
    o.append(f"{','.join(theo_l[a['id']]['hien_thi']) or '-'}{' ✓' if theo_l[a['id']]['cham']['tim_du'] else ''}")
    o += [f"{','.join(kq[c][i]['hien_thi']) or '-'}{' ✓' if kq[c][i]['cham']['tim_du'] else ''}{' (lùi)' if kq[c][i]['lui'] else ''}"
          for c in ("HOP", "LOC", "LOC0")]
    dong.append(f"| {a['id']} | {','.join(a['dieu'])} | " + " | ".join(o) + " |")
dong += ["", "✓ = tìm đủ. Dev chỉ 21 vụ và đã được xem nhiều lần: chỉ để định hướng, không kết luận việc học giúp hay không."]
txt = "\n".join(dong) + "\n"
(RA / "bao_cao.md").write_text(txt, encoding="utf-8")
for c in ("HOP", "LOC", "LOC0"):
    (RA / f"{c}.jsonl").write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in kq[c]), encoding="utf-8")
with zipfile.ZipFile(WORK / "ket_qua_ket_hop_dev.zip", "w", zipfile.ZIP_DEFLATED) as f:
    for p in sorted(RA.iterdir()):
        f.write(p, f"ket_hop_dev/{p.name}")
try:
    from IPython.display import Markdown, display
    display(Markdown(txt))
except ImportError:
    print(txt)
print("Đã ghi", WORK / "ket_qua_ket_hop_dev.zip")
