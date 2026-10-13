"""Kiểm tra môi trường cho Lexo. Chạy MỘT LẦN trên máy Windows dùng để phát triển:

    python scripts/check_env.py

Chỉ dùng thư viện chuẩn nên chạy được trước khi cài requirements.txt.
Cho biết: Python đúng phiên bản chưa; sqlite3 có FTS5 và cho load extension không;
sqlite-vec có dùng được không (nếu không, dùng numpy brute-force — mục 6 của kế hoạch v2);
Ollama và GPU có sẵn không. Chỉ đọc: không ghi gì và không in nội dung .env.
"""
from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_counts = {"OK": 0, "THÔNG TIN": 0, "CẢNH BÁO": 0, "LỖI": 0}


def report(level: str, name: str, detail: str = "") -> None:
    _counts[level] += 1
    print(f"[{level}] {name}" + (f" — {detail}" if detail else ""))


def check_python() -> None:
    v = sys.version_info
    text = f"{v.major}.{v.minor}.{v.micro} ({sys.platform})"
    if (v.major, v.minor) == (3, 10):
        report("OK", "Python 3.10.x", text)
    else:
        report("CẢNH BÁO", "Python không phải 3.10.x", text + " — kế hoạch v2 ghim 3.10.x")


def check_sqlite() -> None:
    report("THÔNG TIN", "Thư viện SQLite", sqlite3.sqlite_version)


def check_fts5() -> None:
    conn = sqlite3.connect(":memory:")
    try:
        conn.execute("CREATE VIRTUAL TABLE t USING fts5(x, tokenize='unicode61 remove_diacritics 0')")
    except sqlite3.OperationalError as e:
        report("LỖI", "SQLite không có FTS5", str(e))
        return
    conn.execute("INSERT INTO t(x) VALUES ('trộm cắp tài sản')")
    with_marks = conn.execute("SELECT count(*) FROM t WHERE t MATCH 'trộm'").fetchone()[0]
    no_marks = conn.execute("SELECT count(*) FROM t WHERE t MATCH 'trom'").fetchone()[0]
    if with_marks == 1 and no_marks == 0:
        report("OK", "FTS5 chạy và phân biệt dấu tiếng Việt", "tokenize=unicode61 remove_diacritics 0")
    else:
        report("CẢNH BÁO", "FTS5 chạy nhưng khớp dấu bất thường", f"'trộm'→{with_marks}, 'trom'→{no_marks}")


def check_extension_loading() -> bool:
    conn = sqlite3.connect(":memory:")
    if not hasattr(conn, "enable_load_extension"):
        report("CẢNH BÁO", "sqlite3 của Python này không có enable_load_extension",
               "sqlite-vec sẽ không load được → dùng numpy brute-force")
        return False
    try:
        conn.enable_load_extension(True)
        conn.enable_load_extension(False)
    except (AttributeError, sqlite3.NotSupportedError) as e:
        report("CẢNH BÁO", "sqlite3 không cho load extension", f"{e} → dùng numpy brute-force")
        return False
    report("OK", "sqlite3 cho phép load extension")
    return True


def check_sqlite_vec(can_load: bool) -> None:
    try:
        import sqlite_vec  # type: ignore
    except ImportError:
        report("THÔNG TIN", "Chưa cài sqlite-vec", "pip install sqlite-vec khi tới Bước 4, rồi chạy lại script này")
        return
    if not can_load:
        report("CẢNH BÁO", "Đã cài sqlite-vec nhưng không load được", "sqlite3 không cho load extension")
        return
    conn = sqlite3.connect(":memory:")
    try:
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        conn.enable_load_extension(False)
        version = conn.execute("SELECT vec_version()").fetchone()[0]
        report("OK", "sqlite-vec load được", str(version))
    except Exception as e:  # noqa: BLE001 — muốn thấy mọi lỗi load
        report("CẢNH BÁO", "sqlite-vec không load được", f"{type(e).__name__}: {e} → dùng numpy brute-force")


def check_gpu() -> None:
    exe = shutil.which("nvidia-smi")
    if not exe:
        report("THÔNG TIN", "Không thấy nvidia-smi",
               "coi như máy này không có GPU NVIDIA/CUDA — embedding chạy bằng CPU")
        return
    try:
        out = subprocess.run([exe, "--query-gpu=name,memory.total", "--format=csv,noheader"],
                             capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired) as e:
        report("CẢNH BÁO", "Không chạy được nvidia-smi", str(e))
        return
    line = out.stdout.strip().replace("\n", " | ")
    if out.returncode == 0 and line:
        report("OK", "GPU NVIDIA", line)
    else:
        report("CẢNH BÁO", "nvidia-smi báo lỗi", out.stderr.strip())


def check_ollama() -> None:
    endpoint = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
    if not endpoint.startswith("http"):
        endpoint = "http://" + endpoint
    try:
        with urllib.request.urlopen(endpoint.rstrip("/") + "/api/tags", timeout=3) as resp:
            models = [m.get("name", "?") for m in json.load(resp).get("models", [])]
        report("OK", "Ollama đang chạy", ", ".join(models) or "chưa tải mô hình nào")
    except (urllib.error.URLError, OSError, ValueError) as e:
        report("THÔNG TIN", "Không kết nối được Ollama",
               f"{endpoint} ({e}) — chỉ cần từ Bước 6 hoặc khi thử trích xuất bằng Qwen local")


def check_files() -> None:
    if (ROOT / "config.yaml").is_file():
        report("OK", "Có config.yaml")
    else:
        report("LỖI", "Thiếu config.yaml")
    if (ROOT / ".env").is_file():
        report("OK", "Có .env", "không đọc nội dung")
    else:
        report("THÔNG TIN", "Chưa có .env", "cần từ Bước 2: copy .env.example thành .env rồi điền API key")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"Lexo check_env — thư mục dự án: {ROOT}\n")
    check_python()
    check_sqlite()
    check_fts5()
    can_load = check_extension_loading()
    check_sqlite_vec(can_load)
    check_gpu()
    check_ollama()
    check_files()
    print(f"\nTổng: {_counts['OK']} OK, {_counts['CẢNH BÁO']} cảnh báo, {_counts['LỖI']} lỗi")
    print("Gửi toàn bộ kết quả trên cho Claude để chốt phương án vector search và cỡ mô hình local.")
    return 1 if _counts["LỖI"] else 0


if __name__ == "__main__":
    sys.exit(main())
