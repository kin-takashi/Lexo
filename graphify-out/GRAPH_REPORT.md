# Graph Report - lexo_g  (2026-10-30)

## Corpus Check
- 156 files · ~188,119 words
- Verdict: corpus is large enough that graph structure adds value.
- Unclassified: 6 file(s) not represented in the graph (top: .ipynb 6)

## Summary
- 2686 nodes · 8215 edges · 102 communities (80 shown, 22 thin omitted)
- Extraction: 95% EXTRACTED · 5% INFERRED · 0% AMBIGUOUS · INFERRED: 396 edges (avg confidence: 0.89)
- Token cost: 0 input · 0 output

## Community Hubs (Navigation)
- Script chung (chỉ mục, đánh giá)
- Tải và lọc dữ liệu cbba (BLHS)
- Chẩn đoán câu hỏi và vector
- Xử lý bản án án lệ (anle_hf)
- Gán nhãn và che bản án cbba
- Sinh câu hỏi bằng LLM
- Tách hành vi (LLM)
- Tách bản án thành bốn phần
- Chọn mẫu cbba cho Kaggle V3
- Nạp và duyệt luật gốc
- Parse văn bản luật gốc
- Tập train và kiểm tra hợp lệ
- Đo bản án (do_ban_an) và embedder
- Agent: trả lời và so sánh
- Chọn Điều từ ứng viên
- Hiệu lực văn bản và hoãn hiệu lực
- Agent: công cụ tra theo ngày
- Agent: hỏi đáp
- Dựng lại bộ luật từ lệnh
- Chunk và chỉ mục tìm kiếm
- Trích lệnh bằng regex và tham chiếu
- Parse và kiểm luật sửa đổi
- Duyệt và áp lệnh sửa đổi
- Đóng gói Kaggle V2
- Test dựng lại bộ luật
- Đóng gói cbba Kaggle V3
- Test schema SQLite
- Chấm tìm đủ và so với chuẩn
- Trình bày Điều và diff HTML
- Phân loại ý định hỏi
- So với chuẩn (so_voi_chuan)
- Kho dữ liệu du_lieu.sqlite
- Test parse luật gốc
- Giao diện duyệt luật gốc
- Xuất bộ luật
- Áp đoạn chữ sửa đổi
- Nhập dữ liệu vào kho
- Xử lý cbba (CLI)
- Hiệu đính và đề xuất sửa
- Test hiệu đính
- Test agent nhiều luật
- Tra cứu CLI và lưu ý hiệu lực
- Test chọn Điều
- Sinh notebook V3 và test CLI
- Phân tích kết quả cbba
- Khởi tạo kho và nạp lệnh
- Xếp lại bằng reranker
- Test đóng gói cbba
- Tra cứu lịch sử Điều
- Giao diện tra cứu và hiển thị
- Duyệt luật gốc (review app)
- Chọn mẫu học
- Kiểm luật gốc (validate)
- Test parse luật sửa đổi
- Test trích lệnh luật sửa đổi
- Án lệ HF: xử lý và tách tập
- Đối chiếu VBHN (script)
- Test bộ câu hỏi
- Test đối chiếu VBHN
- Test giao diện tra cứu
- Kaggle: kết hợp C0-L và test phân tích
- CLI hỏi đáp
- Nạp luật sửa đổi
- Xuất bộ luật và đối chiếu
- Đối chiếu VBHN (lõi)
- Xuất nhập train và bộ đo
- Truy vấn cây Điều
- Trích VBHN từ PDF
- Kiểm tra môi trường
- Tương đồng vector
- Nhập tất cả bản án
- Reranker BGE
- Kết quả trích lệnh
- Xếp lại bằng LLM
- Tổng hợp số liệu Kaggle
- Test CLI nhiều luật
- Test khung dự án
- Tách bản án (CLI)
- Kiểm tra Ollama
- Sinh notebook Kaggle V2
- Báo cáo dựng lại
- Lịch sử sửa đổi Điều
- Nguồn và chuỗi lệnh
- Kết quả so sánh VBHN
- Lập đề xuất sửa VBHN
- So sánh theo mốc
- Bộ nhớ tạm embedding
- Khóa số liệu dữ liệu
- Lỗi dựng lại
- Sửa chữ nhỏ
- Test tăng tin cậy
- Fixture lịch sử

