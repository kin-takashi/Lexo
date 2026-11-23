-- Lexo — du_lieu.sqlite: dữ liệu huấn luyện + đánh giá kèm NGUỒN GỐC và LỊCH SỬ DUYỆT của từng nhãn. Phiên bản 2.
-- v2 (2026-10-23): thêm bộ 'ban_an' (bản án hình sự thật từ dataset tmquan/anle-toaan-gov-vn, nhãn = Điều tòa án áp dụng,
--     chia tap 'train' / 'test'), bảng ban_an_meta, view v_trung_ban_an. DB v1 dựng lại bằng scripts/nhap_du_lieu.py --reset.
-- Tách khỏi luat.sqlite: luat.sqlite là nguồn sự thật về luật; file này là dữ liệu dựng trên luật.
-- Giữa hai file KHÔNG dùng khóa ngoại (SQLite không ràng buộc chéo file): nhan_dieu ghi số hiệu văn bản + số Điều,
-- cột hash_dieu / ngay_doi_chieu dành cho bước đối chiếu với kho luật (để trống lúc nhập).
--
-- Quy ước
--   * Giai đoạn này file JSON vẫn là nguồn chính (train/tinh_huong.json, eval/bo_cau_hoi.json,
--     inbox/anle_hf/ban_an_hinh_su.json do scripts/xu_ly_anle_hf.py sinh ra); DB là bản NHẬP kèm
--     sha256 của file nguồn (log_nhap). Nguồn đổi thì phải nhập lại (scripts/nhap_du_lieu.py --reset), không sửa ngầm.
--   * lich_su_nhan và duyet CHỈ GHI THÊM (trigger chặn UPDATE / DELETE): lịch sử sửa nhãn không bị viết lại.
--   * Ngày lưu TEXT ISO 'YYYY-MM-DD', kiểm bằng date(julianday(x)) IS x như schema luật.
--
-- Nhóm đáp án trong nhan_dieu (cùng mau_id, cùng nhom):
--   * các Điều CHẤP NHẬN thay thế nhau: trúng một Điều trong nhóm là đúng;
--   * mỗi nhóm là một việc phải tìm đủ. Bộ huấn luyện: nhom = thứ tự hành vi. Bộ đo loại 'don': một nhóm chứa mọi
--     Điều chấp nhận. Bộ đo loại 'nhieu_dieu': mỗi Điều là một nhóm riêng (phải tìm đủ).
--   * Bộ bản án ('ban_an'): mỗi Điều tội phạm tòa án áp dụng là một nhóm riêng (phải tìm đủ); loai 'don' = đúng một Điều.
--
-- Tầng tin cậy (view v_tin_cay) — QUY ƯỚC chờ thống nhất với người hướng dẫn, không phải kết luận pháp lý:
--   tranh_chap  có người độc lập (sinh viên luật, người pháp lý, tòa án) không đồng ý hoặc đòi sửa
--   vang        không tranh chấp, và (có toa_an / nguoi_phap_ly đồng ý, hoặc ≥ 2 sinh_vien_luat khác nhau đồng ý)
--   bac         chỉ tác giả đồng ý
--   nhap        chưa ai duyệt
-- Mô hình (vai_tro = 'mo_hinh') không được tính vào tầng nào.

CREATE TABLE log_nhap (
    id           INTEGER PRIMARY KEY,
    loai         TEXT NOT NULL CHECK (loai IN ('train', 'do', 'nhat_ky_sua_nhan', 'ban_va_sua_nhan', 'ban_an_hf')),
    duong_dan    TEXT NOT NULL,
    sha256       TEXT NOT NULL CHECK (length(sha256) = 64),
    so_ban_ghi   INTEGER NOT NULL CHECK (so_ban_ghi >= 0),
    ghi_chu_file TEXT,                                   -- trường ghi_chu nguyên văn của file nguồn (nếu có)
    ngay_nhap    TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (loai, sha256)
);

