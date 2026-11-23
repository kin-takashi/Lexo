# Xem duyệt 20 tình huống nhiều Điều mới của tập dev (dn15–dn34)

Soạn nháp bởi Claude ngày 2026-10-16 (`nguon = claude`, `trang_thai = nhap`). Cần bạn đọc từng câu: (1) tình huống có đúng như đời thực không, (2) tập Điều đáp án có đủ và không dư, (3) các hành vi tách tay (mốc «tách lý tưởng») có hợp lý.
Cách duyệt: sửa thẳng `eval/bo_cau_hoi.json`, đổi `trang_thai` thành `da_duyet` khi chấp nhận; chạy lại `python scripts/kiem_tra_bo_cau_hoi.py`. Câu nào không chắc, xem mục «Ghi chú nhãn» của từng câu và hỏi người có chuyên môn.

Đặc điểm: tổ hợp Điều không trùng tổ hợp nào trong 450 mẫu học và 40 câu nhiều Điều cũ (đã kiểm bằng `mau_trung`); câu hỏi không chứa «điều/khoản/bộ luật» và hành vi không kèm tên tội.

## dn15

**Câu hỏi:** Anh Tín chạy xe máy chở hơn 2 ký ma túy đá giấu trong cốp xe, nhận chở thuê từ biên giới về thành phố để lấy 30 triệu. Đến chốt kiểm soát bị yêu cầu mở cốp, anh rút dao bấm vung lên dọa rồi xô ngã một chiến sĩ công an để bỏ chạy.

**Đáp án (tìm đủ):**
- Điều 250 — Tội vận chuyển trái phép chất ma túy
- Điều 330 — Tội chống người thi hành công vụ

**Hành vi tách tay:**
1. Nhận chở thuê hơn 2 ký ma túy đá bằng xe máy từ biên giới về thành phố
2. Rút dao vung dọa và xô ngã chiến sĩ công an đang kiểm tra để bỏ chạy

## dn16

**Câu hỏi:** Công ty bán hàng trực tuyến của chị Mai bỗng bị một nhóm gửi hàng triệu lượt truy cập giả làm trang web sập suốt hai ngày, thiệt hại hơn 300 triệu đồng tiền đơn hàng. Sau đó có người nhắn tin bảo muốn trang chạy lại thì phải chuyển 200 triệu vào ví điện tử, nếu không sẽ đánh sập tiếp.

**Đáp án (tìm đủ):**
- Điều 287 — Tội cản trở hoặc gây rối loạn hoạt động của mạng máy tính, mạng viễn thông, phương tiện điện tử
- Điều 170 — Tội cưỡng đoạt tài sản

**Hành vi tách tay:**
1. Gửi hàng triệu lượt truy cập giả làm sập trang web bán hàng của công ty suốt hai ngày, gây thiệt hại hơn 300 triệu
2. Nhắn tin dọa đánh sập tiếp để ép công ty chuyển 200 triệu vào ví điện tử

**Ghi chú nhãn:** Đánh sập web (287) rồi đòi tiền (170); đòi tiền bằng cách dọa đánh sập tiếp là cưỡng đoạt chứ không phải một tội riêng về mạng.

## dn17

**Câu hỏi:** Anh Quân bị tạm giữ ở công an huyện vì vụ đánh nhau. Người nhà đưa 50 triệu cho cán bộ giữ buồng giam sau khi anh này gợi ý sẽ lo cho ra. Nhận tiền xong, tối hôm sau cán bộ tự mở cửa buồng cho anh Quân về mà không có quyết định nào.

**Đáp án (tìm đủ):**
- Điều 378 — Tội tha trái pháp luật người bị bắt, người đang bị tạm giữ, tạm giam, người đang chấp hành án phạt tù
- Điều 354 — Tội nhận hối lộ
- Điều 364 — Tội đưa hối lộ

**Hành vi tách tay:**
1. Người nhà đưa 50 triệu cho cán bộ giữ buồng giam để nhờ lo cho người bị tạm giữ ra
2. Cán bộ giữ buồng giam nhận 50 triệu của người nhà người bị tạm giữ
3. Tự mở cửa buồng thả người đang bị tạm giữ khi không có quyết định nào

**Ghi chú nhãn:** Có đủ ba hành vi: đưa hối lộ (364), nhận hối lộ (354), thả người trái pháp luật (378).

## dn18

