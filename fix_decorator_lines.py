import re, sys, io

path = "main.py"

with io.open(path, "r", encoding="utf-8") as f:
    src = f.read()

# Regel: Alles wie "@irgendwas(... )  async def" ODER "@irgendwas(... )  def"
# → in zwei Zeilen auftrennen: Zeile mit Decorator, nächste Zeile mit def/async def
pat = re.compile(r'^(@[^\n]+?)\s+(async\s+def|def)\s+', re.M)
new = pat.sub(r'\1\n\2 ', src)

# Optionale zusätzliche Glättung: doppelte Leerzeilen vermeiden
new = re.sub(r'\n{3,}', '\n\n', new)

if new != src:
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(new)
    print("Patched decorator lines in", path)
else:
    print("No inline-decorator issues found in", path)

# Bonus: Syntax-Check
try:
    compile(new, path, "exec")
    print("Syntax OK after patch.")
except SyntaxError as e:
    print(f"SyntaxError after patch at line {e.lineno}: {e.msg}")
    sys.exit(1)