CREATE TABLE mau (
    id           INTEGER PRIMARY KEY,
    bo           TEXT NOT NULL CHECK (bo IN ('train', 'do', 'ban_an')),
    ma           TEXT NOT NULL,                          -- id trong file nguồn, vd 't001', 'd01', 'dn01'; bản án: doc_name của dataset
    tap          TEXT NOT NULL CHECK (tap IN ('train', 'dev', 'xac_nhan', 'kiem_tra', 'phu', 'test')),
    van_ban      TEXT NOT NULL CHECK (length(trim(van_ban)) > 0),     -- tinh_huong (train), cau_hoi (đo), sự việc ĐÃ CHE đáp án (ban_an)
    hash_van_ban TEXT NOT NULL CHECK (length(hash_van_ban) = 64),     -- sha256 của văn bản đã chuẩn hóa (NFC, gọn khoảng trắng, chữ thường)
    loai         TEXT NOT NULL,
    nguon        TEXT NOT NULL CHECK (nguon IN ('claude', 'nguoi_dung', 'ban_an')),
    trang_thai   TEXT NOT NULL CHECK (trang_thai IN ('nhap', 'da_duyet')),   -- nguyên văn trường trong file nguồn
    log_nhap_id  INTEGER NOT NULL REFERENCES log_nhap (id),
    UNIQUE (bo, ma),
    CHECK ((bo = 'train' AND tap = 'train') OR (bo = 'do' AND tap NOT IN ('train', 'test')) OR (bo = 'ban_an' AND tap IN ('train', 'test'))),
    CHECK ((bo = 'train' AND loai IN ('don', 'nhieu')) OR (bo IN ('do', 'ban_an') AND loai IN ('don', 'nhieu_dieu')))
);
CREATE INDEX idx_mau_hash ON mau (hash_van_ban);

CREATE TABLE hanh_vi (                                   -- chỉ bộ huấn luyện (bộ đo không tách hành vi)
    id      INTEGER PRIMARY KEY,
    mau_id  INTEGER NOT NULL REFERENCES mau (id) ON DELETE CASCADE,
    thu_tu  INTEGER NOT NULL CHECK (thu_tu >= 1),
    mo_ta   TEXT NOT NULL CHECK (length(trim(mo_ta)) > 0),
    UNIQUE (mau_id, thu_tu)
);

CREATE TABLE nhan_dieu (
    id               INTEGER PRIMARY KEY,
    mau_id           INTEGER NOT NULL REFERENCES mau (id) ON DELETE CASCADE,
    hanh_vi_id       INTEGER REFERENCES hanh_vi (id) ON DELETE CASCADE,   -- NULL ở bộ đo
    nhom             INTEGER NOT NULL CHECK (nhom >= 1),
    thu_tu           INTEGER NOT NULL CHECK (thu_tu >= 1),                -- thứ tự trong danh sách gốc (để xuất lại đúng)
    van_ban_so_hieu  TEXT NOT NULL DEFAULT '100/2015/QH13',               -- bộ luật mà số Điều trỏ tới
    dieu             TEXT NOT NULL CHECK (length(dieu) > 0),              -- 'dieu' ở dạng chuỗi: '173', '173a'
    khoan            TEXT,                                                -- để trống: nhãn hiện tại chỉ có mức Điều
    diem             TEXT,
    hash_dieu        TEXT,                                                -- băm nội dung Điều lúc đối chiếu với kho luật
    ngay_doi_chieu   TEXT CHECK (ngay_doi_chieu IS NULL OR date(julianday(ngay_doi_chieu)) IS ngay_doi_chieu),
    UNIQUE (mau_id, nhom, dieu)
);

