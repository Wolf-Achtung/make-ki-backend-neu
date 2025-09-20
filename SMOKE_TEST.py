# Simple smoke test (no external PDF service required)
import json
import gpt_analyze

briefing = {"branche":"Beratung","unternehmensgroesse":"solo","standort":"Berlin","sprache":"de"}

ctx = gpt_analyze.build_context(briefing, "de")
html = gpt_analyze.render_html(ctx, "de")
assert len(html) > 1000 and "Sichere Sofortschritte" in html and "Roadmap" in html
open("smoke_de.html","w",encoding="utf-8").write(html)

ctx_en = gpt_analyze.build_context(briefing, "en")
html_en = gpt_analyze.render_html(ctx_en, "en")
assert len(html_en) > 1000 and "Secure quick steps" in html_en
open("smoke_en.html","w",encoding="utf-8").write(html_en)

print("SMOKE OK")