## God Nodes (most connected - your core abstractions)
1. `rebuild()` - 79 edges
2. `CongCu` - 54 edges
3. `main()` - 51 edges
4. `Agent` - 51 edges
5. `HashEmbedder` - 49 edges
6. `doc_bo()` - 47 edges
7. `open_index()` - 44 edges
8. `P()` - 43 edges
9. `connect()` - 42 edges
10. `fmt_date()` - 40 edges

## Surprising Connections (you probably didn't know these)
- `nap()` --indirect_call--> `lo()`  [INFERRED]
  src/index/so_voi_chuan.py → tests/test_cbba_nhan.py
- `main()` --uses--> `RebuildError`  [INFERRED]
  scripts/apply_commands.py → src/apply/rebuild.py
- `main()` --uses--> `RebuildError`  [INFERRED]
  scripts/doi_chieu_vbhn.py → src/apply/rebuild.py
- `main()` --uses--> `EmbedError`  [INFERRED]
  scripts/dong_goi_cbba_kaggle.py → src/index/embedder.py
- `main()` --uses--> `EmbedError`  [INFERRED]
  scripts/dong_goi_kaggle.py → src/index/embedder.py

## Import Cycles
- None detected.

## Communities (102 total, 22 thin omitted)

### Community 0 - "Script chung (chỉ mục, đánh giá)"
Cohesion: 0.05
Nodes (49): main(), mo_chi_doc(), phut(), main(), hang_dap_an(), main(), doc_du_doan(), dong_bang() (+41 more)

### Community 1 - "Tải và lọc dữ liệu cbba (BLHS)"
Cohesion: 0.04
Nodes (69): doc_nhe(), _duong_dan(), _file_loc(), kiem_tra_dau_ra(), _loc_con_dung_duoc(), main(), _bam(), ban_ghi_tu_hang() (+61 more)

### Community 2 - "Chẩn đoán câu hỏi và vector"
Cohesion: 0.07
Nodes (46): _hang_dieu(), hang_dieu_cua_cau_hoi(), luu_cau_hoi(), _cau_hoi_co_vec(), _chi_so(), chuan_chu(), _co_trung(), ket_luan() (+38 more)

### Community 3 - "Xử lý bản án án lệ (anle_hf)"
Cohesion: 0.05
Nodes (54): xu_ly_tat_ca(), bo_cau_phan_quyet(), che_dap_an(), _che_toi_viet_hoa(), chia_tap(), chuan_van(), con_lo(), _cot() (+46 more)

### Community 4 - "Gán nhãn và che bản án cbba"
Cohesion: 0.06
Nodes (52): bo_cau_phan_quyet_con_sot(), bo_dau_trang(), cat_phan_vks(), cat_truoc_truy_to(), khoi_tao(), kiem_lo_them(), loai_neu_lo(), thong_ke() (+44 more)

### Community 5 - "Sinh câu hỏi bằng LLM"
Cohesion: 0.06
Nodes (33): main(), phut(), can_sinh(), chon_mo_hinh(), chon_trai_deu(), dieu_dap_an(), doc_ket_qua(), don_cau_hoi_mo_coi() (+25 more)

### Community 6 - "Tách hành vi (LLM)"
Cohesion: 0.06
Nodes (34): ghi_nguyen_tu(), main(), doc_bo(), _bam(), chon_vi_du(), hop(), dong_ra(), dung_tin_nhan() (+26 more)

### Community 7 - "Tách bản án thành bốn phần"
Cohesion: 0.08
Nodes (40): _gon(), bo_dau(), _cap_tu_hau_to(), cat_noi_dung(), chuan_hoa(), ket_qua_cap_tren(), khoa(), la_tieu_de() (+32 more)