CREATE TABLE lich_su_nhan (                              -- CHỈ GHI THÊM
    id            INTEGER PRIMARY KEY,
    mau_id        INTEGER NOT NULL REFERENCES mau (id),
    nhom_xu_ly    TEXT NOT NULL CHECK (nhom_xu_ly IN ('ap_dung_dung', 'ap_co_chinh', 'khong_ap')),
    nhom_ban_va   TEXT CHECK (nhom_ban_va IN ('A', 'B', 'C', 'D')),       -- nhóm trong bản vá: A sai Điều, B thiếu yếu tố, C không nhất quán, D mơ hồ
    hanh_dong     TEXT,                                                   -- ĐỔI NHÃN / SỬA ĐỀ / THÊM HV / BỎ HV ...
    muc_chac      TEXT CHECK (muc_chac IN ('Cao', 'TB', 'KC')),           -- KC = người soạn bản vá ghi là cần kiểm chứng văn bản luật
    ban_va        TEXT,
    da_lam        TEXT,
    can_cu        TEXT,
    nhan_truoc    TEXT,                                                   -- chỉ có khi nhật ký ghi rõ «nhãn `A` → `B`»
    nhan_sau      TEXT,
    nguoi_de_xuat TEXT NOT NULL,
    nguoi_quyet   TEXT NOT NULL,
    ngay          TEXT NOT NULL CHECK (date(julianday(ngay)) IS ngay),
    nguon_ban_va  TEXT NOT NULL,
    log_nhap_id   INTEGER NOT NULL REFERENCES log_nhap (id),
    UNIQUE (mau_id, nguon_ban_va)
);

CREATE TABLE duyet (                                     -- CHỈ GHI THÊM
    id       INTEGER PRIMARY KEY,
    mau_id   INTEGER NOT NULL REFERENCES mau (id),
    nguoi    TEXT NOT NULL,
    vai_tro  TEXT NOT NULL CHECK (vai_tro IN ('tac_gia', 'sinh_vien_luat', 'nguoi_phap_ly', 'toa_an', 'mo_hinh')),
    ket_qua  TEXT NOT NULL CHECK (ket_qua IN ('dong_y', 'sua', 'tu_choi')),
    ngay     TEXT CHECK (ngay IS NULL OR date(julianday(ngay)) IS ngay),
    suy_ra   INTEGER NOT NULL DEFAULT 0 CHECK (suy_ra IN (0, 1)),         -- 1: suy ra, chưa có bản ghi duyệt riêng: từ trường trang_thai
                                                                          --    của file nguồn, hoặc (bo = 'ban_an') từ chính bản án
    ghi_chu  TEXT,
    UNIQUE (mau_id, nguoi, vai_tro)
);

CREATE TABLE ban_an_meta (                               -- chỉ bộ 'ban_an': thông tin bản án gốc (không có tên người)
    mau_id             INTEGER PRIMARY KEY REFERENCES mau (id) ON DELETE CASCADE,
    ma_goc             TEXT NOT NULL UNIQUE,                 -- doc_name trong dataset (vd 'TAND192119')
    so_ban_an          TEXT,                                 -- vd '12/2025/HS-PT', do bộ tách đọc
    cap                TEXT NOT NULL CHECK (cap IN ('so_tham', 'phuc_tham', 'giam_doc_tham', 'tai_tham', 'khong_ro')),  -- bộ tách đọc từ số bản án
    cap_dataset        TEXT,                                 -- instance_level của dataset: chỉ để đối chiếu, KHÔNG dùng (sai ở nhiều văn bản)
    ngay_ban_an        TEXT CHECK (ngay_ban_an IS NULL OR date(julianday(ngay_ban_an)) IS ngay_ban_an),
    toa_an             TEXT,
    nguon_nhan         TEXT NOT NULL CHECK (nguon_nhan IN ('quyet_dinh', 'so_tham_trich', 'quyet_dinh_cap_tren', 'ket_hop')),
    so_tham_tham_chieu TEXT,                                 -- số bản án sơ thẩm được trích (để gom các bản án cùng vụ)
    nhom_vu            TEXT NOT NULL,                        -- bản án cùng nhom_vu luôn cùng tap
    toi_danh           TEXT NOT NULL DEFAULT '[]',           -- JSON: tội danh trong ngoặc kép ở phần nhãn
    da_che             TEXT NOT NULL DEFAULT '{}',           -- JSON: số chỗ đã che theo loại
    ten_toi_trong_loi_ke INTEGER NOT NULL DEFAULT 0 CHECK (ten_toi_trong_loi_ke >= 0)   -- tên tội còn trong lời kể (gợi ý mềm, không che)
);

