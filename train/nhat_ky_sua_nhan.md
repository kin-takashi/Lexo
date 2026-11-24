# Nhật ký áp bản vá `sua_nhan_train.md` (2026-10-14)

53 mục: **40 áp đúng bản vá**, **11 áp có chỉnh** (khác bản vá ở chi tiết, mục 1), **2 không áp** vì văn bản luật không đòi điều kiện đó (mục 1).
Tập train sau vá: 450 mẫu, 894 hành vi (trước vá 895); một hành vi: 106 mẫu (trước 103); 2 hành vi: 267; 3: 55; 4: 21; 5: 1. Phủ 315/315 Điều tội phạm. Cổng truy hồi (mô tả → Điều đáp án): Hit@1 73,2%, Hit@3 94,9%, Hit@5 100%. Không rò sang bộ đo (cụm ≥ 9 âm tiết; cos lớn nhất 0,89).
Căn cứ đối chiếu: văn bản Điều trong chỉ mục `db/chi_muc.sqlite` (khoản/điểm đang hiệu lực). Mình không có bản BLHS nào khác để so ngoài chỉ mục này.

## 1. Mục khác bản vá

| Mục | Bản vá | Đã làm | Căn cứ trong văn bản Điều |
|---|---|---|---|
| t142 | Thêm «đã bị xử phạt hành chính» cho 331 | Không thêm | Điều 331 khoản 1 không đòi điều kiện này. Thêm vào dễ làm mô hình lẫn với 163/164 (hai Điều đó mới đòi). |
| t220 | Thêm «đã bị xử phạt hành chính» cho 158 | Không thêm | Điều 158 khoản 1 điểm d chỉ đòi «xâm nhập trái pháp luật chỗ ở». |
| t443 | Bỏ HV 158 vì «thiếu yếu tố vũ lực/đe dọa/đã bị xử lý» | Vẫn bỏ HV 158, lý do khác | Các điều kiện đó không có ở Điều 158. Bỏ vì việc vào phòng là phương thức để trộm, nằm trong hành vi trộm cắp. |
| t197 | 256a: thêm «đã bị xử phạt hành chính về hành vi này mà còn tái phạm» | Đổi thành «đang trong thời hạn quản lý sau cai nghiện»; chỉ còn một người | Điều 256a khoản 1 liệt kê 4 điều kiện (đang cai nghiện/điều trị thay thế, đang quản lý sau cai, trong 2 năm sau đó, trong 2 năm từ khi tự ý ngừng cai tự nguyện). Khoản 2 là tái phạm (án tích). |
| t215 | 149 ⚠ 148 | Chỉ 148, không ⚠ | Điều 149 khoản 1: «nếu không thuộc trường hợp quy định tại Điều 148». Điều 148: «biết mình bị nhiễm HIV mà cố ý lây truyền». Người trong t215 tự nhiễm nên là 148. |
| t010 | 148 ⚠ 149, chọn một nhãn thống nhất với t011, t215 | Giữ 148 duy nhất | Cùng lý do t215. t011 (người không nhiễm dùng kim tiêm dính máu người khác) giữ 149. |
| t294 | Đề mới, giữ «thương tật 30%», nhãn 126/136/178 | Đổi thành 35% | Điều 136 khoản 1 chỉ bắt đầu từ tỷ lệ 31%; 30% thì 136 không còn đúng. |
| t196 | 217a: thêm «hơn 100 người, tổng thu hơn 2 tỷ, có người thiệt hại» | Thêm «không có giấy chứng nhận đăng ký», «mạng lưới hơn 100 người», «thu lợi bất chính hơn một tỷ»; bỏ «sản phẩm gần như không bán được» | Điều 217a khoản 1 đòi không có giấy chứng nhận đăng ký + một trong các ngưỡng; khoản 2 điểm c là mạng lưới ≥ 100 người, điểm a là thu lợi ≥ 1 tỷ («thu lợi bất chính», không phải «tổng thu»). Điều này loại trừ trường hợp thuộc 174/290, nên bỏ chi tiết nghiêng về lừa đảo. |
| t224 | Thêm điều kiện «đã bị xử phạt» cho HV 163 | Thêm cho cả HV 164 | Điều 164 khoản 1 cũng đòi «đã bị xử lý kỷ luật hoặc xử phạt vi phạm hành chính … mà còn vi phạm» (bản vá chỉ nêu cho 163). |
| t146 | Thêm HV 354 (quà 20 triệu) | Thêm HV 354 và đặt đầu danh sách; thêm «đã bị xử lý kỷ luật» cho 336 | Điều 336 khoản 1 đòi «đã bị xử lý kỷ luật về hành vi này mà còn vi phạm» (bản vá không nêu). |
| t406 | Đổi 291 → 288 | Đổi 288 và thêm «thu lợi bất chính 120 triệu đồng» | Điều 288 khoản 1 đòi thu lợi từ 50 triệu (hoặc thiệt hại từ 100 triệu, hoặc gây dư luận xấu); đề trước đó không có số nào. |
| t308 | Đổi 379 → 380 | Đổi 380 và thêm «đã bị cơ quan thi hành án cưỡng chế» | Điều 380 khoản 1 đòi «đã bị áp dụng biện pháp cưỡng chế … hoặc đã bị xử phạt hành chính». |
| t440 | Thêm «tư thù cá nhân, hậu quả nghiêm trọng» vào «sa thải cán bộ» | Thêm như bản vá, nhưng đổi thành «buộc thôi việc công chức xã» | Điều 162 khoản 1: điểm a «buộc thôi việc … công chức, viên chức», điểm b «sa thải … người lao động». Người bị đây là cán bộ xã. |

