-- Lexo — schema SQLite, phiên bản 2.
-- Nguồn: kế hoạch v2 mục 7, có nhiều chỗ khác v2 (xem "KHÁC V2" và "V1 → V2").
--
-- Quy ước
--   * Ngày lưu TEXT ISO 'YYYY-MM-DD'; mọi cột ngày được CHECK là ngày có thật (date() của SQLite chấp nhận 30/02
--     nên kiểm bằng date(julianday(x)) IS x).
--   * Khoảng hiệu lực nửa mở [hieu_luc_tu, hieu_luc_den); hieu_luc_den NULL = đang hiệu lực.
--     "Tại ngày X": hieu_luc_tu <= X AND (hieu_luc_den IS NULL OR X < hieu_luc_den)
--     Khoảng RỖNG (hieu_luc_den = hieu_luc_tu) được phép: bản đó chưa từng có hiệu lực (vd bản gốc của một Điều bị
--     luật sửa đổi thay ngay đúng ngày luật gốc bắt đầu có hiệu lực). Truy vấn "tại ngày X" không bao giờ trả bản rỗng,
--     nhưng lịch sử vẫn giữ để biết bản đó đã tồn tại.
--   * phien_ban_noi_dung là DỮ LIỆU DẪN XUẤT: dựng lại được từ văn bản gốc + lenh_sua_doi đã duyệt, replay theo ngày
--     hiệu lực (src/apply). Nguồn sự thật là file gốc trong raw/ và lenh_sua_doi.
--   * Ràng buộc ở đây chỉ bảo vệ bất biến cấu trúc. Kiểm tra ngữ nghĩa (đích của lệnh tồn tại, số điều/khoản liên tục,
--     cha-con hợp lệ...) nằm ở src/validate và src/apply.
--
-- KHÁC V2 (kế hoạch v2)
--   1. ky_hieu, thu_tu, tieu_de nằm trong phien_ban_noi_dung (có phiên bản), không nằm ở don_vi_luat:
--      đánh số lại chỉ là thêm phiên bản mới cho cùng một nút, không phải tạo nút mới hay chép cây con.
--   2. Mọi nút có văn bản riêng đều có phiên bản, không chỉ nút lá: Khoản có Điểm giữ câu dẫn trong noi_dung.
--   3. quan_he_van_ban bỏ cột don_vi_bi_tac_dong_id (việc này do lenh_sua_doi/phien_ban_noi_dung ghi);
--      mô hình trích xuất nằm ở log_nap.
--   4. loai của don_vi_luat có thêm 'phan' và 'tieu_muc'.
--
-- V1 → V2 (thêm khi bắt đầu nạp luật sửa đổi; DB v1 chưa có dữ liệu nên dựng lại, không migrate)
--   a. van_ban.vai_tro_nap bỏ, chuyển sang log_nap.vai_tro: một văn bản có thể có nhiều vai (Luật 59/2024 vừa là luật
--      mới vừa là luật sửa BLHS).
--   b. van_ban có hai cột ngày hiệu lực: ngay_hieu_luc_theo_van_ban (nguyên văn trong văn bản) và ngay_hieu_luc
--      (thực tế đang dùng, sau khi áp lệnh hoãn hiệu lực).
--   c. phien_ban_noi_dung cho phép khoảng hiệu lực rỗng.
--   d. don_vi_luat.lenh_tao_ra_id: nút do lệnh 'bo_sung' tạo ra (NULL = nút của văn bản gốc). Cho phép dựng lại
--      cây từ văn bản gốc mà không mất/không dư nút.
--   e. lenh_sua_doi viết lại: đích của lệnh là đường dẫn có cấu trúc (dich_json) thay vì id của nút, vì id nút do
--      lệnh 'bo_sung' tạo ra sẽ đổi mỗi lần dựng lại; thêm vi_tri_nguon, can_cu_hieu_luc, khoi_nguon để truy nguồn
--      "điều này do luật nào, điều khoản nào quy định".
--   f. log_nap.phuong_phap (regex / llm / thu_cong) để so baseline với LLM.
--   g. Bảng dieu_khoan_van_ban lưu nguyên văn Điều hiệu lực thi hành và Điều chuyển tiếp của từng văn bản.
--
-- Chỉ mục FTS5 và sqlite-vec: để Bước 4 (đơn vị tìm kiếm chưa chốt).

