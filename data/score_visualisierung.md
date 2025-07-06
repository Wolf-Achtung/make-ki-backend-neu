# Score-Visualisierung (Chart.js – Marken-Blau)

Füge diesen Code-Block in dein PDF-/HTML-Template ein.  
Die Farben sind markenkonform (nur Blautöne).  
**Tipp:** Passe die Score-Werte per Template-Variable (`{{KI_SCORE}}` usw.) dynamisch an.

```html
<canvas id="scoreChart" width="460" height="290"></canvas>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
  const ctx = document.getElementById('scoreChart').getContext('2d');
  const scoreChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: ['KI-Readiness', 'Datenschutz', 'Fördermittel-Fitness', 'Umsetzungskompetenz'],
      datasets: [{
        label: 'Score (0–100)',
        data: [{{KI_SCORE}}, {{DSGVO_SCORE}}, {{FOERDER_SCORE}}, {{UMSETZUNG_SCORE}}],
        backgroundColor: [
          '#003b5a',
          '#045f8e',
          '#2c6ca7',
          '#659cc9'
        ],
        borderRadius: 12,
        barPercentage: 0.55,
        categoryPercentage: 0.7,
      }]
    },
    options: {
      plugins: {
        legend: { display: false },
        title: {
          display: true,
          text: 'Ihre Scoring-Ergebnisse',
          color: '#003b5a',
          font: { size: 18, weight: 'bold' }
        }
      },
      scales: {
        y: {
          beginAtZero: true,
          max: 100,
          ticks: { color: '#003b5a', font: { size: 15 } },
          grid: { color: '#e6eef5' }
        },
        x: {
          ticks: { color: '#003b5a', font: { size: 15 } },
          grid: { color: '#e6eef5' }
        }
      }
    }
  });
</script>
