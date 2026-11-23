"""Tập huấn luyện bước tách hành vi (train/tinh_huong.json): kiểm tra hợp lệ, dò rò rỉ sang bộ đo, chia train/val cố định, dòng SFT."""
import json

import pytest

from src.index.bo_cau_hoi import MAC_DINH as BO_DO
from src.index.bo_cau_hoi import doc_bo
from src.index.tap_train import (K_TRUNG, MAC_DINH, TapTrainError, dieu_da_phu, doc_train, dong_sft, kiem_tra_hop_le, tap_cua,
                                 thong_ke)

VAN = "Anh A thấy chiếc xe máy dựng trước cửa hàng nên lén dắt đi bán lấy tiền tiêu xài."


def mot(id_, van=VAN, hv=None, loai="don", **kw):
    x = {"id": id_, "tinh_huong": van, "hanh_vi": hv if hv is not None else [{"mo_ta": "lén lấy trộm một chiếc xe máy", "dieu": ["173"]}],
         "loai": loai, "nguon": "claude", "trang_thai": "nhap"}
    x.update(kw)
    return x


def hai_hv():
    return [{"mo_ta": "lén lấy trộm một chiếc xe máy", "dieu": ["173"]}, {"mo_ta": "đập phá cửa kính của nhà người khác", "dieu": ["178"]}]


def test_hop_le_co_ban():
    assert kiem_tra_hop_le([mot("a"), mot("b", van="Chị B kể rằng mình bị người quen vay tiền rồi bỏ trốn không trả.", loai="nhieu", hv=hai_hv())]) == []


def test_bat_cac_loi():
    loi = "\n".join(kiem_tra_hop_le([
        mot("a"), mot("a", van="Một đoạn khác hoàn toàn nhưng cùng id với mẫu trước đó."),
        mot("c", van=VAN.upper()),                                                     # trùng văn bản (không phân biệt hoa thường)
        mot("d", van="Anh D phạm tội theo Điều 173 của bộ luật hình sự vì lấy xe."),     # nhắc số Điều
        mot("e", van="ngắn"), mot("f", van="Chuyện thứ f đủ dài để qua được kiểm tra độ dài tối thiểu.", hv=[]),
        mot("g", van="Chuyện thứ g cũng đủ dài và có hai hành vi nhưng gắn nhãn là đơn.", hv=hai_hv()),
        mot("h", van="Chuyện thứ h chỉ một hành vi nhưng gắn nhãn là nhiều hành vi khác nhau.", loai="nhieu"),
        mot("i", van="Chuyện thứ i có số Điều sai định dạng ở phần đáp án của hành vi.", hv=[{"mo_ta": "x y z", "dieu": ["abc"]}]),
        mot("j", van="Chuyện thứ j có nguồn không hợp lệ để kiểm tra giá trị liệt kê.", nguon="ai_do"),
        mot("k", van="Chuyện thứ k có mô tả hành vi nhắc điều 5 của luật nào đó để bị bắt.", hv=[{"mo_ta": "vi phạm điều 5", "dieu": ["173"]}]),
    ]))
    for mong_doi in ("a: id trùng", "c: tinh_huong trùng với a", "d: tinh_huong nhắc số Điều", "e: tinh_huong rỗng hoặc quá ngắn",
                     "f: hanh_vi phải là danh sách không rỗng", "g: loai don phải có đúng 1 hanh_vi", "h: loai nhieu cần ít nhất 2 hanh_vi",
                     "i.hanh_vi[1]: dieu phải là danh sách", "j: nguon = 'ai_do'", "k.hanh_vi[1]: mo_ta nhắc số Điều"):
        assert mong_doi in loi, mong_doi


def test_do_ro_ri_sang_bo_do():
    cau_do = ["Tôi bị mất chiếc xe máy ở bãi giữ xe nên có người lén dắt đi bán thì bị xử thế nào?"]
    loi = kiem_tra_hop_le([mot("a", van="Anh A thấy xe máy ở bãi giữ xe nên có người lén dắt đi bán lấy tiền.")], cau_do)
    assert any(f"trùng cụm {K_TRUNG} âm tiết" in x for x in loi)
    assert kiem_tra_hop_le([mot("a")], cau_do) == []                                    # khác cụm dài: không báo
    loi2 = kiem_tra_hop_le([mot("a", hv=[{"mo_ta": "Tôi bị mất chiếc xe máy ở bãi giữ xe nên có người lén dắt đi bán thì bị xử thế nào?", "dieu": ["173"]}])], cau_do)
    assert any("mo_ta trùng nguyên văn" in x for x in loi2)


def test_dieu_da_phu_va_thong_ke():
    mau = [mot("a"), mot("b", van="Chuyện thứ b đủ dài để qua kiểm tra độ dài tối thiểu của mẫu.", hv=hai_hv(), loai="nhieu")]
    c = dieu_da_phu(mau)
    assert c["173"] == 2 and c["178"] == 1
    tk = thong_ke(mau)
    assert tk["so_mau"] == 2 and tk["tong_hanh_vi"] == 3 and tk["so_hanh_vi"] == {1: 1, 2: 1}


def test_tap_cua_co_dinh_theo_id():
    ids = [f"t{i:03d}" for i in range(1000)]
    a = [tap_cua(i, 0.1) for i in ids]
    assert a == [tap_cua(i, 0.1) for i in reversed(ids[::-1])]                          # không phụ thuộc thứ tự hay lần gọi
    assert 60 <= a.count("val") <= 140                                                  # ~10%
    assert all(tap_cua(i, 0.0) == "train" for i in ids)


def test_dong_sft_dich_chi_co_mo_ta_khong_co_so_dieu():
    d = dong_sft(mot("a", van="Chuyện thứ a đủ dài để qua kiểm tra.", hv=hai_hv(), loai="nhieu"))
    assert [m["role"] for m in d["messages"]] == ["system", "user", "assistant"]
    dich = json.loads(d["messages"][2]["content"])
    assert dich == {"hanh_vi": ["lén lấy trộm một chiếc xe máy", "đập phá cửa kính của nhà người khác"]}
    assert "173" not in d["messages"][2]["content"] and "178" not in d["messages"][2]["content"]


def test_doc_train_bao_loi(tmp_path):
    with pytest.raises(TapTrainError, match="không thấy"):
        doc_train(tmp_path / "khong_co.json")
    hong = tmp_path / "hong.json"
    hong.write_text("{khong phai json", encoding="utf-8")
    with pytest.raises(TapTrainError, match="JSON"):
        doc_train(hong)
    thieu = tmp_path / "thieu.json"
    thieu.write_text("{}", encoding="utf-8")
    with pytest.raises(TapTrainError, match="mau"):
        doc_train(thieu)


def test_file_train_that_hop_le_va_khong_ro_ri_sang_bo_do():
    if not MAC_DINH.exists():
        pytest.skip("chưa có train/tinh_huong.json")
    mau = doc_train(MAC_DINH)
    cau_do = [x["cau_hoi"] for x in doc_bo(BO_DO, None, None)] if BO_DO.exists() else []
    assert kiem_tra_hop_le(mau, cau_do) == []
    assert len(mau) >= 100
    # tập val và train của SFT không giao nhau theo id
    tap = {x["id"]: tap_cua(x["id"], 0.1) for x in mau}
    assert set(tap.values()) <= {"train", "val"} and "val" in tap.values() and "train" in tap.values()