CREATE TABLE IF NOT EXISTS van_ban (
    id                          INTEGER PRIMARY KEY,
    so_hieu                     TEXT NOT NULL UNIQUE,   -- vd '100/2015/QH13'
    ten_viet_tat                TEXT,                   -- vd 'BLHS'; tra chính xác cần cột này. Luật sửa đổi có thể để trống.
    ten_day_du                  TEXT NOT NULL,
    loai                        TEXT NOT NULL,          -- bo_luat / luat / nghi_quyet / nghi_dinh ...
    ngay_ban_hanh               TEXT CHECK (ngay_ban_hanh IS NULL OR date(julianday(ngay_ban_hanh)) IS ngay_ban_hanh),
                                                        -- với luật của Quốc hội: ngày thông qua ghi ở câu chốt
    ngay_hieu_luc_theo_van_ban  TEXT CHECK (ngay_hieu_luc_theo_van_ban IS NULL
                                            OR date(julianday(ngay_hieu_luc_theo_van_ban)) IS ngay_hieu_luc_theo_van_ban),
    ngay_hieu_luc               TEXT CHECK (ngay_hieu_luc IS NULL OR date(julianday(ngay_hieu_luc)) IS ngay_hieu_luc),
    ngay_het_hieu_luc           TEXT CHECK (ngay_het_hieu_luc IS NULL OR date(julianday(ngay_het_hieu_luc)) IS ngay_het_hieu_luc),
    trang_thai                  TEXT NOT NULL DEFAULT 'con_hieu_luc'
                                CHECK (trang_thai IN ('con_hieu_luc', 'het_hieu_luc', 'chua_co_hieu_luc', 'het_hieu_luc_mot_phan')),
    nguon                       TEXT,                   -- URL hoặc tên file
    file_goc                    TEXT,                   -- đường dẫn trong raw/ (dùng dấu '/')
    ngay_nap                    TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK (ngay_ban_hanh IS NULL OR ngay_hieu_luc IS NULL OR ngay_hieu_luc >= ngay_ban_hanh),
    CHECK (ngay_ban_hanh IS NULL OR ngay_hieu_luc_theo_van_ban IS NULL OR ngay_hieu_luc_theo_van_ban >= ngay_ban_hanh)
);
CREATE INDEX IF NOT EXISTS idx_van_ban_viet_tat ON van_ban (ten_viet_tat);

-- Mỗi lần nạp/trích xuất một văn bản (kể cả chạy lại bằng phương pháp/mô hình khác) là một dòng.
CREATE TABLE IF NOT EXISTS log_nap (
    id               INTEGER PRIMARY KEY,
    van_ban_id       INTEGER REFERENCES van_ban (id),
    file_nguon       TEXT NOT NULL,
    duong_dan_raw    TEXT,
    ngay_nap         TEXT NOT NULL DEFAULT (datetime('now')),
    vai_tro          TEXT NOT NULL CHECK (vai_tro IN ('goc', 'sua_doi', 'hoan_dinh_chi')),
    phuong_phap      TEXT NOT NULL CHECK (phuong_phap IN ('regex', 'llm', 'thu_cong')),
    mo_hinh_su_dung  TEXT,                             -- tên + phiên bản; NULL nếu chỉ dùng code
    ket_qua          TEXT NOT NULL CHECK (ket_qua IN ('thanh_cong', 'loi')),
    ghi_chu          TEXT
);