**Câu hỏi:** Anh Bảo cãi nhau với hàng xóm về lối đi chung, từng bị công an xã phạt hành chính vì tự ý vào nhà người ta. Tối qua anh lại đạp cửa xông vào nhà ông Lộc, đập vỡ tivi và tủ kính thiệt hại hơn 20 triệu rồi chỉ vào mặt ông dọa sẽ cầm dao giết cả nhà.

**Đáp án (tìm đủ):**
- Điều 158 — Tội xâm phạm chỗ ở của người khác
- Điều 178 — Tội hủy hoại hoặc cố ý làm hư hỏng tài sản
- Điều 133 — Tội đe dọa giết người

**Hành vi tách tay:**
1. Đạp cửa xông vào nhà hàng xóm dù từng bị phạt hành chính vì tự ý vào nhà người khác
2. Đập vỡ tivi và tủ kính trong nhà, thiệt hại hơn 20 triệu
3. Chỉ vào mặt dọa cầm dao giết cả nhà ông hàng xóm

## dn19

**Câu hỏi:** Công ty may của ông Hải đã ba năm không đóng bảo hiểm xã hội cho 200 công nhân, nợ gần 4 tỷ đồng dù bị nhắc nhiều lần. Cô phụ trách nhân sự của công ty còn lập hồ sơ nghỉ việc giả cho mười người quen để nhận trợ cấp thất nghiệp, chiếm hơn 250 triệu.

**Đáp án (tìm đủ):**
- Điều 216 — Tội trốn đóng bảo hiểm xã hội, bảo hiểm y tế, bảo hiểm thất nghiệp cho người lao động
- Điều 214 — Tội gian lận bảo hiểm xã hội, bảo hiểm thất nghiệp

**Hành vi tách tay:**
1. Không đóng bảo hiểm xã hội cho 200 công nhân suốt ba năm, nợ gần 4 tỷ đồng
2. Lập hồ sơ nghỉ việc giả cho mười người quen để nhận trợ cấp thất nghiệp hơn 250 triệu

## dn20

**Câu hỏi:** Chủ cây xăng ở ngoại thành cho thợ chỉnh bộ đếm của cột bơm để mỗi lít xăng bán ra bị thiếu 50 mililit, nhiều năm liền thu lợi hơn 600 triệu. Ông còn không xuất hóa đơn, khai thấp doanh thu để trốn hơn 1,4 tỷ đồng tiền thuế.

**Đáp án (tìm đủ):**
- Điều 198 — Tội lừa dối khách hàng
- Điều 200 — Tội trốn thuế

**Hành vi tách tay:**
1. Cho chỉnh bộ đếm cột bơm để mỗi lít xăng bán ra thiếu 50 mililit, thu lợi hơn 600 triệu
2. Không xuất hóa đơn và khai thấp doanh thu để trốn hơn 1,4 tỷ đồng tiền thuế

## dn21

**Câu hỏi:** Ông Tám chuyên rủ ba đứa trẻ mười lăm, mười sáu tuổi trong xóm đi trộm xe máy và linh kiện, hứa chia tiền mỗi lần. Số hàng lấy được ông đem bán cho một tiệm sửa xe, chủ tiệm biết rõ là đồ ăn trộm nhưng vẫn mua giá rẻ.

**Đáp án (tìm đủ):**
- Điều 325 — Tội dụ dỗ, ép buộc hoặc chứa chấp người dưới 18 tuổi phạm pháp
- Điều 323 — Tội chứa chấp hoặc tiêu thụ tài sản do người khác phạm tội mà có

**Hành vi tách tay:**
1. Rủ ba đứa trẻ mười lăm, mười sáu tuổi đi trộm xe máy và linh kiện rồi chia tiền
2. Chủ tiệm sửa xe mua đồ ăn trộm giá rẻ dù biết rõ nguồn gốc

## dn22

**Câu hỏi:** Ông Bảy dựng sới đá gà ăn tiền ở bãi đất sau nhà, thu tiền hồ của người xem, mỗi buổi vài chục triệu. Hôm công an ập vào bắt quả tang, anh Mạnh đang đặt cược liền vớ cây gậy quơ về phía tổ công tác để mọi người chạy thoát.

**Đáp án (tìm đủ):**
- Điều 322 — Tội tổ chức đánh bạc hoặc gá bạc
- Điều 321 — Tội đánh bạc
- Điều 330 — Tội chống người thi hành công vụ

