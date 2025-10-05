# File: tests/test_prompt_loader.py
# -*- coding: utf-8 -*-
import importlib
import os
from pathlib import Path

import pytest


def write(p: Path, content: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")


@pytest.fixture()
def tmp_prompts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    # Create a fake prompts dir
    base = tmp_path / "prompts"
    # de subtree
    write(base / "de" / "executive_summary_de.md", "DE: from subdir")
    # root fallback file (en)
    write(base / "executive_summary_en.md", "EN: from root")
    # unsuffixed fallback
    write(base / "quick_wins.md", "UNSUFFIXED quick wins")
    monkeypatch.setenv("PROMPTS_DIR", str(base))
    # Force reload of module to capture env var
    if "gpt_analyze" in globals():
        import sys as _sys
        _sys.modules.pop("gpt_analyze", None)
    mod = importlib.import_module("gpt_analyze")
    return mod


def test_loader_prefers_lang_subdir(tmp_prompts):
    m = tmp_prompts
    txt = m._prompt("executive_summary", "de")
    assert "DE: from subdir" in txt


def test_loader_falls_back_to_root_lang_file(tmp_prompts, monkeypatch):
    m = tmp_prompts
    # Remove subdir file to force fallback
    prompts_dir = Path(os.environ["PROMPTS_DIR"])
    (prompts_dir / "de" / "executive_summary_de.md").unlink()
    txt = m._prompt("executive_summary", "en")
    assert "EN: from root" in txt


def test_loader_falls_back_to_unsuffixed(tmp_prompts):
    m = tmp_prompts
    txt = m._prompt("quick_wins", "en-GB")
    assert "UNSUFFIXED quick wins" in txt
