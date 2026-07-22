// Admin Dashboard Charts using Chart.js

let categoryChart = null;
let statusChart = null;

document.addEventListener('DOMContentLoaded', () => {
    const statsContainer = document.getElementById('admin-charts-container');
    if (!statsContainer) return;

    // Fetch and render data
    loadDashboardStats();

    // Listen to theme changes to redraw charts with correct font colors
    const themeToggles = document.querySelectorAll('#themeToggleBtn');
    themeToggles.forEach(btn => {
        btn.addEventListener('click', () => {
            // Wait slightly for DOM to update theme attribute
            setTimeout(() => {
                loadDashboardStats();
            }, 150);
        });
    });
});

/**
 * Fetch stats JSON from backend and initialize charts
 */
function loadDashboardStats() {
    fetch('/api/admin/stats')
        .then(response => response.json())
        .then(data => {
            renderCharts(data);
        })
        .catch(err => console.error("Error loading dashboard metrics:", err));
}

/**
 * Render/Update Chart.js instances with the premium palette
 */
function renderCharts(data) {
    const isDark = document.documentElement.classList.contains('dark');
    const textColor = isDark ? '#CBD5E1' : '#475569';
    const gridColor = isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.04)';
    
    // Premium brand palette
    const violetColor  = isDark ? '#A78BFA' : '#8B5CF6';
    const cyanColor    = isDark ? '#22D3EE' : '#06B6D4';
    const pinkColor    = isDark ? '#F9A8D4' : '#F472B6';
    const yellowColor  = isDark ? '#FDE68A' : '#FBBF24';
    const greenColor   = isDark ? '#6EE7B7' : '#22C55E';
    const dangerColor  = isDark ? '#FCA5A5' : '#EF4444';
    const slateColor   = isDark ? '#94A3B8' : '#64748B';

    // 1. Category Chart (Doughnut)
    const catCanvas = document.getElementById('categoryChart');
    if (catCanvas) {
        if (categoryChart) categoryChart.destroy();
        
        const catData = data.category_counts || {};
        const labels = Object.keys(catData);
        const values = Object.values(catData);

        // Fallback if empty
        if (labels.length === 0) {
            labels.push("No data");
            values.push(1);
        }

        categoryChart = new Chart(catCanvas, {
            type: 'doughnut',
            data: {
                labels: labels,
                datasets: [{
                    data: values,
                    backgroundColor: [
                        violetColor,
                        cyanColor,
                        pinkColor,
                        yellowColor,
                        greenColor,
                        dangerColor,
                        slateColor
                    ],
                    borderWidth: isDark ? 2 : 1,
                    borderColor: isDark ? '#1E293B' : '#ffffff'
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: {
                        position: 'right',
                        labels: {
                            color: textColor,
                            font: { family: 'Inter', size: 12, weight: 500 },
                            padding: 16,
                            usePointStyle: true,
                            pointStyleWidth: 10,
                        }
                    }
                },
                cutout: '65%'
            }
        });
    }

    // 2. Status Chart (Bar)
    const statusCanvas = document.getElementById('statusChart');
    if (statusCanvas) {
        if (statusChart) statusChart.destroy();

        const statusData = data.status_counts || {};
        const labels = ['Pending', 'Under Review', 'In Progress', 'Resolved', 'Rejected'];
        const values = labels.map(l => statusData[l] || 0);

        statusChart = new Chart(statusCanvas, {
            type: 'bar',
            data: {
                labels: labels,
                datasets: [{
                    label: 'Complaints',
                    data: values,
                    backgroundColor: [
                        yellowColor,    // Pending
                        violetColor,    // Under Review
                        cyanColor,      // In Progress
                        greenColor,     // Resolved
                        slateColor      // Rejected
                    ],
                    borderRadius: 8,
                    borderSkipped: false,
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    x: {
                        grid: { display: false },
                        ticks: {
                            color: textColor,
                            font: { family: 'Inter', size: 11, weight: 500 }
                        }
                    },
                    y: {
                        grid: { color: gridColor },
                        ticks: {
                            color: textColor,
                            font: { family: 'Inter', size: 11 },
                            precision: 0
                        }
                    }
                }
            }
        });
    }
}