### Community 8 - "Chọn mẫu cbba cho Kaggle V3"
Cohesion: 0.06
Nodes (30): bam(), CbbaKaggleError, ChiMucGanTrung, chon_dev(), chon_so_bo(), chon_train(), do_chua(), doc_meta() (+22 more)

### Community 9 - "Nạp và duyệt luật gốc"
Cohesion: 0.10
Nodes (33): ingest_base_law(), IngestError, _insert_nodes(), stage_base_law(), extract_docx(), approve(), new_review(), save_review() (+25 more)

### Community 10 - "Parse văn bản luật gốc"
Cohesion: 0.07
Nodes (21): ExtractedText, _append_text(), _extract_meta(), _is_title_line(), _match_khoan_diem(), _match_structural(), _open(), parse_body() (+13 more)

### Community 11 - "Tập train và kiểm tra hợp lệ"
Cohesion: 0.10
Nodes (27): _ghi_jsonl(), main(), _sha(), _tom_tat(), main(), main(), cum_trung(), dieu_da_phu() (+19 more)

### Community 12 - "Đo bản án (do_ban_an) và embedder"
Cohesion: 0.06
Nodes (20): binom_hai_phia(), chay_A(), chay_ket_hop(), doc_jsonl(), DoError, dong_bang(), hoi_lap(), main() (+12 more)

### Community 13 - "Agent: trả lời và so sánh"
Cohesion: 0.09
Nodes (5): HanhVi, _them(), TraLoi, YDinh, test_lay_dieu_duong_tat()

### Community 14 - "Chọn Điều từ ứng viên"
Cohesion: 0.07
Nodes (29): tieu_de(), _bam(), bang_recall(), chia_dev(), chon_k(), ChonError, dich_chon(), doc_chon() (+21 more)

### Community 15 - "Hiệu lực văn bản và hoãn hiệu lực"
Cohesion: 0.10
Nodes (24): _cua_so(), _in_bang(), main(), _tom_tat(), dat_het_hieu_luc(), ghi_hoan_hieu_luc(), HieuLucError, _iso() (+16 more)

### Community 16 - "Agent: công cụ tra theo ngày"
Cohesion: 0.08
Nodes (3): CongCu, LuatTaiNgay, test_cau_hinh_luat_chua_nap_ghi_de_duoc()

### Community 17 - "Agent: hỏi đáp"
Cohesion: 0.10
Nodes (30): Agent, ag(), nap_quan_he(), tao(), test_canh_bao_lenh_chua_duyet(), test_dieu_da_bai_bo_giai_thich_ly_do(), test_khong_co_chi_muc(), test_lich_su() (+22 more)

### Community 18 - "Dựng lại bộ luật từ lệnh"
Cohesion: 0.15
Nodes (30): _alloc_thu_tu(), _base_date(), _close_subtree(), _close_version(), CommandError, _create_subtree(), _Ctx, _dong_het_hieu_luc() (+22 more)

### Community 19 - "Chunk và chỉ mục tìm kiếm"
Cohesion: 0.09
Nodes (25): NhoTam, _kiem_tra_chi_muc_cu(), _mo_chi_doc(), build_chunks(), dau_dieu(), _chu(), Chunk, _lead() (+17 more)

### Community 20 - "Trích lệnh bằng regex và tham chiếu"
Cohesion: 0.11
Nodes (24): _build(), context_path(), find_groups(), path_to_json(), RefGroup, resolve_targets(), paths_of(), Target (+16 more)

### Community 21 - "Parse và kiểm luật sửa đổi"
Cohesion: 0.09
Nodes (19): _quote_text(), AmendingLaw, AmendingMeta, Clause, _clause_from(), DieuSuaDoi, fix_stray_open_quotes(), Item (+11 more)

### Community 22 - "Duyệt và áp lệnh sửa đổi"
Cohesion: 0.12
Nodes (26): main(), _print_report(), ApproveError, bao_cao_markdown(), _cut(), duyet_theo_lo(), _one(), tong_quan() (+18 more)

