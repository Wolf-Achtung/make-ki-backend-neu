# Score-Visualisierung (Chart.js – Marken-Blau)

Ihr individueller Score im Vergleich:  
Die Balken zeigen Ihren Gesamtwert sowie Teil-Scores für Datenschutz, Fördermittel und Umsetzung.

<!-- Chart.js (nur in HTML/Preview sichtbar) -->
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
        '#34b7e4',
        '#26c2a7',
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

<!-- Fallback für PDF-Export -->
![Score-Balkendiagramm](https://dummyimage.com/700x210/003b5a/ffffff&text=Score+Chart+Beispiel)

*Hinweis: Das interaktive Balkendiagramm ist nur in der HTML-Ansicht sichtbar.*
