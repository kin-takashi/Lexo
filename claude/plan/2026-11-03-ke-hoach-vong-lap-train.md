# Kế hoạch: vòng lặp huấn luyện Lexo trên Kaggle

- Ngày: 2026-11-03
- Trạng thái: kế hoạch, chưa build, chưa chạy thử
- Nơi đặt dự kiến: `E:\Lexo\claude\plan\2026-11-03-ke-hoach-vong-lap-train.md`

## 1. Mục tiêu

Chạy huấn luyện dài (dự kiến 40–60 giờ) trên Kaggle mà người dùng không phải mở web Kaggle hay cài gì về Kaggle trên máy. Claude đẩy notebook, chạy, lấy kết quả về, rồi suy nghĩ và chạy vòng tiếp theo. Mọi dataset và notebook đều để private.

## 2. Hai chat và vai trò

| | Chat chính | Chat Kaggle |
|---|---|---|
| Việc | Suy nghĩ, viết kế hoạch từng vòng, đọc kết quả, quyết định đi tiếp, sửa hoặc dừng | Đọc kế hoạch vòng, viết notebook (.ipynb), tạo dataset, đẩy và chạy trên Kaggle, theo dõi, tải output, viết file kết quả ngắn |
| Cần Kaggle MCP | Không | Có |