### Community 23 - "Đóng gói Kaggle V2"
Cohesion: 0.09
Nodes (23): in_bang_recall(), main(), NhoTam, readme_do(), readme_hoc(), bam_chu(), chep_ma_nguon(), doc_jsonl() (+15 more)

### Community 24 - "Test dựng lại bộ luật"
Cohesion: 0.20
Nodes (30): rebuild(), Env, path(), P(), test_bai_bo_chuong_bai_bo_ca_cay(), test_bai_bo_mot_khoan(), test_bo_sung_dieu_moi_co_khoan_va_diem(), test_bo_sung_khoan_sau_khoan_xen_giua_thu_tu() (+22 more)

### Community 25 - "Đóng gói cbba Kaggle V3"
Cohesion: 0.08
Nodes (15): cosine(), embed(), main(), doc_tat_ca_meta(), _duong_dan(), ghi_bao_cao(), in_bang_recall(), main() (+7 more)

### Community 26 - "Test schema SQLite"
Cohesion: 0.15
Nodes (30): add_don_vi(), add_lenh(), add_log(), add_pb(), add_van_ban(), test_adjacent_versions_and_other_nodes_are_allowed(), test_as_of_query_handles_open_ended_version(), test_close_then_insert_works_and_extending_is_rejected() (+22 more)

### Community 27 - "Chấm tìm đủ và so với chuẩn"
Cohesion: 0.10
Nodes (24): diem(), doc_file(), main(), theo_cot(), tim_du_cua(), nap_danh_gia_nhieu(), pc(), cham() (+16 more)

### Community 28 - "Trình bày Điều và diff HTML"
Cohesion: 0.10
Nodes (21): cua_so_hieu_luc(), diff_html(), _ghi(), ghi_chu_nguon(), _gop_dong(), loc_khoan(), markdown_dieu(), ngay_vn() (+13 more)

### Community 29 - "Phân loại ý định hỏi"
Cohesion: 0.11
Nodes (22): bo_dau(), chuan_hoa(), _co(), _hop_le(), Moc, _ngoai_linh_vuc(), phan_loai(), tim_moc() (+14 more)

### Community 30 - "So với chuẩn (so_voi_chuan)"
Cohesion: 0.11
Nodes (20): boot_hieu(), doc_tach(), _ghep_tham(), ghep_toi_uu(), so_sanh(), so_voi_cac_chuan(), tong_hop(), tran_chuan() (+12 more)

### Community 31 - "Kho dữ liệu du_lieu.sqlite"
Cohesion: 0.11
Nodes (22): connect(), init_db(), ba(), db(), db_ba(), db_that(), file_ban_an(), ghi() (+14 more)

### Community 32 - "Test parse luật gốc"
Cohesion: 0.13
Nodes (28): parse_base_law(), codes(), make(), make_cu(), test_clean_law_has_no_errors_or_warnings(), test_diem_co_dau_cach_truoc_ngoac(), test_impossible_effective_date_is_not_read(), test_inline_merged_points_are_split_only_for_next_letter() (+20 more)

### Community 33 - "Giao diện duyệt luật gốc"
Cohesion: 0.14
Nodes (19): ParsedLaw, line_of(), load_doc(), dieu_at_line(), dieu_matches_source(), dieu_spans(), node_to_text(), path_to() (+11 more)

### Community 34 - "Xuất bộ luật"
Cohesion: 0.11
Nodes (23): nhan_duyet(), BoLuat, _doan(), dung_bo_luat(), walk(), _ghi_chu_dieu(), walk(), _gioi_thieu() (+15 more)

### Community 35 - "Áp đoạn chữ sửa đổi"
Cohesion: 0.13
Nodes (22): _apply_at_start(), _apply_exact(), apply_phrase(), _cap(), _is_word(), phrase_regex(), _remove(), _sep() (+14 more)

### Community 36 - "Nhập dữ liệu vào kho"
Cohesion: 0.15
Nodes (17): _cac_o(), chuan_van(), doc_ban_va(), doc_nhat_ky(), _ghi_duyet_tac_gia(), _ghi_log(), hash_van(), kiem_tra_ban_an() (+9 more)