Ghi chú nhỏ: t223 dùng «xử phạt hành chính» thay «xử lý kỷ luật» vì chủ thể là công ty (Điều 165 chấp nhận cả hai); t305 giữ `140 ⚠ 185` theo bản vá nhưng Điều 140 tự loại trừ khi thuộc 185, nên đáp án đúng nghiêng về 185; t244 là `174 ⚠ 290` (174 chính); t296 đổi thứ tự hành vi cho khớp thứ tự trong đề (bắn bừa trước, rời đơn vị sau); t385, t146, t324, t274 chèn hành vi mới theo đúng thứ tự trong đề.

## 2. Mục áp đúng bản vá

Các mục «KC» đã đối chiếu và đúng với văn bản: t221, t346, t444 (159 đòi xử phạt hành chính trước đó), t256 (364 khoản 7: người bị ép đưa hối lộ mà chủ động khai báo trước khi bị phát giác thì không có tội, nên đề cần nói rõ chủ quán không khai báo), t030 (315 khoản 1 điểm a có «làm chết người»), t306 (316 khoản 1 điểm a có «làm chết người»).

| Mục | Thay đổi |
|---|---|
| t052 | nhãn `185 + 186` → `140 + 186`; đề sửa |
| t359 | nhãn `141 + 133` → `141` |
| t378 | đề sửa; mô tả hành vi sửa |
| t408 | nhãn `317 + 192` → `317 + 193`; đề sửa |
| t273 | nhãn `157 + 373` → `157 + 134`; đề sửa |
| t317 | nhãn `128 + 129` → `260 + 129`; đề sửa |
| t049 | đề sửa; mô tả hành vi sửa |
| t291 | đề sửa; mô tả hành vi sửa |
| t240 | đề sửa; mô tả hành vi sửa |
| t223 | đề sửa; mô tả hành vi sửa |
| t301 | đề sửa; mô tả hành vi sửa |
| t221 | đề sửa; mô tả hành vi sửa |
| t346 | đề sửa; mô tả hành vi sửa |
| t444 | đề sửa; mô tả hành vi sửa |
| t401 | đề sửa; mô tả hành vi sửa |
| t360 | đề sửa; mô tả hành vi sửa |
| t344 | đề sửa; mô tả hành vi sửa |
| t296 | nhãn `398 + 397 + 402 + 412` → `398 + 397 + 412 + 402`; đề sửa |
| t244 | nhãn `289 + 290` → `289 + 174/290` |
| t398 | đề sửa; mô tả hành vi sửa |
| t385 | nhãn `151 + 341` → `151 + 151 + 341` |
| t274 | nhãn `123 + 168 + 304 + 323` → `123 + 168 + 304 + 173 + 323` |
| t279 | nhãn `192 + 202 + 226 + 200` → `193 + 202 + 200`; đề sửa |
| t366 | nhãn `141 + 157` → `141` |
| t214 | nhãn `147` → `147 + 326` |
| t284 | đề sửa; mô tả hành vi sửa |
| t303 | đề sửa; mô tả hành vi sửa |
| t324 | nhãn `232 + 233` → `232 + 354 + 233`; đề sửa |
| t158 | đề sửa; mô tả hành vi sửa |
| t038 | đề sửa |
| t427 | đề sửa |
| t381 | đề sửa |
| t256 | đề sửa; mô tả hành vi sửa |
| t305 | nhãn `151 + 140` → `151 + 140/185` |
| t382 | đề sửa; mô tả hành vi sửa |
| t374 | đề sửa; mô tả hành vi sửa |
| t069 | nhãn `202 + 192` → `202 + 193`; đề sửa |
| t071 | đề sửa |
| t030 | nhãn `315 + 129` → `315` |
| t306 | nhãn `316 + 129 + 341` → `316 + 341` |

## 3. Quy tắc đã chốt và việc ngoài bản vá

- **Quy tắc nhóm hàng giả** (chốt sau khi duyệt): hàng làm giả rồi bán như hàng thật/chính hãng (giả chất lượng, công dụng, nguồn gốc, kể cả gắn nhãn hiệu nổi tiếng) → 192–195 theo loại hàng; chỉ nhái nhãn hiệu, bao bì mà bán là hàng nhái → 226. Rà lại: t060 (192), t298, t065 (192), t061, t323, t069, t279, t408 (193), t062, t382 (194), t063 (195) giữ nguyên; t085 và t260 (226) giữ nguyên. Chỉ làm rõ đề của t279 và t408 (thêm «bán như hàng chính hãng») để nhãn 193 đọc ra được từ đề.
- Ngoài bản vá, mình thấy t071 (Điều 205 lập quỹ trái phép) khoản 1 đòi «lợi dụng chức vụ» và «gây thiệt hại tài sản Nhà nước từ 50 triệu đến dưới 200 triệu hoặc đã bị xử lý kỷ luật». Đề hiện chưa nêu ngưỡng đó, mình chưa sửa vì không nằm trong bản vá.
