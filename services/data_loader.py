from pathlib import Path
import json, yaml, csv
from typing import Dict, Any, List
from loguru import logger

ROOT = Path(__file__).resolve().parents[1]
PROMPTS_DIR = ROOT / "prompts"
DATA_DIR = ROOT / "data"

def _read_text(p: Path) -> str | None:
    try:
        txt = p.read_text(encoding="utf-8")
        if "..." in txt and p.suffix != ".md":
            logger.warning(f"File likely truncated (contains '...'): {p.name}")
        return txt
    except Exception as e:
        logger.error(f"Failed to read {p}: {e}")
        return None

def load_all_prompts(lang: str) -> dict:
    folder = PROMPTS_DIR / lang
    prompts: Dict[str, str] = {}
    if not folder.exists():
        logger.warning(f"No prompts folder for language {lang}: {folder}")
        return prompts
    for p in folder.glob("*.md"):
        txt = _read_text(p)
        if not txt:
            continue
        key = p.stem.lower().strip()
        prompts[key] = txt
    logger.info(f"Loaded {len(prompts)} prompts for {lang}")
    return prompts

def _safe_json_load(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Skip invalid JSON: {p.name} -> {e}")
        return None

def _safe_yaml_load(p: Path):
    try:
        return yaml.safe_load(p.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Skip invalid YAML: {p.name} -> {e}")
        return None

def _safe_csv_load(p: Path):
    rows = []
    try:
        with p.open("r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                rows.append(row)
        return rows
    except Exception as e:
        logger.warning(f"Skip invalid CSV: {p.name} -> {e}")
        return None

def load_all_data() -> Dict[str, Any]:
    datasets: Dict[str, Any] = {}
    if not DATA_DIR.exists():
        return datasets
    for p in DATA_DIR.rglob("*"):
        if p.is_dir():
            continue
        key = p.relative_to(DATA_DIR).as_posix().lower()
        if p.suffix == ".json":
            data = _safe_json_load(p)
        elif p.suffix in (".yaml", ".yml"):
            data = _safe_yaml_load(p)
        elif p.suffix == ".csv":
            data = _safe_csv_load(p)
        elif p.suffix in (".md", ".txt"):
            data = _read_text(p)
        else:
            continue
        if data is not None:
            datasets[key] = data
    logger.info(f"Loaded {len(datasets)} data artifacts from {DATA_DIR}")
    return datasets
