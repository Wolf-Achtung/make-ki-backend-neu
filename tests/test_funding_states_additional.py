
import json, re, sys, pathlib, datetime

PATH = pathlib.Path(__file__).resolve().parent.parent / "funding_states_additional.json"
data = json.loads(pathlib.Path(PATH).read_text(encoding="utf-8"))

# 1) Structure: top-level dict of states -> list of programs
assert isinstance(data, dict) and data, "Top-level must be a non-empty dict"

required_fields = {"program", "target", "benefit", "status", "as_of", "source", "sector_hints"}
url_re = re.compile(r"^https?://")

issues = []

for state, items in data.items():
    if not isinstance(items, list) or not (1 <= len(items) <= 6):
        issues.append(f"{state}: items must be a list with 1..6 entries")
        continue
    for i, row in enumerate(items, 1):
        missing = required_fields - row.keys()
        if missing:
            issues.append(f"{state} #{i}: missing fields {sorted(missing)}")
            continue
        # Asserts
        assert isinstance(row["sector_hints"], list) and row["sector_hints"], f"{state} #{i}: sector_hints must be non-empty list"
        assert url_re.match(row["source"]), f"{state} #{i}: source must be http(s) URL"
        # ISO date
        try:
            datetime.date.fromisoformat(row["as_of"])
        except Exception:
            issues.append(f"{state} #{i}: as_of not ISO date: {row['as_of']}")
        # Hard limits (1000 Zeichen pro Kapitel betreffen Report; hier kurze Felder prüfen)
        for key in ("target", "benefit", "status"):
            assert len(row[key]) <= 400, f"{state} #{i}: '{key}' too long ({len(row[key])} chars)"

# State coverage: should include 12 additional Bundesländer
expected_states = {
    "Hamburg","Hessen","Brandenburg","Mecklenburg‑Vorpommern","Niedersachsen",
    "Rheinland‑Pfalz","Saarland","Sachsen","Sachsen‑Anhalt","Schleswig‑Holstein",
    "Thüringen","Bremen"
}
assert expected_states.issubset(set(data.keys())), "Not all required states present"

if issues:
    print("❌ Preflight FAILED:")
    for msg in issues:
        print(" -", msg)
    sys.exit(1)
else:
    print("✅ Preflight OK: funding_states_additional.json is sound and ready.")