-- Lệnh sửa đổi: MỌI lệnh đã trích xuất, kể cả trước khi duyệt và của các đợt trích xuất khác nhau.
-- Chỉ lệnh có trang_thai_duyet 'da_duyet'/'da_sua' được dùng để dựng phiên bản (trừ khi xem trước).
--
-- dich_json (đường dẫn có cấu trúc, mỗi phần tử {"loai": "dieu|khoan|diem|chuong|muc|phan", "ky_hieu": "173a"}):
--   sua_doi     {"muc_tieu": [{"duong_dan": [...], "phan": "toan_bo"|"tieu_de"}, ...]}
--   bo_sung     {"cha": [...] | null, "sau": [...] | null, "loai": "khoan", "ky_hieu": "4"}
--   bai_bo      {"muc_tieu": [[...], ...]}
--   thay_cum_tu {"muc_tieu": [[...], ...], "kieu": "thay|bo|chen_sau|chen_truoc|chen_dau|chen_cuoi"}
--   hoan_hieu_luc  NULL (nhắm cả văn bản dich, ngay_hieu_luc_moi là ngày mới)
-- Phần tử đầu của đường dẫn Điều/Chương được tìm trên toàn văn bản (số Điều là duy nhất trong một bộ luật);
-- các phần tử sau là con trực tiếp.
CREATE TABLE IF NOT EXISTS lenh_sua_doi (
    id                 INTEGER PRIMARY KEY,
    van_ban_nguon_id   INTEGER NOT NULL REFERENCES van_ban (id),   -- văn bản chứa lệnh
    log_nap_id         INTEGER NOT NULL REFERENCES log_nap (id),   -- đợt trích xuất (cho biết phương pháp/mô hình)
    thu_tu             INTEGER NOT NULL,                           -- thứ tự trong văn bản nguồn, để replay tất định
    loai_thao_tac      TEXT NOT NULL
                       CHECK (loai_thao_tac IN ('sua_doi', 'bo_sung', 'bai_bo', 'thay_cum_tu', 'danh_so_lai', 'hoan_hieu_luc')),
    van_ban_dich_id    INTEGER NOT NULL REFERENCES van_ban (id),   -- văn bản bị tác động (hoan_hieu_luc: cả văn bản)
    tham_chieu_dich    TEXT,                                       -- nguyên văn tham chiếu trong luật nguồn, vd 'khoản 2 Điều 173'
    dich_json          TEXT CHECK (dich_json IS NULL OR json_valid(dich_json)),
    noi_dung_moi       TEXT,                                       -- nguyên văn khối trích dẫn “...” (do code gắn, không do LLM chép)
    noi_dung_moi_duyet TEXT,                                       -- nội dung sau khi người duyệt sửa (NULL nếu giữ nguyên)
    cum_tu_cu          TEXT,                                       -- thay_cum_tu: chuỗi cũ (NULL với chen_dau/chen_cuoi)
    cum_tu_moi         TEXT,                                       -- thay_cum_tu: chuỗi mới ('' nếu bỏ)
    pham_vi            TEXT CHECK (pham_vi IS NULL OR pham_vi IN ('don_vi', 'dieu', 'toan_van_ban')),
    anh_xa_so_json     TEXT CHECK (anh_xa_so_json IS NULL OR json_valid(anh_xa_so_json)),   -- danh_so_lai: [{"cu":..,"moi":..}]
    ngay_hieu_luc_moi  TEXT CHECK (ngay_hieu_luc_moi IS NULL OR date(julianday(ngay_hieu_luc_moi)) IS ngay_hieu_luc_moi),  -- hoan_hieu_luc
    hieu_luc_tu        TEXT CHECK (hieu_luc_tu IS NULL OR date(julianday(hieu_luc_tu)) IS hieu_luc_tu),   -- mốc hiệu lực của chính lệnh này
    can_cu_hieu_luc    TEXT,                                       -- vì sao ngày đó, vd 'Điều 3 Luật 12/2017/QH14 (mặc định của luật)'
    vi_tri_nguon       TEXT,                                       -- vd 'Điều 1 khoản 21': "điều này do luật nào, điều khoản nào quy định"
    khoi_nguon         TEXT,                                       -- mã khối trong amending.json, vd 'D1.21.a'
    nguon_dong_tu      INTEGER,                                    -- dòng trong văn bản nguồn (giao diện hai cột, validator)
    nguon_dong_den     INTEGER,
    lenh_goc_json      TEXT CHECK (lenh_goc_json IS NULL OR json_valid(lenh_goc_json)),   -- JSON gốc của bộ trích xuất, để tính P/R/F1
    khop_nguyen_van    INTEGER CHECK (khop_nguyen_van IS NULL OR khop_nguyen_van IN (0, 1)),
    trang_thai_duyet   TEXT NOT NULL DEFAULT 'cho_duyet'
                       CHECK (trang_thai_duyet IN ('cho_duyet', 'da_duyet', 'da_sua', 'tu_choi')),
    nguoi_duyet        TEXT,
    ngay_duyet         TEXT,
    ghi_chu_duyet      TEXT,
    ngay_tao           TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (log_nap_id, thu_tu),
    CHECK (trang_thai_duyet NOT IN ('da_duyet', 'da_sua') OR hieu_luc_tu IS NOT NULL),
    CHECK (nguon_dong_tu IS NULL OR nguon_dong_den IS NULL OR nguon_dong_den >= nguon_dong_tu)
);
CREATE INDEX IF NOT EXISTS idx_lenh_nguon ON lenh_sua_doi (van_ban_nguon_id, trang_thai_duyet);
CREATE INDEX IF NOT EXISTS idx_lenh_dich ON lenh_sua_doi (van_ban_dich_id, hieu_luc_tu);