### Community 37 - "Xử lý cbba (CLI)"
Cohesion: 0.10
Nodes (17): _duong_dan(), main(), kho(), _bam(), chon_ma(), doc_dong(), doc_tap(), ghi_jsonl() (+9 more)

### Community 38 - "Hiệu đính và đề xuất sửa"
Cohesion: 0.10
Nodes (16): cmd_nap(), ap_dung(), BaoCaoHieuDinh, dieu_ap_dung(), KetQuaQuyTac, khoa_nut(), key(), khoi_phuc() (+8 more)

### Community 39 - "Test hiệu đính"
Cohesion: 0.16
Nodes (20): duyet(), HieuDinhError, luu_de_xuat(), de_xuat(), sua_khoan_3_1(), test_ap_dung_len_moi_phien_ban_giu_ban_goc(), test_chua_duyet_hoac_bi_tu_choi_thi_khong_ap(), test_dieu_ap_dung() (+12 more)

### Community 40 - "Test agent nhiều luật"
Cohesion: 0.08
Nodes (8): fmt_hom_nay(), hai(), mot(), test_ban_goc_la_nguyen_van_thong_qua_du_chua_tung_ap_dung(), test_chi_muc_cu_khong_bao_nham_khi_khop(), test_phan_loai_nam_bo_luat_da_biet(), test_so_sanh_ban_goc_voi_hien_hanh(), test_tim_mo_ta_chon_bo_luat_theo_ngay_va_chi_muc()

### Community 41 - "Tra cứu CLI và lưu ý hiệu lực"
Cohesion: 0.13
Nodes (13): main(), dieu_khoan_lien_quan(), dieu_status(), hieu_dinh_cho_duyet_dieu(), luu_y_hieu_luc(), parse_reference(), so_hieu_dinh_cho_duyet(), so_lenh_cho_duyet() (+5 more)

### Community 42 - "Test chọn Điều"
Cohesion: 0.11
Nodes (18): cat_su_viec(), chia_doan(), _ban_an_gia(), _chay(), _chi_muc_nho(), _goi_do_gia(), test_binom_hai_phia(), test_cat_su_viec_giu_dau_cuoi_va_xuong_dong() (+10 more)

### Community 43 - "Sinh notebook V3 và test CLI"
Cohesion: 0.18
Nodes (16): ap_dung(), _dong(), main(), sinh(), ThayError, dung(), ghi_vbhn(), run() (+8 more)

### Community 44 - "Phân tích kết quả cbba"
Cohesion: 0.13
Nodes (16): bang_cap(), bang_nhom(), bang_tong(), bao_cao(), doc_jsonl(), hang_truy_hoi(), khoang_hieu(), main() (+8 more)

### Community 45 - "Khởi tạo kho và nạp lệnh"
Cohesion: 0.14
Nodes (10): main(), main(), db_path_from_config(), main(), raw_dir(), backup_and_remove(), connect(), init_db() (+2 more)

### Community 46 - "Xếp lại bằng reranker"
Cohesion: 0.15
Nodes (17): chi_so(), hang_dap_an(), ket_luan_xep_lai(), kiem_dinh_dau(), quet_w(), rut_gon(), xep_lai_top(), z() (+9 more)

### Community 47 - "Test đóng gói cbba"
Cohesion: 0.14
Nodes (16): _anle(), _chay(), _dong(), _du_lieu_gia(), _meta(), moi_truong(), _nb_v2(), test_chon_so_bo_dev_nguyen_nhom_va_hoc_khong_giao_dev() (+8 more)

### Community 48 - "Tra cứu lịch sử Điều"
Cohesion: 0.15
Nodes (18): find_van_ban(), get_dieu(), render(), so_sanh(), tom_tat_nguon(), test_lookup_exact_and_as_of(), test_lookup_ignores_versions_outside_date(), test_real_all_dieu_numbers_present_including_317() (+10 more)

### Community 49 - "Giao diện tra cứu và hiển thị"
Cohesion: 0.18
Nodes (15): DieuDayDu, DieuKetQua, md_thoat(), fmt_date(), dat_cau(), het_ngay(), hien_thi(), lay_agent() (+7 more)

