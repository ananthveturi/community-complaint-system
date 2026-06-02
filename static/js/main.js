// Main Javascript for Community Complaint System

document.addEventListener('DOMContentLoaded', () => {
    // 1. Theme Toggle Functionality
    initTheme();

    // 2. Flash Alert Auto-Dismiss
    initAlerts();

    // 3. Image File Upload Preview
    initImagePreviews();
});

/**
 * Initialize and handle Dark/Light theme toggle
 */
function initTheme() {
    const themeToggleBtn = document.getElementById('themeToggleBtn');
    if (!themeToggleBtn) return;

    // Check saved theme or system preference
    const savedTheme = localStorage.getItem('theme');
    const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    
    let currentTheme = 'light';
    if (savedTheme === 'dark' || (!savedTheme && systemPrefersDark)) {
        currentTheme = 'dark';
    }

    // Set initial theme
    document.documentElement.setAttribute('data-theme', currentTheme);
    updateThemeIcon(themeToggleBtn, currentTheme);

    // Toggle click handler
    themeToggleBtn.addEventListener('click', () => {
        const activeTheme = document.documentElement.getAttribute('data-theme');
        const newTheme = activeTheme === 'dark' ? 'light' : 'dark';
        
        document.documentElement.setAttribute('data-theme', newTheme);
        localStorage.setItem('theme', newTheme);
        updateThemeIcon(themeToggleBtn, newTheme);
    });
}

function updateThemeIcon(btn, theme) {
    if (theme === 'dark') {
        btn.innerHTML = '☀️'; // Sun icon for light mode switch
        btn.setAttribute('title', 'Switch to Light Mode');
    } else {
        btn.innerHTML = '🌙'; // Moon icon for dark mode switch
        btn.setAttribute('title', 'Switch to Dark Mode');
    }
}

/**
 * Handle auto-dismissal of flash notifications after 5 seconds
 */
function initAlerts() {
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        // Set auto-dismiss timer
        setTimeout(() => {
            dismissAlert(alert);
        }, 5000);

        // Close button click handler
        const closeBtn = alert.querySelector('.alert-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                dismissAlert(alert);
            });
        }
    });
}

function dismissAlert(alert) {
    alert.classList.add('fade-out');
    alert.addEventListener('animationend', () => {
        alert.remove();
    });
}

/**
 * Set up dynamic previews for file upload inputs
 */
function initImagePreviews() {
    // Look for all instances of upload inputs (e.g. citizen file complaint, admin resolve)
    const fileInputs = document.querySelectorAll('.file-upload-input');
    
    fileInputs.forEach(input => {
        const previewImg = input.closest('.form-group').querySelector('.image-preview');
        const uploadPlaceholder = input.closest('.file-upload-wrapper').querySelector('.upload-placeholder');
        
        if (!previewImg) return;
        
        input.addEventListener('change', function() {
            const file = this.files[0];
            if (file) {
                const reader = new FileReader();
                reader.addEventListener('load', function() {
                    previewImg.setAttribute('src', this.result);
                    previewImg.style.display = 'block';
                    if (uploadPlaceholder) {
                        uploadPlaceholder.style.display = 'none';
                    }
                });
                reader.readAsDataURL(file);
            } else {
                previewImg.style.display = 'none';
                if (uploadPlaceholder) {
                    uploadPlaceholder.style.display = 'block';
                }
            }
        });
    });
}

/**
 * Admin Action Selection Listener: Toggle file upload requirements dynamically
 * When status is set to "Resolved", show and require the solution proof image.
 */
const statusSelect = document.getElementById('admin-status-select');
const resolutionProofGroup = document.getElementById('resolution-proof-group');
const resolutionProofInput = document.getElementById('resolution_proof');

if (statusSelect && resolutionProofGroup && resolutionProofInput) {
    statusSelect.addEventListener('change', function() {
        if (this.value === 'Resolved') {
            resolutionProofGroup.style.display = 'block';
            resolutionProofInput.setAttribute('required', 'required');
        } else {
            resolutionProofGroup.style.display = 'none';
            resolutionProofInput.removeAttribute('required');
        }
    });
    
    // Initial check (in case it is pre-selected)
    if (statusSelect.value === 'Resolved') {
        resolutionProofGroup.style.display = 'block';
        resolutionProofInput.setAttribute('required', 'required');
    }
}
