# Top recommendations – the big 5

Write an HTML ordered list (`<ol>…</ol>`) containing the five most important recommendations for the company. Each recommendation should start with a bold action keyword and be phrased as a single sentence, ending with the expected impact and required effort (High/Medium/Low) in parentheses, for example `(H/M)`. Draw on the company’s vision, strategic goals, greatest potential and moonshot, and weave in industry benchmarks, opportunities and risks. Combine strategic measures (such as governance, collaboration and data foundations) with tangible next steps (pilots, prototypes, training). Do not duplicate items from the quick wins or the roadmap.

Take the company size into account internally only, tailoring recommendations for solo professionals, small teams (2–10) or SMEs (11–100) without naming these categories explicitly. Adopt a friendly, advisory tone that motivates rather than lectures.

For solo businesses or very small teams with limited weekly capacity, recommendations should be affordable and modular – for example, using managed LLM services, implementing lightweight governance guidelines or running short automation workshops. Larger SMEs can take on more ambitious projects such as building their own data platform, deploying an LLMOps pipeline or creating a white‑label consulting tool. Also take into account the selected training interests (e.g. automation & scripts) and the vision priority to suggest relevant training or product development paths.

Where available, also factor in the weekly time capacity (`time_capacity`), existing tools (`existing_tools`), regulated industry flags (`regulated_industry`), training interests (`training_interests`) and the priority of the vision elements (`vision_priority`) to tailor your recommendations to the company's resources, compliance obligations, learning plans and strategic focus. Do not reference these variable names explicitly in the report.

Example:

```
<ol>
  <li><b>Expand partnerships:</b> Forge strategic alliances with AI technology providers to broaden your offering and leverage shared resources (H/M).</li>
  <li><b>Embed compliance:</b> Strengthen your data‑protection and governance practices and align processes with the EU AI Act to reduce legal risks (M/M).</li>
  <li><b>Improve data quality:</b> Establish structured data management (e.g. a CRM) and perform a data clean‑up to build a solid foundation for AI projects (M/M).</li>
  <li><b>Launch pilots:</b> Select a priority use case and implement an MVP to achieve measurable results within three months (M/M).</li>
  <li><b>Empower your team:</b> Run short AI awareness workshops and clarify roles to build acceptance and know‑how within the team (L/L).</li>
</ol>
```