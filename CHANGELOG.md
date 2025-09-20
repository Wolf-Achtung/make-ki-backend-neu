# Changelog – Gold-Standard (2025‑09‑20)

## Added
- **Meta‑Guard & Persona‑Lock:** Alle Metafelder werden gesetzt (nie „—“). Leere Werte = „n. v.“.
- **Roadmap‑Token‑Fix:** t30/t90/t365 werden sicher ersetzt; Artefakt „bis Tage“ → „bis 30 Tage“.
- **„Sichere Sofortschritte“-Box:** Konsistentes Naming + Pastellblau‑Box im Template.
- **Kurator & Sanitizer (Live‑Updates):** Entfernt URLs, erhält Zahlen/Einheiten, bündelt Kurztexte.
- **DE/EN/Both‑Pfad:** Ein Request kann beide Sprachversionen ausgeben (Page‑Break).
- **HTML‑Length‑Guard:** < 1000 Zeichen → narrativer Fallback statt leeres PDF.

## Fixed
- Eliminierte Ellipsen/Platzhalter in Python/HTML, die Syntaxfehler verursachten.
- Robustere Modul‑Ladeschicht mit Logging.

## Notes
- Optionaler PDF‑Service ist als Stub vorgesehen – HTML wird immer ausgeliefert.