### Community 50 - "Duyệt luật gốc (review app)"
Cohesion: 0.18
Nodes (14): Staged, collect(), blocking_problems(), file_sha256(), flag_key(), load_parsed(), load_review(), save_parsed() (+6 more)

### Community 51 - "Chọn mẫu học"
Cohesion: 0.17
Nodes (12): mau_trung(), to_hop_bo_do(), to_hop_dieu(), xep_hang(), cau(), mau(), _tap(), test_mau_trung_chi_theo_cau_nhieu_dieu_va_bat_ke_thu_tu() (+4 more)

### Community 52 - "Kiểm luật gốc (validate)"
Cohesion: 0.20
Nodes (16): main(), _allowed_next(), _check_children(), _check_int_sequence(), _check_points(), _check_sequence(), Flag, _fmt() (+8 more)

### Community 53 - "Test parse luật sửa đổi"
Cohesion: 0.21
Nodes (17): has_errors(), validate_amending_law(), codes(), parse(), test_bat_dau_ngoac_khong_can_bang(), test_bat_muc_nhay_so(), test_bat_thieu_khoi_trich_dan(), test_bat_thieu_ngay() (+9 more)

### Community 54 - "Test trích lệnh luật sửa đổi"
Cohesion: 0.19
Nodes (18): extract_commands(), scan_structure(), parse(), test_dau_dong_go_nham_o_cho_mo_ngoac_duoc_doc_la_mo_ngoac_va_co_canh_bao(), test_dieu_hieu_luc_khong_tieu_de_van_duoc_nhan_ra(), test_dong_nhac_lai_so_lenh_trong_khoi_khong_bi_cat_nham(), test_ket_qua_trich_lenh_ghi_duoc_ra_json(), test_khoan_dieu_duoc_sua_doi_dang_bi_dong_va_thanh_cum_tu() (+10 more)

### Community 55 - "Án lệ HF: xử lý và tách tập"
Cohesion: 0.14
Nodes (12): _duong_dan(), _ghi_jsonl(), main(), thong_ke(), doc_parquet(), sha256_file(), ten_toi_tu_luat(), tim_parquet() (+4 more)

### Community 56 - "Đối chiếu VBHN (script)"
Cohesion: 0.20
Nodes (16): _cho_duyet_canh_bao(), cmd_danh_sach(), cmd_de_xuat(), cmd_duyet(), cmd_so_sanh(), _cut(), _in_hieu_dinh(), _luu_json() (+8 more)

### Community 57 - "Test bộ câu hỏi"
Cohesion: 0.18
Nodes (14): bang_xem_duyet(), kiem_tra_hop_le(), _ten_dieu(), ghi(), mot(), test_bang_xem_duyet_cau_nhieu_dieu_noi_bang_dau_cong(), test_bang_xem_duyet_chia_tap_va_thoat_dau_gach(), test_doc_bo_loc_theo_tap_va_loai() (+6 more)

### Community 58 - "Test đối chiếu VBHN"
Cohesion: 0.22
Nodes (14): ap_dung_sua(), de_xuat_sua(), apply_all(), test_ap_dung_sua_mo_ho_hoac_khong_co(), test_de_xuat_sua_chen_cuoi_van_truoc_dau_cau_ket_thuc(), test_de_xuat_sua_chen_sau_dau_cau_va_viet_hoa_tu_sau(), test_de_xuat_sua_chen_truoc_dau_cau(), test_de_xuat_sua_chi_khac_trinh_bay_thi_khong_sua() (+6 more)

### Community 59 - "Test giao diện tra cứu"
Cohesion: 0.25
Nodes (13): chay(), hoi(), kho_tep(), md(), test_goi_y_chay_cau_ke_tiep(), test_khoi_dong_hien_vi_du_va_trang_thai(), test_loi_bat_ngo_khong_lam_trang_trang(), test_ngay_xem_o_thanh_ben() (+5 more)