-- Nút trong cây Phần > Chương > Mục > Điều > Khoản > Điểm. Chỉ giữ danh tính và vị trí trong cây;
-- ký hiệu, thứ tự, tiêu đề, nội dung nằm ở phien_ban_noi_dung vì các lệnh sửa đổi làm đổi chúng.
CREATE TABLE IF NOT EXISTS don_vi_luat (
    id             INTEGER PRIMARY KEY,
    van_ban_id     INTEGER NOT NULL REFERENCES van_ban (id),
    cha_id         INTEGER REFERENCES don_vi_luat (id),   -- NULL nếu là nút gốc của văn bản
    loai           TEXT NOT NULL
                   CHECK (loai IN ('phan', 'chuong', 'muc', 'tieu_muc', 'dieu', 'khoan', 'diem')),
    lenh_tao_ra_id INTEGER REFERENCES lenh_sua_doi (id)   -- NULL = nút của văn bản gốc; khác NULL = do lệnh 'bo_sung' tạo
);
CREATE INDEX IF NOT EXISTS idx_don_vi_van_ban ON don_vi_luat (van_ban_id, loai);
CREATE INDEX IF NOT EXISTS idx_don_vi_cha ON don_vi_luat (cha_id);
CREATE INDEX IF NOT EXISTS idx_don_vi_lenh ON don_vi_luat (lenh_tao_ra_id);

