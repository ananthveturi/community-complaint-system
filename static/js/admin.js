// Admin Dashboard Charts using Chart.js

let categoryChart = null;
let statusChart = null;

document.addEventListener('DOMContentLoaded', () => {
    const statsContainer = document.getElementById('admin-charts-container');
    if (!statsContainer) return;

    // Fetch and render data
    loadDashboardStats();

    // Listen to theme changes to redraw charts with correct font colors
    const themeToggleBtn = document.getElementById('themeToggleBtn');
    if (themeToggleBtn) {
        themeToggleBtn.addEventListener('click', () => {
            // Wait slightly for DOM to update theme attribute
            setTimeout(() => {
                loadDashboardStats();
            }, 100);
        });
    }
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
 * Render/Update Chart.js instances
 */
function renderCharts(data) {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    const textColor = isDark ? '#cbd5e1' : '#475569';
    const gridColor = isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.05)';
    
    // Theme Colors
    const primaryColor = isDark ? '#6366f1' : '#4f46e5';
    const successColor = isDark ? '#34d399' : '#10b981';
    const warningColor = isDark ? '#fbbf24' : '#f59e0b';
    const dangerColor = isDark ? '#f87171' : '#ef4444';
    const infoColor = isDark ? '#22d3ee' : '#06b6d4';

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
                        primaryColor,
                        infoColor,
                        successColor,
                        warningColor,
                        dangerColor,
                        '#8b5cf6',
                        '#ec4899'
                    ],
                    borderWidth: isDark ? 2 : 1,
                    borderColor: isDark ? '#1e293b' : '#ffffff'
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
                            font: { family: 'Outfit', size: 12 }
                        }
                    }
                }
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
                        dangerColor,  // Pending
                        infoColor,    // Under Review
                        primaryColor, // In Progress
                        successColor, // Resolved
                        '#64748b'     // Rejected
                    ],
                    borderRadius: 6
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
                            font: { family: 'Outfit', size: 12 }
                        }
                    },
                    y: {
                        grid: { color: gridColor },
                        ticks: {
                            color: textColor,
                            font: { family: 'Outfit', size: 12 },
                            precision: 0
                        }
                    }
                }
            }
        });
    }
}
