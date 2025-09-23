# Gold‑Standard Report – FULL Variant

**Modus:** LLM für Executive Summary, Risiken, Empfehlungen, Roadmap, Vision · Deterministische Basis (Partials, Whitelists, Fallbacks)  
**Design:** Cheat‑Sheet‑Look (Blautöne, Seitenzahlen, kurze Module) · Ansprache: professionell, beratend, konstruktiv, **per Sie**.

## Dateien
- `gpt_analyze.py` – Full‑Analyzer (Template‑Only, Story‑Killer, Whitelist‑Only; nutzt `prompts.zip`/`data.zip`)
- `prompts_loader.py` – entpackt `prompts.zip` und baut eine Prompt‑Registry
- `innovation_intro.py` – Branchen‑Intros für Gamechanger
- `templates/report_template_de.html`, `report_template_en.html`
- `templates/partials/quick_wins_*.html`, `eu_ai_act_*.html`
- `data/tool_whitelist.json`, `data/funding_whitelist.json` (mit `as_of`)

## ENV
```bash
TEMPLATE_DE=report_template_de.html
TEMPLATE_EN=report_template_en.html

LLM_MODE=full            # full | hybrid | off
GPT_MODEL_NAME=gpt-4o-mini
GPT_TEMPERATURE=0.2
```
Prompts bitte als `prompts.zip` ins App‑Root legen (z. B. `exec_summary_de.md`, `risks_de.md`, `recommendations_de.md`, `roadmap_de.md`, `vision_de.md`).

## Qualität
- Template‑Only Rendering (kein Analyzer‑HTML)
- Story‑Killer blockt Anekdoten/„Mehr erfahren“/Fantasie‑Tools
- Whitelist‑Only für Tools & Förderung
- „Per Sie“‑Ton in allen Texten
- Seitenzahlen im Footer