**Hành vi tách tay:**
1. Dựng sới đá gà ăn tiền ở bãi đất sau nhà, thu tiền hồ của người xem mỗi buổi vài chục triệu
2. Đặt cược ăn thua tiền tại sới đá gà
3. Vớ cây gậy quơ về phía tổ công an để mọi người chạy thoát

**Ghi chú nhãn:** Dễ lệch 321/322: người đặt cược ở sới là đánh bạc (321), chủ sới là tổ chức đánh bạc (322); tiếng «chống người thi hành công vụ» (330) chỉ ở hành vi quơ gậy.

## dn23

**Câu hỏi:** Anh Lực trồng hơn 300 cây cần sa xen trong vườn rau sau nhà. Cây thu hoạch anh phơi khô, chia thành từng gói nhỏ bán cho thanh niên trong vùng, mỗi tháng kiếm vài chục triệu.

**Đáp án (tìm đủ):**
- Điều 247 — Tội trồng cây thuốc phiện, cây côca, cây cần sa hoặc các loại cây khác có chứa chất ma túy
- Điều 251 — Tội mua bán trái phép chất ma túy

**Hành vi tách tay:**
1. Trồng hơn 300 cây cần sa xen trong vườn rau sau nhà
2. Phơi khô cần sa, chia gói nhỏ bán cho thanh niên trong vùng

## dn24

**Câu hỏi:** Cơ sở của ông Tuấn pha bột sữa rẻ tiền với tinh bột rồi đóng vào hộp mang nhãn sữa dinh dưỡng cho trẻ em, bán ra thị trường hơn 3 tỷ đồng. Doanh thu này ông không khai, không xuất hóa đơn nên trốn hơn 600 triệu đồng tiền thuế.

**Đáp án (tìm đủ):**
- Điều 193 — Tội sản xuất, buôn bán hàng giả là lương thực, thực phẩm, phụ gia thực phẩm
- Điều 200 — Tội trốn thuế

**Hành vi tách tay:**
1. Pha bột sữa rẻ tiền với tinh bột đóng hộp mang nhãn sữa dinh dưỡng cho trẻ em bán hơn 3 tỷ đồng
2. Không khai doanh thu, không xuất hóa đơn để trốn hơn 600 triệu đồng tiền thuế

## dn25

**Câu hỏi:** Sau trận lũ, ông chủ tịch xã nhận 400 triệu tiền cứu trợ về cho dân. Ông bỏ túi 150 triệu, số gạo và mì tôm còn lại thì phát cho họ hàng và người thân quen, trong khi nhiều hộ mất nhà thật sự không được nhận gì.

**Đáp án (tìm đủ):**
- Điều 353 — Tội tham ô tài sản
- Điều 231 — Tội cố ý làm trái quy định về phân phối tiền, hàng cứu trợ

**Hành vi tách tay:**
1. Giữ lại 150 triệu trong số tiền cứu trợ lũ bỏ túi riêng
2. Phát gạo và mì tôm cứu trợ cho họ hàng, người quen mà không phát cho các hộ mất nhà

**Ghi chú nhãn:** 353 (tham ô) cho phần bỏ túi; 231 cho phần phát sai đối tượng. Một số người sẽ cho là 356 hoặc 355.

## dn26

**Câu hỏi:** Trong phiên xử vụ tranh chấp đất, thân nhân của bị cáo đứng giữa phòng xử la hét chửi chủ tọa và ném dép lên bàn hội đồng xét xử. Khi cảnh sát tư pháp tiến đến yêu cầu ra ngoài, một người xô mạnh và đạp vào chân anh ấy.

**Đáp án (tìm đủ):**
- Điều 391 — Tội gây rối trật tự phiên tòa, phiên họp
- Điều 330 — Tội chống người thi hành công vụ

**Hành vi tách tay:**
1. La hét chửi chủ tọa và ném dép lên bàn hội đồng xét xử giữa phiên tòa
2. Xô và đạp vào chân cảnh sát tư pháp đang yêu cầu ra khỏi phòng xử

**Ghi chú nhãn:** 330 hay chỉ 391? Hành vi xô/đạp cảnh sát tư pháp có thể bị coi nằm trong 391 (gây rối phiên tòa) hay tách sang 330. Nhãn hiện tại: tách.

## dn27

**Câu hỏi:** Chị Ngọc bán mỹ phẩm online bị một người từng làm chung nhắn tin dọa sẽ tung lên mạng chuyện chị bán hàng giả, trừ khi chị đưa 50 triệu. Chị không đưa, người này liền đăng bài khắp các nhóm bịa chuyện chị lừa đảo, bán hàng giả khiến chị mất hết khách.

