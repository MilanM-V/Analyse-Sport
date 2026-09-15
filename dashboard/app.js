let chartInstance = null;

async function fetchData() {
    const refreshIcon = document.getElementById('refresh-icon');
    refreshIcon.classList.add('animate-spin');
    
    try {
        // Prevent caching by appending timestamp
        const response = await fetch(`data.json?t=${new Date().getTime()}`);
        if (!response.ok) throw new Error("Data not found");
        
        const data = await response.json();
        updateDashboard(data);
    } catch (error) {
        console.error("Error fetching data:", error);
    } finally {
        setTimeout(() => refreshIcon.classList.remove('animate-spin'), 500);
    }
}

function updateDashboard(data) {
    if (data.error) {
        console.error(data.error);
        return;
    }

    // Update Last Updated
    const date = new Date(data.last_updated);
    document.getElementById('last-updated').textContent = `Dernière mise à jour : ${date.toLocaleString('fr-FR')}`;

    // Update KPIs
    const kpis = data.kpis;
    document.getElementById('kpi-balance').textContent = `${kpis.current_balance.toFixed(2)} U`;
    
    const profitEl = document.getElementById('kpi-profit');
    profitEl.textContent = `${kpis.total_profit > 0 ? '+' : ''}${kpis.total_profit.toFixed(2)} U`;
    profitEl.className = `text-2xl font-bold mt-2 ${kpis.total_profit > 0 ? 'text-success' : kpis.total_profit < 0 ? 'text-danger' : ''}`;

    const roiEl = document.getElementById('kpi-roi');
    roiEl.textContent = `${kpis.roi > 0 ? '+' : ''}${kpis.roi.toFixed(1)}%`;
    roiEl.className = `text-2xl font-bold mt-2 ${kpis.roi > 0 ? 'text-success' : kpis.roi < 0 ? 'text-danger' : ''}`;

    document.getElementById('kpi-winrate').textContent = `${kpis.winrate.toFixed(1)}%`;
    document.getElementById('kpi-total-bets').textContent = kpis.total_bets;
    document.getElementById('pending-exposure').textContent = `${kpis.pending_exposure.toFixed(2)} U`;

    // Update Active Bets
    updateActiveBets(data.pending_bets);

    // Update History Table
    updateHistory(data.history);

    // Update Chart
    updateChart(data.evolution);
}

function updateActiveBets(bets) {
    document.getElementById('active-count').textContent = bets.length;
    const container = document.getElementById('active-bets-container');
    container.innerHTML = '';

    if (bets.length === 0) {
        container.innerHTML = `<div class="text-center text-slate-500 py-8">Aucun pari en cours</div>`;
        return;
    }

    bets.forEach(bet => {
        const betEl = document.createElement('div');
        betEl.className = "bg-slate-800/50 p-3 rounded-lg border border-slate-700/50";
        betEl.innerHTML = `
            <div class="flex justify-between items-start mb-1">
                <span class="font-medium text-white">${bet.player}</span>
                <span class="text-xs bg-slate-700 px-2 py-1 rounded text-slate-300 uppercase">${bet.sport}</span>
            </div>
            <div class="text-sm text-slate-400 flex justify-between">
                <span>${bet.market}</span>
                <span class="text-accent font-medium">@${bet.cote.toFixed(2)}</span>
            </div>
            <div class="mt-2 text-sm font-medium text-slate-300">
                Mise : ${bet.mise.toFixed(2)} U
            </div>
        `;
        container.appendChild(betEl);
    });
}

function updateHistory(bets) {
    const tbody = document.getElementById('history-tbody');
    tbody.innerHTML = '';
    
    // Take only the last 50 for performance
    const displayBets = bets.slice(0, 50);

    displayBets.forEach(bet => {
        const tr = document.createElement('tr');
        tr.className = "hover:bg-slate-800/30 transition-colors";
        
        const dateObj = new Date(bet.timestamp);
        const dateStr = dateObj.toLocaleDateString('fr-FR', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
        
        const gainClass = bet.gain > 0 ? "text-success" : (bet.gain < 0 ? "text-danger" : "text-slate-400");
        const gainText = bet.gain > 0 ? `+${bet.gain.toFixed(2)} U` : `${bet.gain.toFixed(2)} U`;

        tr.innerHTML = `
            <td class="py-3 px-4 text-slate-300">${dateStr}</td>
            <td class="py-3 px-4 uppercase text-xs font-semibold text-slate-400 tracking-wider">${bet.sport}</td>
            <td class="py-3 px-4 text-white font-medium">${bet.player}</td>
            <td class="py-3 px-4 text-slate-400">${bet.market}</td>
            <td class="py-3 px-4 text-slate-300">@${bet.cote.toFixed(2)}</td>
            <td class="py-3 px-4 text-slate-300">${bet.mise.toFixed(2)} U</td>
            <td class="py-3 px-4 text-right font-bold ${gainClass}">${gainText}</td>
        `;
        tbody.appendChild(tr);
    });
}

function updateChart(evolution) {
    const ctx = document.getElementById('evolutionChart').getContext('2d');
    
    const labels = evolution.map(d => {
        const dt = new Date(d.date);
        return dt.toLocaleDateString('fr-FR', { month: 'short', day: 'numeric' });
    });
    const dataPoints = evolution.map(d => d.balance);

    if (chartInstance) {
        chartInstance.destroy();
    }

    Chart.defaults.color = '#94a3b8';
    Chart.defaults.font.family = "'Inter', sans-serif";

    chartInstance = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Bankroll (U)',
                data: dataPoints,
                borderColor: '#3b82f6',
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                borderWidth: 2,
                pointRadius: 0,
                pointHoverRadius: 4,
                fill: true,
                tension: 0.2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                intersect: false,
                mode: 'index',
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    backgroundColor: '#1e293b',
                    titleColor: '#f8fafc',
                    bodyColor: '#cbd5e1',
                    borderColor: '#334155',
                    borderWidth: 1,
                    padding: 10,
                    displayColors: false,
                    callbacks: {
                        label: function(context) {
                            return `${context.parsed.y.toFixed(2)} U`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    grid: { display: false, drawBorder: false },
                    ticks: { maxTicksLimit: 8 }
                },
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)', drawBorder: false },
                    beginAtZero: false
                }
            }
        }
    });
}

// Initial fetch
fetchData();
// Auto-refresh every 5 minutes
setInterval(fetchData, 5 * 60 * 1000);