### Community 60 - "Kaggle: kết hợp C0-L và test phân tích"
Cohesion: 0.16
Nodes (9): du_dev(), ket_hop(), tim_ket_qua(), _dong(), _mau(), test_bao_cao_day_du_va_danh_dau_chua_du(), test_chay_script_ghi_phan_tich(), test_hang_truy_hoi_va_vi_mo_theo_dieu() (+1 more)

### Community 61 - "CLI hỏi đáp"
Cohesion: 0.15
Nodes (6): main(), hoi(), MocLichSu, SoSanh, thanh_van_ban(), KhoLoi

### Community 62 - "Nạp luật sửa đổi"
Cohesion: 0.19
Nodes (10): main(), amending_scope(), load_amending(), save_amending(), stage_amending_law(), StagedAmending, slugify_so_hieu(), format_report() (+2 more)

### Community 63 - "Xuất bộ luật và đối chiếu"
Cohesion: 0.17
Nodes (13): doi_chieu(), main(), _brief_diff(), compare(), Diff, nodes(), test_compare_cac_loai_sai_khac(), test_compare_giong_het() (+5 more)

### Community 64 - "Đối chiếu VBHN (lõi)"
Cohesion: 0.18
Nodes (11): fold(), Item, items_from_db(), items_from_nodes(), walk(), _keys(), _norm(), _toks() (+3 more)

### Community 65 - "Xuất nhập train và bộ đo"
Cohesion: 0.17
Nodes (12): _in_thong_ke(), main(), kiem_tra_toan_ven(), thong_ke(), xuat_do(), xuat_train(), doc_tho(), test_ban_an_nhap_nhan_tang_vang_va_meta() (+4 more)

### Community 66 - "Truy vấn cây Điều"
Cohesion: 0.24
Nodes (8): get_cay(), _load_children(), _note(), _note_hieu_dinh(), _Prov, _select(), UnitView, _view()

### Community 67 - "Trích VBHN từ PDF"
Cohesion: 0.19
Nodes (7): cmd_trich(), extract_vbhn(), _page_lines(), VbhnText, tao_pdf(), test_extract_vbhn_pdf_gia_lap(), test_vbhn_text_to_dict_from_dict_khu_hoi()

### Community 68 - "Kiểm tra môi trường"
Cohesion: 0.41
Nodes (10): check_extension_loading(), check_files(), check_fts5(), check_gpu(), check_ollama(), check_python(), check_sqlite(), check_sqlite_vec() (+2 more)

### Community 69 - "Tương đồng vector"
Cohesion: 0.23
Nodes (8): am_tiet(), tuong_dong_vec(), chuan_hoa(), nap(), td(), bo_tien_to(), test_tuong_dong_vec_cosine_va_nap_theo_lo(), test_bo_tien_to_viet_hoa_chu_dau()

### Community 70 - "Nhập tất cả bản án"
Cohesion: 0.22
Nodes (7): doc_ban_an_de_doi_chieu(), nhap_tat_ca(), xuat_ban_an(), test_ban_an_that_nhap_duoc_va_khop(), test_ban_an_xuat_nguoc_khop_va_nhap_lai_khong_doi(), test_file_nguon_doi_phai_reset(), test_nhap_lai_cung_file_khong_nhan_doi()

### Community 71 - "Reranker BGE"
Cohesion: 0.22
Nodes (5): BgeReranker, XepLaiError, test_xep_lai_doi_thu_tu_va_hong_thi_giu_nguyen(), cham(), test_bge_thieu_mo_hinh_bao_cach_tai()

### Community 72 - "Kết quả trích lệnh"
Cohesion: 0.29
Nodes (4): ExtractionResult, load_extraction(), real_blhs_conn(), real_pipeline()

### Community 73 - "Xếp lại bằng LLM"
Cohesion: 0.22
Nodes (4): LLMXepLai, LLMThu, test_llm_cham_hai_luot_dao_thu_tu_va_trung_binh(), test_llm_tra_sai_dinh_dang_thi_bao_loi_ro()

