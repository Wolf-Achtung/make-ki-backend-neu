# filename: scripts/validate_schema.py
# Simple CI guard: ensure shared/report_schema.json exists and contains expected fields/enums.
import json, sys, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
schema_file = ROOT / "shared" / "report_schema.json"
required_fields = ["branche", "unternehmensgroesse", "bundesland"]

try:
    data = json.loads(schema_file.read_text(encoding="utf-8"))
except Exception as e:
    print("Schema missing or unreadable:", e)
    sys.exit(1)

fields = (data.get("fields") or {})
missing = [k for k in required_fields if k not in fields]
if missing:
    print("Schema fields missing:", ",".join(missing))
    sys.exit(2)

for k in required_fields:
    enum = fields[k].get("enum") or []
    if not enum:
        print(f"Schema field '{k}' has empty enum")
        sys.exit(3)

print("Schema OK:", data.get("version"))
sys.exit(0)
