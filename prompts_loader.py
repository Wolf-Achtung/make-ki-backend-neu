from __future__ import annotations
import zipfile
from pathlib import Path
from typing import Dict

BASE = Path(__file__).resolve().parent

def _unzip(zipname: str, target: str) -> None:
    z = BASE / zipname
    t = BASE / target
    if z.exists():
        t.mkdir(exist_ok=True, parents=True)
        try:
            with zipfile.ZipFile(z, "r") as f:
                f.extractall(t)
        except Exception:
            pass

def ensure_unzipped() -> None:
    _unzip("prompts.zip", "prompts")
    _unzip("data.zip", "data")

def load_registry() -> Dict[str, str]:
    ensure_unzipped()
    reg: Dict[str,str] = {}
    pdir = BASE / "prompts"
    if not pdir.exists():
        return reg
    for p in list(pdir.glob("**/*.md")) + list(pdir.glob("**/*.txt")):
        try:
            reg[p.stem.lower()] = p.read_text(encoding="utf-8")
        except Exception:
            continue
    return reg

def get_prompt(reg: Dict[str,str], key: str, lang: str = "de") -> str:
    lang = "de" if str(lang).lower().startswith("de") else "en"
    key = key.lower()
    for cand in (f"{key}_{lang}", key):
        if cand in reg:
            return reg[cand]
    for k,v in reg.items():
        if k.startswith(f"{key}_{lang}") or k.startswith(key):
            return v
    return ""