- Lý do tách: log và output của Kaggle rất dài. Để ở chat Kaggle thì chat chính không bị loãng ngữ cảnh.
- Hai chat trao đổi bằng các file .md trong `claude\plan\` của dự án.

## 3. Hai kiểu vòng

- **Vòng cải tiến (vòng ngoài):** chat chính nghĩ, viết kế hoạch vòng N, chạy trên Kaggle, nhận kết quả, rồi viết vòng N+1 hoặc dừng.
- **Đoạn chạy (vòng trong):** một lần chạy 40–60 giờ vượt giới hạn 12 giờ mỗi phiên, nên chia thành khoảng 4–6 đoạn nối tiếp nhờ checkpoint. Các đoạn tự nối nhau. Chat chính chỉ được gọi khi cả lần chạy xong hoặc lỗi.

## 4. Vòng cải tiến, từng bước

1. Chat chính ghi `claude\plan\YYYY-MM-DD-vong-N-ke-hoach.md`: mục tiêu, dữ liệu vào, việc notebook phải làm, tiêu chí đạt, điều kiện dừng, số giờ dự kiến.
2. Mặc định dừng chờ người dùng duyệt ("chạy").
3. Chat Kaggle đọc kế hoạch, tạo hoặc cập nhật dataset private (`create_dataset`, `create_dataset_version`).
4. Chat Kaggle viết notebook, đẩy lên và chạy bằng `save_notebook` (private, gắn dataset, bật GPU nếu cần).
5. Theo dõi bằng `get_notebook_session_status`: `QUEUED`, `RUNNING`, `COMPLETE`, `ERROR`.
6. Khi `COMPLETE`: liệt kê và tải output (`list_notebook_session_output`, `download_notebook_output`, `download_notebook_output_zip`).
7. Chat Kaggle ghi `claude\plan\YYYY-MM-DD-vong-N-ket-qua.md` ngắn: trạng thái, số đo, lỗi, danh sách file, % hoàn thành. Không dán log thô.
8. Chat chính đọc kết quả rồi chọn: viết kế hoạch vòng N+1, sửa lỗi, hoặc dừng.

## 5. Một lần chạy dài (checkpoint)

Căn cứ trong tài liệu Kaggle:
- Phiên tối đa 12 giờ (CPU, GPU) và 9 giờ (TPU).
- "Save & Run All" phải chạy xong trong 12 giờ mới lưu thành công.
- Thư mục `/kaggle/working` tự lưu tối đa 20 GB.

Thiết kế notebook:
- Biến cấu hình `MAX_HOURS` khoảng 11. Đến mốc này notebook lưu checkpoint rồi tự thoát gọn, không để Kaggle cắt ở 12 giờ.
- Checkpoint gồm trọng số, trạng thái optimizer, số bước, trạng thái ngẫu nhiên, vị trí dữ liệu. Lưu theo mốc 5% tiến độ và theo thời gian (khoảng 30 phút một lần). Chỉ giữ 2 bản gần nhất.
- Ghi file nhỏ `progress.json` (bước, %, giờ đã chạy, số đo) để chat Kaggle đọc mà không cần phân tích log.
- Khi khởi động: có checkpoint thì nạp và chạy tiếp, không có thì chạy từ đầu.

Nối đoạn:
- Đoạn nào kết thúc `COMPLETE` mà tiến độ còn dưới 100% thì đẩy đoạn tiếp theo, nạp checkpoint từ output của đoạn trước.
- Kaggle cho dùng output của một notebook làm dữ liệu đầu vào cho notebook khác, và `save_notebook` có trường `kernel_data_sources`. Checkpoint nặng nhờ đó không đi qua chat hay máy người dùng.
- **Chưa biết** một notebook có dùng được output của chính nó không. Dự kiến dùng hai notebook luân phiên A và B (A lấy output của B, B lấy output của A).
- Nếu cách đó không được, hai phương án dự phòng (đều chưa kiểm chứng):
  - Tải checkpoint về rồi tạo dataset version. Chỉ hợp khi checkpoint nhỏ, vì nội dung file đi qua MCP.
  - Để notebook tự đẩy checkpoint lên một dataset private bằng Kaggle API, token để trong Kaggle Secrets, cần bật internet.
- Hạn mức GPU mỗi tuần có thể làm 40–60 giờ GPU kéo dài hơn một tuần (xem mục 11).

## 6. Giám sát và thông báo

- Kaggle không gọi vào chat được. Tài liệu không nhắc thông báo khi chạy xong.
- **Mặc định:** cuối notebook (khối `try/finally`) gửi thông báo đẩy tới điện thoại qua dịch vụ như ntfy.sh, khi xong hoặc khi lỗi. Người dùng thấy thông báo thì nhắn "xong vòng N" vào chat chính. Tên kênh đặt dài và ngẫu nhiên, không gửi dữ liệu nhạy cảm. Cần bật internet trong notebook.
- Nếu Kaggle cắt cứng ở 12 giờ thì khối `finally` có thể không chạy. Vì vậy phải tự dừng ở khoảng 11 giờ.
- **Tùy chọn tự động:** Claude hẹn giờ quay lại chat (30–60 phút một lần) để hỏi trạng thái, xong thì tự chạy tiếp. Cách này phụ thuộc client.

## 7. Quy ước

- Dataset và notebook luôn private.
- Dùng tên cố định: một notebook (hoặc cặp A/B) và một dataset cho cả dự án, mỗi lần chỉ lên phiên bản mới. Kaggle MCP không có lệnh xóa, nên tạo mới mỗi vòng sẽ chất đống.
- Token Kaggle (bắt đầu bằng `KGAT`) chỉ nằm trong cấu hình MCP. Không dán vào chat, không in ra trong notebook.
- File .md nằm trong `claude\plan\`, tên dạng `YYYY-MM-DD-ten-ngan.md`.
- Output không phải .md tải về `E:\Lexo`. Vị trí chi tiết người dùng sẽ thiết lập sau. Đề xuất thư mục con theo vòng (`vong-01`, `vong-02`...) trong thư mục dữ liệu của dự án.

## 8. Điều kiện dừng (đề xuất)

- Dừng khi đạt tiêu chí ghi trong kế hoạch.
- Dừng và báo khi cùng một lỗi lặp lại 2 lần, hoặc khi hết hạn mức hay hết phiên. Không tự thử lại.
- Tối đa 5 vòng cải tiến. Mỗi vòng chờ người dùng duyệt, có thể bỏ bước duyệt sau vài vòng ổn.

## 9. Đã kiểm chứng và chưa kiểm chứng

Đã đọc trong tài liệu ([Kaggle MCP](https://www.kaggle.com/docs/mcp), [Kaggle Notebooks](https://www.kaggle.com/docs/notebooks)):
- Có `create_dataset` (có `is_private`), `create_dataset_version`, `save_notebook` ("lưu và chạy từ trên xuống dưới", có `is_private`, `dataset_data_sources`, `kernel_data_sources`), `get_notebook_session_status`, các lệnh tải output.
- Không có lệnh xóa dataset hay notebook trong danh sách tool.
- Giới hạn 12 giờ, 9 giờ cho TPU, 20 GB `/kaggle/working`. Output notebook dùng được làm dữ liệu đầu vào cho notebook khác.
- Xác thực bằng OAuth 2.0 hoặc token `KGAT`. Cấu hình Claude Desktop dùng `npx mcp-remote`.

Chưa kiểm chứng (thử ở Giai đoạn 0):
1. `save_notebook` nhận nguyên JSON `.ipynb` hay chỉ mã nguồn.
2. `save_notebook` tự tạo notebook khi tên chưa có và lên phiên bản khi đã có.
3. Tải output về đĩa máy người dùng (phụ thuộc client).
4. Notebook dùng output của notebook khác, và của chính nó.
5. Thông báo ntfy gửi được từ notebook.
6. Output của phiên bị cắt hoặc lỗi có còn không.
7. Hạn mức GPU mỗi tuần.
8. Hẹn giờ kiểm tra trạng thái trên client của người dùng.
9. Đưa dataset lớn lên qua MCP.

## 10. Giai đoạn 0: chạy thử nhỏ trước khi build

Người dùng làm một lần: có tài khoản Kaggle, lấy token (Settings, Generate New Token), dán cấu hình MCP có kèm token vào Claude Desktop hoặc Claude Code.

Sau đó Claude chạy thử:
1. Dataset private 1 file nhỏ, và notebook "hello" đọc dataset rồi ghi 1 file output.
2. Chạy, theo dõi, tải output về `E:\Lexo`.
3. Thử cặp notebook A và B truyền một checkpoint giả nhỏ cho nhau.
4. Thử gửi thông báo ntfy từ notebook.
5. Ghi lại kết quả từng điểm ở mục 9, rồi chỉnh kế hoạch trước khi build thật.

## 11. Còn mở

- Chạy GPU hay CPU. Hạn mức GPU mỗi tuần không có trong trang tài liệu đã đọc. Tôi nhớ khoảng 30 giờ mỗi tuần nhưng chưa kiểm chứng. Xem mục quota trong cài đặt tài khoản Kaggle.
- Thư mục chi tiết cho output (người dùng thiết lập sau).
- Cách chat chính biết vòng xong: mặc định nhắn tay, có thể đổi sang tự động.
- Colab MCP: tạm gác, không nằm trong kế hoạch này.
