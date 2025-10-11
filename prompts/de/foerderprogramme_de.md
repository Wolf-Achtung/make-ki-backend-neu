
Erzeuge eine **Förderprogramme‑Tabelle** (Berlin **und** bundesweit) als HTML‑Fragment für KMU/Freiberufler.

**Pflichtprogramme (immer aufführen):**
- ZIM – Zentrales Innovationsprogramm Mittelstand (Bund)
- BMBF – KMU‑innovativ: IKT (Bund, DLR‑PT)
- Wenn Bundesland = BE: Pro FIT (Berlin), Transfer BONUS (IBB)

**Spalten (genau diese, in dieser Reihenfolge):**
- Programm
- Träger
- Quote/Budget
- Bund/Land
- Frist/Stand (Monat Jahr oder „laufend“)
- Link

**Regeln:**
- Nur **echte Programme** (keine News/Artikel). **Jedes** Programm mit Link zur offiziellen Seite.
- Keine Floskeln, keine Eigenwerbung. Kürze, aber **präzise**.
- Wenn Fristen unklar: „laufend (bitte prüfen)“. Datum **TT.MM.JJJJ** falls bekannt.
- Mindestens 4 Zeilen, dedupliziert.

**Ausgabe:** Semantische `<table class="compact funding">` mit `<thead>`/`<tbody>`. Keine Zusatztexte.
