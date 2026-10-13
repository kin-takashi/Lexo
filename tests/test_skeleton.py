"""Kiểm tra khung dự án (Bước 0): gói import được, cấu hình không chứa bí mật."""
import importlib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = ["store", "ingest", "parse", "extract", "validate", "review", "apply", "index", "query", "agent"]


@pytest.mark.parametrize("name", PACKAGES)
def test_package_importable(name):
    importlib.import_module(f"src.{name}")


def test_config_has_required_sections_and_no_secret():
    yaml = pytest.importorskip("yaml")
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    for section in ("paths", "llm_extract", "llm_local", "embedding", "vector_store"):
        assert section in cfg, f"config.yaml thiếu mục {section}"
    assert "api_key" not in cfg["llm_extract"], "API key phải nằm trong .env, không nằm trong config.yaml"


def test_gitignore_protects_secrets_and_data():
    lines = {line.strip() for line in (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()}
    assert {".env", "/raw/", "/db/"} <= lines


def test_env_example_has_empty_values():
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("#"):
            key, _, value = line.partition("=")
            assert value.strip() == "", f"{key} trong .env.example phải để trống"
