# SMOKE_TEST.py — HTML smoke
import gpt_analyze
briefing = {"branche":"Beratung","unternehmensgroesse":"solo","standort":"Berlin","sprache":"de"}
ctx = gpt_analyze.build_context(briefing, "de")
from gpt_analyze import render_html
html = render_html(ctx, "de")
open("smoke_de.html","w",encoding="utf-8").write(html)
print("SMOKE OK", len(html))
