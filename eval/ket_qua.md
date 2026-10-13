Bộ câu hỏi: cau_hoi_thu.json (58 câu); mô hình ollama:bge-m3

| chế độ | Hit@1 | Hit@3 | Hit@5 | Hit@10 | MRR |
|---|---|---|---|---|---|
| hybrid | 57% | 84% | 88% | 93% | 0.706 |
| vector | 64% | 84% | 88% | 95% | 0.753 |
| fts | 52% | 67% | 76% | 78% | 0.619 |

Hit@k = tỷ lệ câu mà Điều đáp án nằm trong k Điều đầu. MRR = trung bình 1/hạng của đáp án (1.0 là luôn đứng đầu).

## Các câu đáp án KHÔNG nằm trong top 3 (hybrid): 9/58

- [q01] lén lấy xe máy của hàng xóm bị phạt sao  -> đáp án Điều 173, hạng 20; hạng 1 là: Điều 265. Tội tổ chức đua xe trái phép
- [q03] cầm dao dọa đâm để lấy tiền người ta  -> đáp án Điều 168, hạng 4; hạng 1 là: Điều 133. Tội đe dọa giết người
- [q04] gạt người khác đưa tiền đầu tư rồi biến mất luôn  -> đáp án Điều 174, hạng 13; hạng 1 là: Điều 209. Tội cố ý công bố thông tin sai lệch hoặc che giấu thông tin trong hoạt động chứng khoán
- [q08] cãi nhau rồi cầm dao đâm chết người  -> đáp án Điều 123, hạng 8; hạng 1 là: Điều 128. Tội vô ý làm chết người
- [q09] uống rượu lái xe gây tai nạn làm chết người  -> đáp án Điều 260, hạng 21; hạng 1 là: Điều 263. Tội điều động người không đủ điều kiện điều khiển phương tiện tham gia giao thông đường bộ
- [q33] mua lại đồ ăn trộm dù biết là của gian  -> đáp án Điều 323, hạng 6; hạng 1 là: Điều 173. Tội trộm cắp tài sản
- [q34] ly hôn rồi không chịu đóng tiền nuôi con  -> đáp án Điều 186, hạng 74; hạng 1 là: Điều 183. Tội tổ chức tảo hôn
- [q38] bán phụ nữ và trẻ em ra nước ngoài  -> đáp án Điều 150/151, hạng 4; hạng 1 là: Điều 349. Tội tổ chức, môi giới cho người khác trốn đi nước ngoài hoặc ở lại nước ngoài trái phép
- [q41] tự ý xông vào nhà người khác khi chủ nhà không đồng ý  -> đáp án Điều 158, hạng 7; hạng 1 là: Điều 136. Tội cố ý gây thương tích hoặc gây tổn hại cho sức khỏe của người khác do vượt quá giới hạn phòng vệ chính đáng hoặc do vượt quá mức cần thiết khi bắt giữ người phạm tội

## Hạng từng câu