**Đáp án (tìm đủ):**
- Điều 170 — Tội cưỡng đoạt tài sản
- Điều 156 — Tội vu khống

**Hành vi tách tay:**
1. Nhắn tin dọa tung tin chị bán hàng giả lên mạng nếu không đưa 50 triệu
2. Đăng bài khắp các nhóm bịa chuyện chị lừa đảo, bán hàng giả

**Ghi chú nhãn:** Nhắn đòi 50 triệu kèm dọa tung tin = cưỡng đoạt (170); bài bịa chuyện = vu khống (156). Bài đăng có thể bị xét thêm theo 155 (làm nhục) nếu lời lẽ xúc phạm.

## dn28

**Câu hỏi:** Hai bảo vệ siêu thị nghi một cậu thanh niên lấy trộm đồ nên lôi vào phòng kho phía sau, khóa cửa nhốt gần năm tiếng. Trong lúc nhốt, một người rút dao dọa sẽ giết nếu cậu không nhận, người kia lấy gậy đánh khiến cậu bị tổn hại sức khỏe 16%.

**Đáp án (tìm đủ):**
- Điều 157 — Tội bắt, giữ hoặc giam người trái pháp luật
- Điều 133 — Tội đe dọa giết người
- Điều 134 — Tội cố ý gây thương tích hoặc gây tổn hại cho sức khỏe của người khác

**Hành vi tách tay:**
1. Lôi thanh niên nghi lấy trộm đồ vào phòng kho, khóa cửa nhốt gần năm tiếng
2. Rút dao dọa sẽ giết nếu không nhận đã lấy trộm
3. Lấy gậy đánh khiến thanh niên bị tổn hại sức khỏe 16%

## dn29

**Câu hỏi:** Giám đốc một công ty cổ phần cho làm giả báo cáo kiểm toán rồi nộp kèm hồ sơ xin phát hành cổ phiếu ra thị trường. Sau đó ông còn cho đăng lên website công ty bản báo cáo tài chính ghi doanh thu lớn gấp nhiều lần thực tế, làm nhà đầu tư tin theo mà mất hơn 80 tỷ.

**Đáp án (tìm đủ):**
- Điều 212 — Tội làm giả tài liệu trong hồ sơ chào bán, niêm yết chứng khoán
- Điều 209 — Tội cố ý công bố thông tin sai lệch hoặc che giấu thông tin trong hoạt động chứng khoán

**Hành vi tách tay:**
1. Cho làm giả báo cáo kiểm toán nộp kèm hồ sơ xin phát hành cổ phiếu ra thị trường
2. Đăng lên website công ty báo cáo tài chính ghi doanh thu lớn gấp nhiều lần thực tế, nhà đầu tư tin theo mất hơn 80 tỷ

**Ghi chú nhãn:** 209 hay 211? Đăng báo cáo tài chính sai trên website = công bố thông tin sai lệch (209); 211 là thao túng thị trường nên không chọn.

## dn30

**Câu hỏi:** Chị Vân vay 20 triệu qua một ứng dụng cho vay với lãi hai phần trăm mỗi ngày, trả gần một năm vẫn còn nợ. Bên cho vay thu của hàng trăm người như vậy hơn 300 triệu tiền lãi, rồi gửi ảnh chị đã chỉnh sửa kèm lời chửi bới cho toàn bộ danh bạ, nhắn sẽ tìm đến nhà giết cả nhà chị nếu không trả.

**Đáp án (tìm đủ):**
- Điều 201 — Tội cho vay lãi nặng trong giao dịch dân sự
- Điều 155 — Tội làm nhục người khác
- Điều 133 — Tội đe dọa giết người

**Hành vi tách tay:**
1. Cho vay 20 triệu với lãi hai phần trăm mỗi ngày, thu của hàng trăm người hơn 300 triệu tiền lãi
2. Gửi ảnh chỉnh sửa kèm lời chửi bới cho toàn bộ danh bạ điện thoại của người vay
3. Nhắn tin dọa tìm đến nhà giết cả nhà nếu không trả nợ

## dn31

**Câu hỏi:** Xưởng gia công hóa chất của ông Vỹ thuê năm em mười bốn, mười lăm tuổi làm ở khu pha hóa chất độc hại, từng bị phạt hành chính vì việc này mà vẫn tiếp tục. Ông còn thu điện thoại, giấy tờ của công nhân và dọa đánh nếu ai không chịu làm thêm đến khuya.