CREATE TRIGGER lich_su_nhan_khong_sua BEFORE UPDATE ON lich_su_nhan
BEGIN SELECT RAISE(ABORT, 'lich_su_nhan chỉ được ghi thêm'); END;
CREATE TRIGGER lich_su_nhan_khong_xoa BEFORE DELETE ON lich_su_nhan
BEGIN SELECT RAISE(ABORT, 'lich_su_nhan chỉ được ghi thêm'); END;
CREATE TRIGGER duyet_khong_sua BEFORE UPDATE ON duyet
BEGIN SELECT RAISE(ABORT, 'duyet chỉ được ghi thêm'); END;
CREATE TRIGGER duyet_khong_xoa BEFORE DELETE ON duyet
BEGIN SELECT RAISE(ABORT, 'duyet chỉ được ghi thêm'); END;

CREATE VIEW v_tin_cay AS
WITH tong AS (
    SELECT mau_id,
           SUM(ket_qua = 'dong_y' AND vai_tro IN ('toa_an', 'nguoi_phap_ly'))                    AS chuyen_mon_dong_y,
           COUNT(DISTINCT CASE WHEN ket_qua = 'dong_y' AND vai_tro = 'sinh_vien_luat' THEN nguoi END) AS sv_dong_y,
           SUM(ket_qua <> 'dong_y' AND vai_tro IN ('toa_an', 'nguoi_phap_ly', 'sinh_vien_luat')) AS phan_doi,
           SUM(ket_qua = 'dong_y' AND vai_tro = 'tac_gia')                                       AS tac_gia_dong_y
    FROM duyet
    GROUP BY mau_id
)
SELECT m.id AS mau_id, m.bo, m.ma, m.tap, m.nguon,
       CASE
           WHEN COALESCE(t.phan_doi, 0) > 0 THEN 'tranh_chap'
           WHEN COALESCE(t.chuyen_mon_dong_y, 0) >= 1 OR COALESCE(t.sv_dong_y, 0) >= 2 THEN 'vang'
           WHEN COALESCE(t.tac_gia_dong_y, 0) >= 1 THEN 'bac'
           ELSE 'nhap'
       END AS tang
FROM mau m
LEFT JOIN tong t ON t.mau_id = m.id;

CREATE VIEW v_trung_van_ban AS                            -- văn bản bộ huấn luyện trùng nguyên văn một câu của bộ đo (rò rỉ cứng)
SELECT a.id AS train_id, a.ma AS ma_train, b.id AS do_id, b.ma AS ma_do, b.tap
FROM mau a
JOIN mau b ON b.hash_van_ban = a.hash_van_ban AND b.bo = 'do'
WHERE a.bo = 'train';

CREATE VIEW v_trung_ban_an AS                             -- bản án trùng nguyên văn một mẫu khác (bộ khác, hoặc tap khác của bộ ban_an)
SELECT a.id AS ban_an_id, a.ma AS ma_ban_an, a.tap AS tap_ban_an, b.id AS khac_id, b.bo AS bo_khac, b.ma AS ma_khac, b.tap AS tap_khac
FROM mau a
JOIN mau b ON b.hash_van_ban = a.hash_van_ban AND b.id <> a.id AND (b.bo <> 'ban_an' OR b.tap <> a.tap)
WHERE a.bo = 'ban_an' AND (b.bo <> 'ban_an' OR a.id < b.id);