-- Phiên bản của từng nút. DỮ LIỆU DẪN XUẤT (xem đầu file).
-- Nguồn của một phiên bản: van_ban_tao_ra_id (+ lenh_tao_ra_id nếu do lệnh sửa đổi tạo; NULL = bản gốc do code parse).
CREATE TABLE IF NOT EXISTS phien_ban_noi_dung (
    id                  INTEGER PRIMARY KEY,
    don_vi_id           INTEGER NOT NULL REFERENCES don_vi_luat (id),
    ky_hieu             TEXT NOT NULL,                 -- TEXT: '173', '173a', '2', 'a'; đổi được theo phiên bản (đánh số lại)
    thu_tu              INTEGER NOT NULL,              -- khóa sắp xếp giữa anh em; cách quãng (1000, 2000...) để chèn không phải đánh lại
    tieu_de             TEXT,                          -- chỉ Phần/Chương/Mục/Điều có
    noi_dung            TEXT NOT NULL DEFAULT '',      -- văn bản riêng của nút: nội dung Điều/Khoản/Điểm không chia nhỏ,
                                                       -- hoặc câu dẫn của Khoản có Điểm; '' nếu nút chỉ là khung
    hieu_luc_tu         TEXT NOT NULL CHECK (date(julianday(hieu_luc_tu)) IS hieu_luc_tu),
    hieu_luc_den        TEXT CHECK (hieu_luc_den IS NULL OR date(julianday(hieu_luc_den)) IS hieu_luc_den),
    van_ban_tao_ra_id   INTEGER NOT NULL REFERENCES van_ban (id),
    lenh_tao_ra_id      INTEGER REFERENCES lenh_sua_doi (id),   -- NULL nếu bản gốc do code parse
    lenh_dong_id        INTEGER REFERENCES lenh_sua_doi (id),   -- lệnh làm hết hiệu lực bản này (thay thế hoặc bãi bỏ)
    doi_chieu_hop_nhat  TEXT NOT NULL DEFAULT 'chua_doi_chieu'
                        CHECK (doi_chieu_hop_nhat IN ('khop', 'khong_khop', 'chua_doi_chieu')),
    nguoi_duyet         TEXT,
    ngay_duyet          TEXT,
    -- Hiệu đính (bảng hieu_dinh): tieu_de/noi_dung ở trên là bản ĐÃ hiệu đính; bản như luật ban hành được giữ ở hai cột *_goc
    -- (NULL = không bị hiệu đính). hieu_dinh_json = mảng id các quy tắc hieu_dinh đã áp vào phiên bản này.
    tieu_de_goc         TEXT,
    noi_dung_goc        TEXT,
    hieu_dinh_json      TEXT CHECK (hieu_dinh_json IS NULL OR json_valid(hieu_dinh_json)),
    CHECK (hieu_luc_den IS NULL OR hieu_luc_den >= hieu_luc_tu)      -- bằng nhau = khoảng rỗng, xem đầu file
);
CREATE INDEX IF NOT EXISTS idx_pb_don_vi ON phien_ban_noi_dung (don_vi_id, hieu_luc_tu);
CREATE INDEX IF NOT EXISTS idx_pb_ky_hieu ON phien_ban_noi_dung (ky_hieu);
CREATE INDEX IF NOT EXISTS idx_pb_van_ban_tao_ra ON phien_ban_noi_dung (van_ban_tao_ra_id);
CREATE INDEX IF NOT EXISTS idx_pb_lenh_tao_ra ON phien_ban_noi_dung (lenh_tao_ra_id);
CREATE INDEX IF NOT EXISTS idx_pb_lenh_dong ON phien_ban_noi_dung (lenh_dong_id);

-- Bất biến quan trọng nhất của "xem theo ngày": tại mỗi ngày, một nút có nhiều nhất một phiên bản.
-- Khi thay thế phải đóng bản cũ (UPDATE hieu_luc_den) trước rồi mới INSERT bản mới.
-- Điều kiện chồng lấn của hai khoảng nửa mở [a,b) và [c,d) là a < d AND c < b; khoảng rỗng chỉ bị coi là chồng lấn
-- khi nằm lọt hẳn bên trong một khoảng khác.
CREATE TRIGGER IF NOT EXISTS trg_pb_khong_chong_lan_insert
BEFORE INSERT ON phien_ban_noi_dung
WHEN EXISTS (
    SELECT 1 FROM phien_ban_noi_dung p
    WHERE p.don_vi_id = NEW.don_vi_id
      AND NEW.hieu_luc_tu < COALESCE(p.hieu_luc_den, '9999-12-31')
      AND p.hieu_luc_tu < COALESCE(NEW.hieu_luc_den, '9999-12-31')
)
BEGIN
    SELECT RAISE(ABORT, 'phien_ban_noi_dung: khoang hieu luc chong lan voi phien ban khac cua cung don vi');
END;

CREATE TRIGGER IF NOT EXISTS trg_pb_khong_chong_lan_update
BEFORE UPDATE OF don_vi_id, hieu_luc_tu, hieu_luc_den ON phien_ban_noi_dung
WHEN EXISTS (
    SELECT 1 FROM phien_ban_noi_dung p
    WHERE p.don_vi_id = NEW.don_vi_id
      AND p.id <> NEW.id
      AND NEW.hieu_luc_tu < COALESCE(p.hieu_luc_den, '9999-12-31')
      AND p.hieu_luc_tu < COALESCE(NEW.hieu_luc_den, '9999-12-31')
)
BEGIN
    SELECT RAISE(ABORT, 'phien_ban_noi_dung: khoang hieu luc chong lan voi phien ban khac cua cung don vi');