### Community 75 - "Test CLI nhiều luật"
Cohesion: 0.33
Nodes (6): db(), run(), test_khong_nem_nam_chon_bo_luat_theo_ngay_xem(), test_khong_nem_nam_va_khong_ngay_dung_bo_luat_hom_nay(), test_neu_nam_thi_dung_dung_bo_do_ke_ca_khi_ngay_o_ngoai(), test_ngay_khong_thuoc_bo_luat_nao_thi_van_doi_nam()

### Community 77 - "Tách bản án (CLI)"
Cohesion: 0.32
Nodes (3): _danh_sach(), main(), doc_file()

### Community 78 - "Kiểm tra Ollama"
Cohesion: 0.25
Nodes (3): cau_hinh_agent(), co_model(), kiem_tra_ollama()

### Community 79 - "Sinh notebook Kaggle V2"
Cohesion: 0.43
Nodes (5): code(), _dong(), main(), md(), nb()

### Community 81 - "Lịch sử sửa đổi Điều"
Cohesion: 0.29
Nodes (3): lich_su_dieu(), SuKien, test_lich_su_dieu()

### Community 84 - "Lập đề xuất sửa VBHN"
Cohesion: 0.43
Nodes (6): lap_de_xuat(), item(), test_lap_de_xuat_bo_qua_khac_trinh_bay_va_nut_chi_co_mot_ben(), test_lap_de_xuat_can_bang_chung(), test_lap_de_xuat_chi_nut_xac_minh(), test_lap_de_xuat_khong_sua_tu_dong_duoc_thi_khong_de_xuat()

## Knowledge Gaps
- **22 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `CongCu` connect `Agent: công cụ tra theo ngày` to `Script chung (chỉ mục, đánh giá)`, `Chẩn đoán câu hỏi và vector`, `Sinh câu hỏi bằng LLM`, `Tách hành vi (LLM)`, `Reranker BGE`, `Test agent nhiều luật`, `Đo bản án (do_ban_an) và embedder`, `Agent: trả lời và so sánh`, `Kiểm tra Ollama`, `Hiệu lực văn bản và hoãn hiệu lực`, `Agent: hỏi đáp`, `Giao diện tra cứu và hiển thị`, `Chunk và chỉ mục tìm kiếm`, `CLI hỏi đáp`?**
  _High betweenness centrality (0.040) - this node is a cross-community bridge._
- **Are the 2 inferred relationships involving `rebuild()` (e.g. with `.ok()` and `.n_loi()`) actually correct?**
  _`rebuild()` has 2 INFERRED edges - model-reasoned connections that need verification._
- **Should `Script chung (chỉ mục, đánh giá)` be split into smaller, more focused modules?**
  _Cohesion score 0.05378151260504202 - nodes in this community are weakly interconnected._
- **Why does `main()` connect `Đóng gói cbba Kaggle V3` to `Script chung (chỉ mục, đánh giá)`, `Chẩn đoán câu hỏi và vector`, `Chọn mẫu cbba cho Kaggle V3`, `Sinh notebook V3 và test CLI`, `Chọn Điều từ ứng viên`, `Test đóng gói cbba`, `Đóng gói Kaggle V2`?**
  _High betweenness centrality (0.025) - this node is a cross-community bridge._
- **Should `Tải và lọc dữ liệu cbba (BLHS)` be split into smaller, more focused modules?**
  _Cohesion score 0.0380754586362063 - nodes in this community are weakly interconnected._
- **Why does `Agent` connect `Agent: hỏi đáp` to `Test agent nhiều luật`, `Agent: trả lời và so sánh`, `Hiệu lực văn bản và hoãn hiệu lực`, `Agent: công cụ tra theo ngày`, `Giao diện tra cứu và hiển thị`, `So sánh theo mốc`, `Test giao diện tra cứu`, `CLI hỏi đáp`?**
  _High betweenness centrality (0.023) - this node is a cross-community bridge._
- **Should `Chẩn đoán câu hỏi và vector` be split into smaller, more focused modules?**
  _Cohesion score 0.0653417645287564 - nodes in this community are weakly interconnected._