- [q01] hybrid=20, vector=10, fts=-  lén lấy xe máy của hàng xóm bị phạt sao
- [q02] hybrid=2, vector=1, fts=7  giật điện thoại của người đi đường rồi chạy xe bỏ chạy
- [q03] hybrid=4, vector=3, fts=18  cầm dao dọa đâm để lấy tiền người ta
- [q04] hybrid=13, vector=4, fts=-  gạt người khác đưa tiền đầu tư rồi biến mất luôn
- [q05] hybrid=3, vector=17, fts=1  mượn tiền rồi bỏ trốn không chịu trả
- [q06] hybrid=2, vector=1, fts=5  nhặt được điện thoại người khác đánh rơi nhưng không trả lại
- [q07] hybrid=3, vector=2, fts=22  đánh người ta nhập viện, tỷ lệ thương tật cao
- [q08] hybrid=8, vector=2, fts=67  cãi nhau rồi cầm dao đâm chết người
- [q09] hybrid=21, vector=15, fts=13  uống rượu lái xe gây tai nạn làm chết người
- [q10] hybrid=2, vector=1, fts=3  chạy xe máy đua với nhau trên đường phố
- [q11] hybrid=1, vector=1, fts=1  tổ chức cho nhiều người đua xe để cá cược
- [q12] hybrid=3, vector=2, fts=11  cất ma túy trong người để tự dùng
- [q13] hybrid=1, vector=1, fts=2  bán ma túy cho người khác
- [q14] hybrid=1, vector=1, fts=2  chở thuê ma túy từ tỉnh này sang tỉnh khác
- [q15] hybrid=2, vector=2, fts=2  đánh bạc ăn tiền bằng bài hoặc cá độ
- [q16] hybrid=1, vector=2, fts=1  mở sòng bạc, chủ chứa cho người khác tới đánh bạc
- [q17] hybrid=3, vector=1, fts=16  cán bộ nhận tiền của dân để giải quyết hồ sơ
- [q18] hybrid=3, vector=1, fts=2  cán bộ lấy tiền công quỹ bỏ vào túi riêng
- [q19] hybrid=1, vector=1, fts=1  đăng bài chửi bới bôi nhọ danh dự người khác trên mạng
- [q20] hybrid=1, vector=9, fts=1  bịa chuyện nói xấu người khác để hại họ
- [q21] hybrid=1, vector=1, fts=1  hack vào máy tính người khác để lấy dữ liệu
- [q22] hybrid=1, vector=1, fts=1  tạo và phát tán virus, mã độc cho máy tính
- [q23] hybrid=1, vector=1, fts=4  dùng mạng internet lừa đảo lấy tiền
- [q24] hybrid=1, vector=1, fts=1  làm giả con dấu và giấy tờ của cơ quan nhà nước
- [q25] hybrid=1, vector=1, fts=1  sản xuất và bán hàng giả
- [q26] hybrid=1, vector=1, fts=1  bán thực phẩm bẩn không đảm bảo vệ sinh an toàn
- [q27] hybrid=1, vector=1, fts=1  xả nước thải ra sông gây ô nhiễm
- [q28] hybrid=1, vector=1, fts=1  chặt phá rừng trái phép lấy gỗ
- [q29] hybrid=1, vector=1, fts=1  buôn bán động vật hoang dã quý hiếm
- [q30] hybrid=1, vector=3, fts=1  công ty cố ý khai thiếu để không đóng thuế
- [q31] hybrid=1, vector=1, fts=1  cho vay nặng lãi lấy lãi cao
- [q32] hybrid=2, vector=3, fts=3  hợp thức hóa tiền do phạm tội mà có thông qua ngân hàng
- [q33] hybrid=6, vector=7, fts=62  mua lại đồ ăn trộm dù biết là của gian
- [q34] hybrid=74, vector=55, fts=-  ly hôn rồi không chịu đóng tiền nuôi con
- [q35] hybrid=1, vector=1, fts=1  đang có vợ mà đi lấy vợ khác
- [q36] hybrid=2, vector=6, fts=1  cưỡng ép quan hệ tình dục trái ý muốn
- [q37] hybrid=1, vector=1, fts=1  sờ soạng, dâm ô với trẻ em
- [q38] hybrid=4, vector=1, fts=37  bán phụ nữ và trẻ em ra nước ngoài
- [q39] hybrid=1, vector=1, fts=1  nhắn tin dọa giết người khác
- [q40] hybrid=1, vector=1, fts=1  bắt giữ người trái pháp luật nhốt trong nhà
- [q41] hybrid=7, vector=1, fts=107  tự ý xông vào nhà người khác khi chủ nhà không đồng ý
- [q42] hybrid=1, vector=1, fts=2  đập phá, đốt xe của người khác cho hư hỏng
- [q43] hybrid=1, vector=1, fts=4  đánh nhau gây náo loạn nơi công cộng
- [q44] hybrid=3, vector=1, fts=188  chửi bới, đánh công an đang làm nhiệm vụ
- [q45] hybrid=1, vector=1, fts=1  trốn không đi nghĩa vụ quân sự
- [q46] hybrid=1, vector=1, fts=1  cất giữ súng quân dụng trái phép
- [q47] hybrid=2, vector=2, fts=4  buôn lậu hàng hóa qua biên giới
- [q48] hybrid=1, vector=1, fts=1  làm giả hồ sơ để trục lợi bảo hiểm y tế
- [q49] hybrid=1, vector=1, fts=4  in tiền giả đem tiêu
- [q50] hybrid=1, vector=1, fts=1  thấy người gặp nạn mà không cứu giúp
- [q51] hybrid=1, vector=1, fts=1  sơ ý làm người khác chết
- [q52] hybrid=1, vector=1, fts=1  sinh con ra rồi vứt bỏ làm cháu chết
- [q53] hybrid=1, vector=1, fts=1  cố tình làm lây lan dịch bệnh nguy hiểm ra cộng đồng
- [q54] hybrid=1, vector=1, fts=1  mở nhà chứa gái mại dâm
- [q55] hybrid=1, vector=2, fts=1  kinh doanh đa cấp bất hợp pháp lôi kéo người tham gia
- [q56] hybrid=2, vector=2, fts=1  đăng tin sai sự thật chống phá nhà nước
- [q57] hybrid=3, vector=4, fts=2  cho nhiều người đến nhà mình sử dụng ma túy
- [q58] hybrid=2, vector=2, fts=2  cán bộ thiếu trách nhiệm làm thất thoát tài sản nhà nước
