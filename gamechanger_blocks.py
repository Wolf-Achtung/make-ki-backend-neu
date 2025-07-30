# gamechanger_blocks.py

from innovation_intro import INNOVATION_INTRO

def build_gamechanger_blocks(data: dict, features: dict) -> str:
    blocks = []

    if features.get("moonshot"):
        blocks.append(
            "Bitte generieren Sie zum Abschluss eine visionäre Moonshot-Empfehlung: "
            "Welche bahnbrechende KI-Innovation könnte diese Branche/Unternehmen in 3 Jahren revolutionieren?"
        )
    if features.get("maturity_benchmark"):
        blocks.append(
            "Vergleichen Sie den KI-Reifegrad dieses Unternehmens (Score, Digitalisierungsgrad, Automatisierung, Know-how) "
            "mit aktuellen Benchmarks der Branche und stellen Sie das Ergebnis in einer Tabelle dar."
        )
    if features.get("foerder_forecast"):
        blocks.append(
            "Fügen Sie einen Forecast hinzu: Welche relevanten Förderprogramme werden laut offiziellen Quellen oder Trends "
            "im nächsten Jahr starten, enden oder sich stark verändern?"
        )
    if features.get("next_steps"):
        blocks.append(
            "Leiten Sie eine konkrete, individuell empfohlene 30-Tage- und 6-Monats-Roadmap mit direkt umsetzbaren Schritten aus den Ergebnissen ab."
        )
    if features.get("realtime_check"):
        blocks.append(
            "Überprüfen Sie für jedes empfohlene Förderprogramm und Tool, ob es zum Stichtag {{ datum }} noch verfügbar ist und für Unternehmen dieser Branche/Größe offen steht. "
            "Vermerken Sie abgelaufene Programme oder geänderte Bedingungen."
        )
    if features.get("best_practice"):
        branche = data.get("branche", "").lower()
        intro = INNOVATION_INTRO.get(branche, "")
        blocks.append(
            f"{intro}\nGeben Sie zwei kurze Best-Practice-Beispiele, wie KI oder Fördermittel in dieser Branche zuletzt erfolgreich eingesetzt wurden."
        )

    return "\n\n".join(blocks)
