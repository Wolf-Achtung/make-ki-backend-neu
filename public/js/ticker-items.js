
const ITEMS = [
  { id:'detective-reverse',
    de:{ label:'Detektiv rückwärts', explain:'Skizziere einen Fall — ich rekonstruiere alles rückwärts.', help:'Gib Ort, Opfer/Täter, 3–5 Hinweise. Output: rückwärts erzählte Ermittlungs‑Timeline inkl. Fazit & offenen Fragen.', placeholder:'Tatort, Beteiligte, 3–5 Hinweise', prompt:'Rekonstruiere folgenden Fall rückwärts (Timeline, präzise, deutsch). Fall: {{input}}' },
    en:{ label:'Detective in Reverse', explain:'Sketch a case — I reconstruct it backwards.', help:'Give 3–5 clues. Output: reverse timeline + conclusion.', placeholder:'Scene, people, clues', prompt:'Reconstruct this case backwards: {{input}}' } },
  { id:'biography-pixel',
    de:{ label:'Biografie eines Pixels', explain:'Nenne Genre/Ära — ein Pixel erzählt.', help:'Sag Genre/Ära. Output: 3 Mini‑Abschnitte (Szene • Konflikt • Auflösung).', placeholder:'Genre oder Epoche', prompt:'Schreibe eine Ich‑Erzählung im Stil {{input}} in 3 Mini‑Abschnitten. Max. 900 Zeichen.' },
    en:{ label:'Biography of a Pixel', explain:'Give a genre/era — the pixel speaks.', help:'Provide genre/era. Output: 3 mini sections.', placeholder:'Genre or era', prompt:'Write a first‑person vignette in the style of {{input}}.' } },
  { id:'npc-afterhours',
    de:{ label:'NPC nach Feierabend', explain:'Gib Genre/Setting – ein Nebencharakter erzählt.', help:'Sag Spiel/Genre. Output: 5 kurze Absätze mit innerem Monolog.', placeholder:'Setting/Genre', prompt:'Erzähle die Gedanken eines Nebencharakters nach Feierabend in {{input}}.' },
    en:{ label:'NPC After Hours', explain:'Give genre/setting — a side character talks.', help:'Provide world/genre. Output: 5 paras.', placeholder:'Setting/genre', prompt:'Write the thoughts of a side character after work in {{input}}.' } },
  { id:'color-synesthesia',
    de:{ label:'Farbsynästhetiker', explain:'Nenne zwei Songs – ich male dir die Farben.', help:'Gib 2 Songs. Output: je 6 Bullets + Vergleich.', placeholder:'Song A — Song B', prompt:'Analysiere die synästhetischen Farbräume: {{input}}.' },
    en:{ label:'Color Synesthete', explain:'Name two songs — I paint their colors.', help:'Two songs. Output: 6 bullets each + comparison.', placeholder:'Song A — Song B', prompt:'Analyse the synesthetic color spaces of {{input}}.' } },
  { id:'today-new',
    de:{ label:'Heute neu', explain:'Tages‑Spotlight: KI‑Fund des Tages.', help:'Ohne Input: Ich ziehe eine News & fasse zusammen.', placeholder:'—', prompt:'Formuliere eine inspirierende, präzise KI‑Notiz aus: {{input}} → Kurzfazit • 3 Nuggets • 1 Praxisidee.' },
    en:{ label:'Today new', explain:'Daily spotlight: AI find of the day.', help:'No input: I’ll condense a news item.', placeholder:'—', prompt:'Condense into crisp note: {{input}}.' } },
  { id:'emotion-alchemist',
    de:{ label:'Emotions‑Alchemist', explain:'Sag Ausgangs‑ und Zielgefühl …', help:'Gib „von … nach …“ + Kontext. Output: 5 Schritte + 2 Stolpersteine + 1 Übung.', placeholder:'Von … nach … (+ Kontext)', prompt:'Leite eine Person in 5 Schritten von {{input}}. Ergänze 2 Stolpersteine + 1 Mini‑Übung.' },
    en:{ label:'Emotion Alchemist', explain:'From feeling A to B …', help:'Give “from … to …”. Output: 5 steps + 2 pitfalls + 1 exercise.', placeholder:'From … to …', prompt:'Guide a person in 5 steps from {{input}} with 2 pitfalls + 1 mini exercise.' } },
  { id:'time-travel-diary',
    de:{ label:'Zeitreise‑Tagebuch', explain:'Schick mir einen Tag – ich schreibe ihn neu.', help:'Gib Datum + Ort + Ereignis. Output: 3 Szenen.', placeholder:'Datum + Ort + Ereignis', prompt:'Schreibe ein Tagebuch aus alternativer Zeitlinie zu {{input}} in 3 Szenen.' },
    en:{ label:'Time‑travel Diary', explain:'Send a day — I rewrite it.', help:'Date + place + event. Output: 3 scenes.', placeholder:'Date • place • event', prompt:'Write a diary entry from an alternate timeline for {{input}}.' } },
  { id:'interdimensional-market',
    de:{ label:'Interdimensionaler Markt', explain:'Sag, was du suchst – ich öffne einen Markt.', help:'Gib „Ich suche …“. Output: Szene + 5 Stände.', placeholder:'Was suchst du?', prompt:'Gestalte einen interdimensionalen Markt rund um: {{input}} — Szene + 5 Stände.' },
    en:{ label:'Interdimensional Market', explain:'Tell me what you seek — I open a market.', help:'Say “I’m looking for …”. Output: scene + 5 stalls.', placeholder:'What are you looking for?', prompt:'Create a market around: {{input}} — scene + 5 stalls.' } }
];
export function tickerItemsFor(locale){
  const l = (locale === 'de' || locale === 'en') ? locale : 'en';
  return ITEMS.map(it => ({ id: it.id, ...it[l] }));
}