**Đáp án (tìm đủ):**
- Điều 296 — Tội vi phạm quy định về sử dụng người lao động dưới 16 tuổi
- Điều 297 — Tội cưỡng bức lao động

**Hành vi tách tay:**
1. Thuê năm em mười bốn, mười lăm tuổi làm ở khu pha hóa chất độc hại dù từng bị phạt hành chính
2. Thu điện thoại, giấy tờ và dọa đánh để ép công nhân làm thêm đến khuya

**Ghi chú nhãn:** 296 cần «đã bị xử phạt hành chính»; 297 (cưỡng bức lao động) dựa vào hành vi thu giấy tờ và dọa đánh để ép làm thêm; có thể bị cho là chưa đủ yếu tố cưỡng bức.

## dn32

**Câu hỏi:** Một công ty bất động sản tự ý biến hàng chục héc-ta đất lúa thành khu phân lô bán nền khi chưa được chuyển mục đích sử dụng, thu lợi hơn 80 tỷ. Cán bộ địa chính huyện biết rõ vẫn ký cấp giấy chứng nhận cho các lô đất đó, làm Nhà nước thất thu nhiều tỷ đồng.

**Đáp án (tìm đủ):**
- Điều 228 — Tội vi phạm các quy định về sử dụng đất đai
- Điều 229 — Tội vi phạm các quy định về quản lý đất đai

**Hành vi tách tay:**
1. Biến hàng chục héc-ta đất lúa thành khu phân lô bán nền khi chưa được chuyển mục đích sử dụng, thu lợi hơn 80 tỷ
2. Cán bộ địa chính huyện biết rõ vẫn ký cấp giấy chứng nhận cho các lô đất làm Nhà nước thất thu nhiều tỷ đồng

**Ghi chú nhãn:** 228 và 229 gần nghĩa: chủ đầu tư chuyển mục đích đất trái phép → 228, cán bộ địa chính cấp giấy trái quy định → 229; nhãn có thể bị tranh cãi với 356 (lạm dụng chức vụ, quyền hạn).

## dn33

**Câu hỏi:** Quán lẩu bò của bà Hoa dùng thịt đã ôi nhiều ngày nấu cho tiệc cưới, hơn 30 khách phải nhập viện vì ngộ độc. Trước đó quán còn mua thịt trâu đông lạnh nhưng ghi trong thực đơn và hóa đơn là bò Úc để bán giá gấp đôi, thu lợi hơn 120 triệu.

**Đáp án (tìm đủ):**
- Điều 317 — Tội vi phạm quy định về an toàn thực phẩm
- Điều 198 — Tội lừa dối khách hàng

**Hành vi tách tay:**
1. Dùng thịt ôi nhiều ngày nấu cho tiệc cưới khiến hơn 30 khách nhập viện vì ngộ độc
2. Mua thịt trâu đông lạnh nhưng ghi là bò Úc trên thực đơn và hóa đơn để bán giá gấp đôi, thu lợi hơn 120 triệu

**Ghi chú nhãn:** 317 (an toàn thực phẩm) và 198 (lừa dối khách hàng). Có thể bị xét thêm 193 nếu coi thịt trâu ghi là bò Úc là hàng giả.

## dn34

**Câu hỏi:** Anh Quyết ly hôn đã lâu nhưng vẫn nhiều lần tự ý vào nhà vợ cũ, từng bị công an xã lập biên bản phạt hành chính. Đêm qua anh lại đạp cửa xông vào nhà lúc nửa đêm, dùng gậy đánh chị khiến chị bị thương, tỷ lệ tổn thương cơ thể 18%.

**Đáp án (tìm đủ):**
- Điều 158 — Tội xâm phạm chỗ ở của người khác
- Điều 134 — Tội cố ý gây thương tích hoặc gây tổn hại cho sức khỏe của người khác

**Hành vi tách tay:**
1. Đạp cửa xông vào nhà vợ cũ lúc nửa đêm dù từng bị phạt hành chính vì tự ý vào nhà
2. Dùng gậy đánh vợ cũ gây tổn thương cơ thể 18%

---
Còn thiếu: ít nhất 10 tình huống do chính bạn viết (`nguon = nguoi_dung`) để báo cáo riêng và giảm thiên lệch «cùng một người soạn».
