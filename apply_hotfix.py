#!/usr/bin/env python3
import sys, os, re, io, shutil

def patch_imports(src: str) -> tuple[str, list[str]]:
    changed = []
    out = src

    # Normalize line endings for safety
    out = out.replace('\r\n', '\n')

    # 1) If there's already "from jose import jwt, JWTError" do nothing
    if re.search(r'from\s+jose\s+import\s+.*\bJWTError\b', out):
        return out, changed

    # 2) If there's "from jose import jwt" (without JWTError), add it
    def repl_add_jwterror(m):
        before = m.group(0)
        if 'JWTError' not in before:
            changed.append("Updated jose import to include JWTError")
            if before.strip().endswith(','):
                return before + ' JWTError'
            else:
                return before + ', JWTError'
        return before

    out2 = re.sub(r'from\s+jose\s+import\s+([^\n#]+)', repl_add_jwterror, out, count=1, flags=re.MULTILINE)
    if out2 != out:
        return out2, changed

    # 3) If there's "import jose" somewhere but no "from jose import ...", add a new line import
    if re.search(r'^\s*import\s+jose\b', out, flags=re.MULTILINE):
        # Insert after last import block
        lines = out.split('\n')
        insert_at = 0
        for i, line in enumerate(lines):
            if re.match(r'^\s*(import|from)\s+', line):
                insert_at = i + 1
        lines.insert(insert_at, 'from jose import JWTError')
        changed.append("Inserted `from jose import JWTError` after existing imports")
        return '\n'.join(lines), changed

    # 4) No jose imports at all -> add a clean import in the import block
    lines = out.split('\n')
    insert_at = 0
    for i, line in enumerate(lines):
        if re.match(r'^\s*(import|from)\s+', line):
            insert_at = i + 1
    lines.insert(insert_at, 'from jose import JWTError')
    changed.append("Inserted `from jose import JWTError` in import block")
    return '\n'.join(lines), changed

def main():
    repo = sys.argv[1] if len(sys.argv) > 1 else '.'
    main_py = os.path.join(repo, 'main.py')
    if not os.path.exists(main_py):
        print(f"[!] main.py not found at: {main_py}")
        sys.exit(1)

    with open(main_py, 'r', encoding='utf-8') as f:
        src = f.read()

    new_src, changes = patch_imports(src)
    if not changes:
        print("[i] No changes required; JWTError already imported.")
        sys.exit(0)

    # Backup and write
    backup_path = main_py + '.bak'
    shutil.copyfile(main_py, backup_path)
    with open(main_py, 'w', encoding='utf-8') as f:
        f.write(new_src)

    print("[✓] Hotfix applied successfully.")
    print("    - Backup written to:", backup_path)
    print("    - Changes:")
    for c in changes:
        print("      *", c)

if __name__ == "__main__":
    main()