END;

-- Hiệu đính kỹ thuật: sửa chữ có bằng chứng (lỗi gõ trong bản luật đăng/sao chép, khác biệt với VĂN BẢN HỢP NHẤT chính thức).
-- KHÔNG dẫn xuất: là quyết định của người duyệt (như lenh_sua_doi), nên sống sót qua rebuild; rebuild() áp lại các quy tắc đã duyệt
-- lên mọi phiên bản của nút (tu_cu phải xuất hiện đúng một lần trong trường đó, nếu không thì bỏ qua phiên bản đó và báo cáo).
-- khoa: khoá nút theo Điều, vd 'dieu 229/khoan 1/diem b' (cùng dạng src/validate/vbhn.key_of).
CREATE TABLE IF NOT EXISTS hieu_dinh (
    id                INTEGER PRIMARY KEY,
    van_ban_id        INTEGER NOT NULL REFERENCES van_ban (id),
    khoa              TEXT NOT NULL,
    truong            TEXT NOT NULL CHECK (truong IN ('noi_dung', 'tieu_de')),
    tu_cu             TEXT NOT NULL CHECK (length(tu_cu) > 0),
    thanh_moi         TEXT NOT NULL,
    loai              TEXT NOT NULL CHECK (loai IN ('loi_go', 'nhieu_chu', 'sai_so_lieu')),
    bang_chung_json   TEXT NOT NULL CHECK (json_valid(bang_chung_json)),
    trang_thai_duyet  TEXT NOT NULL DEFAULT 'cho_duyet' CHECK (trang_thai_duyet IN ('cho_duyet', 'da_duyet', 'tu_choi')),
    nguoi_duyet       TEXT,
    ngay_duyet        TEXT,
    ghi_chu_duyet     TEXT,
    ngay_tao          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    CHECK (trang_thai_duyet = 'cho_duyet' OR (nguoi_duyet IS NOT NULL AND ngay_duyet IS NOT NULL)),
    CHECK (tu_cu <> thanh_moi),
    UNIQUE (van_ban_id, khoa, truong, tu_cu, thanh_moi)
);
CREATE INDEX IF NOT EXISTS idx_hieu_dinh_vb ON hieu_dinh (van_ban_id, trang_thai_duyet);

-- Chiều quan hệ: A <loai_quan_he> B, vd (A, 'sua_doi', B) = A sửa đổi B.
CREATE TABLE IF NOT EXISTS quan_he_van_ban (
    id            INTEGER PRIMARY KEY,
    van_ban_a_id  INTEGER NOT NULL REFERENCES van_ban (id),
    loai_quan_he  TEXT NOT NULL
                  CHECK (loai_quan_he IN ('sua_doi', 'bo_sung', 'thay_the', 'bai_bo', 'hoan_hieu_luc', 'huong_dan', 'dinh_chi')),
    van_ban_b_id  INTEGER NOT NULL REFERENCES van_ban (id),
    ghi_chu       TEXT,
    UNIQUE (van_ban_a_id, loai_quan_he, van_ban_b_id),
    CHECK (van_ban_a_id <> van_ban_b_id)
);

-- Nguyên văn các điều khoản hiệu lực thi hành / chuyển tiếp của từng văn bản. Chỉ LƯU và gắn vào văn bản để hiển thị
-- kèm khi tra; hệ thống không tự suy ra "điều luật nào áp dụng cho hành vi nào" (hồi tố có lợi...): đó là giới hạn đã biết.
CREATE TABLE IF NOT EXISTS dieu_khoan_van_ban (
    id          INTEGER PRIMARY KEY,
    van_ban_id  INTEGER NOT NULL REFERENCES van_ban (id),
    loai        TEXT NOT NULL CHECK (loai IN ('hieu_luc', 'chuyen_tiep')),
    vi_tri      TEXT NOT NULL,                        -- vd 'Điều 3'
    noi_dung    TEXT NOT NULL,
    thu_tu      INTEGER NOT NULL DEFAULT 0,
    UNIQUE (van_ban_id, loai, vi_tri)
);
