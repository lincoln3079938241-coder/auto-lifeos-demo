from __future__ import annotations

from pathlib import Path, PurePosixPath

from llm.base import get_provider
from services.experiments import PUBLIC_ROOT


def test_mock_provider_is_forced() -> None:
    provider, note = get_provider()
    assert provider.name == "mock"
    assert "Mock" in note


def test_app_does_not_read_api_credentials() -> None:
    source = (PUBLIC_ROOT / "app.py").read_text(encoding="utf-8").lower()
    forbidden = ["openai_api", "api_key", "secrets.toml", "os.getenv", "dotenv"]
    assert not any(marker in source for marker in forbidden)


def test_public_python_uses_portable_paths() -> None:
    for path in PUBLIC_ROOT.rglob("*.py"):
        if ".git" in path.parts or "__pycache__" in path.parts:
            continue
        source = path.read_text(encoding="utf-8")
        assert "C:" + "\\Users" not in source
        assert "C:" + "/Users" not in source
    assert PurePosixPath("data/synthetic_ab_cases.json").as_posix() == "data/synthetic_ab_cases.json"


def test_runtime_requirements_exclude_packaging_tools() -> None:
    requirements = (PUBLIC_ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    forbidden = ["playwright", "python-pptx", "pywin32", "powerpoint", "python-dotenv"]
    assert not any(package in requirements for package in forbidden)
