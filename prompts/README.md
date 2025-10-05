# Prompts – Gold‑Standard Layout

We ship **language‑scoped subfolders** and **root copies** for backward compatibility:

```
prompts/
  de/  … *_de.md
  en/  … *_en.md
  executive_summary_de.md  (temporary duplicate for current loader)
  executive_summary_en.md  (temporary duplicate for current loader)
  ...
```

**Why subfolders (`de`, `en`)?**
1) Clear locale scoping and QA (no cross‑language leakage).
2) Safer upgrades and translation review (PRs touch one locale).
3) Easier runtime selection (`lang` → path).
4) Prevent file‑name collisions with future locales.
5) Cleaner packaging for CI/CD and content linting.

**Zero‑downtime migration**
Your current backend loads files from `prompts/*.md` (see logs “Loaded prompt: executive_summary_de.md”). Keep using it today – the **root copies** are identical to the `de/` and `en/` files. When ready, switch the loader to check:
1) `prompts/{lang}/{name}` then
2) fallback to `prompts/{name}`.

**Output guards in every file**
- Only semantic HTML fragments – no code fences, no `<html>`, no `<!DOCTYPE>`.
- No dates in LLM output (renderer adds “Stand/As of”). 
- Domain pins: *Consulting & Professional Services (Solo)* only.
- Economics: respect 4‑month payback baseline from backend.

—
