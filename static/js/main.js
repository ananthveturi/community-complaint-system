document.addEventListener('DOMContentLoaded', () => {
    initTheme();
    initAlerts();
    initImagePreviews();
    initAdminResolutionProofToggle();
    initLocationMapPreview();
});

function initTheme() {
    // Find all toggle buttons (there may be one in public nav and one in app nav)
    const themeToggles = document.querySelectorAll('#themeToggleBtn');
    if (themeToggles.length === 0) return;

    const savedTheme = localStorage.getItem('theme');
    const systemPrefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const currentTheme = savedTheme === 'dark' || (!savedTheme && systemPrefersDark) ? 'dark' : 'light';

    applyTheme(currentTheme);

    themeToggles.forEach(btn => {
        btn.addEventListener('click', () => {
            const isDark = document.documentElement.classList.contains('dark');
            const newTheme = isDark ? 'light' : 'dark';
            applyTheme(newTheme);
            localStorage.setItem('theme', newTheme);
        });
    });
}

function applyTheme(theme) {
    if (theme === 'dark') {
        document.documentElement.classList.add('dark');
        document.documentElement.setAttribute('data-theme', 'dark');
    } else {
        document.documentElement.classList.remove('dark');
        document.documentElement.setAttribute('data-theme', 'light');
    }
    // Update all toggle button icons
    document.querySelectorAll('#themeToggleBtn').forEach(btn => {
        updateThemeIcon(btn, theme);
    });
}

function updateThemeIcon(btn, theme) {
    const darkIcon = btn.querySelector('.theme-icon-dark');
    const lightIcon = btn.querySelector('.theme-icon-light');
    if (darkIcon && lightIcon) {
        if (theme === 'dark') {
            darkIcon.classList.add('hidden');
            lightIcon.classList.remove('hidden');
        } else {
            darkIcon.classList.remove('hidden');
            lightIcon.classList.add('hidden');
        }
    }
    btn.setAttribute('title', theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode');
}

function initAlerts() {
    document.querySelectorAll('.alert').forEach(alert => {
        setTimeout(() => dismissAlert(alert), 5000);
        const closeBtn = alert.querySelector('.alert-close');
        if (closeBtn) closeBtn.addEventListener('click', () => dismissAlert(alert));
    });
}

function dismissAlert(alert) {
    alert.classList.add('fade-out');
    setTimeout(() => alert.remove(), 260);
}

function initImagePreviews() {
    document.querySelectorAll('.file-upload-input').forEach(input => {
        const wrapper = input.closest('.file-upload-wrapper');
        const previewImg = wrapper ? wrapper.querySelector('.image-preview') : null;
        const uploadPlaceholder = wrapper ? wrapper.querySelector('.upload-placeholder') : null;
        if (!previewImg) return;

        input.addEventListener('change', function() {
            const file = this.files[0];
            if (!file) {
                previewImg.style.display = 'none';
                if (uploadPlaceholder) uploadPlaceholder.style.display = 'block';
                return;
            }

            const allowedTypes = ['image/png', 'image/jpeg', 'image/gif'];
            const maxBytes = 5 * 1024 * 1024;
            if (!allowedTypes.includes(file.type) || file.size > maxBytes) {
                this.value = '';
                previewImg.removeAttribute('src');
                previewImg.style.display = 'none';
                if (uploadPlaceholder) {
                    uploadPlaceholder.style.display = 'block';
                    uploadPlaceholder.innerHTML = '<div class="upload-icon">Upload failed</div><p style="font-weight: 800;">Use PNG, JPG, JPEG, or GIF under 5 MB.</p>';
                }
                return;
            }

            const reader = new FileReader();
            reader.addEventListener('load', function() {
                previewImg.setAttribute('src', this.result);
                previewImg.style.display = 'block';
                if (uploadPlaceholder) uploadPlaceholder.style.display = 'none';
            });
            reader.readAsDataURL(file);
        });
    });
}

function initAdminResolutionProofToggle() {
    const statusSelect = document.getElementById('admin-status-select');
    const resolutionProofGroup = document.getElementById('resolution-proof-group');
    const resolutionProofInput = document.getElementById('resolution_proof');
    if (!statusSelect || !resolutionProofGroup || !resolutionProofInput) return;

    const toggleProof = () => {
        const resolving = statusSelect.value === 'Resolved';
        resolutionProofGroup.style.display = resolving ? 'block' : 'none';
        if (resolving) {
            resolutionProofInput.setAttribute('required', 'required');
        } else {
            resolutionProofInput.removeAttribute('required');
        }
    };

    statusSelect.addEventListener('change', toggleProof);
    toggleProof();
}

function initLocationMapPreview() {
    const locationInput = document.getElementById('location');
    const mapFrame = document.getElementById('google-map-preview');
    const latitudeInput = document.getElementById('latitude');
    const longitudeInput = document.getElementById('longitude');
    const currentLocationBtn = document.getElementById('use-current-location');
    const mapStatus = document.getElementById('map-status');
    if (!locationInput || !mapFrame) return;

    const setMapByQuery = (query) => {
        const safeQuery = encodeURIComponent(query || 'India');
        mapFrame.src = `https://www.google.com/maps?q=${safeQuery}&output=embed`;
    };

    let debounceTimer = null;
    locationInput.addEventListener('input', () => {
        if (latitudeInput) latitudeInput.value = '';
        if (longitudeInput) longitudeInput.value = '';
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            setMapByQuery(locationInput.value.trim());
            if (mapStatus) mapStatus.textContent = 'Map preview updated from the typed landmark. Use GPS for higher accuracy.';
        }, 650);
    });

    if (!currentLocationBtn || !navigator.geolocation) return;

    currentLocationBtn.addEventListener('click', () => {
        if (mapStatus) mapStatus.textContent = 'Requesting browser location permission...';
        navigator.geolocation.getCurrentPosition(
            (position) => {
                const lat = position.coords.latitude.toFixed(7);
                const lng = position.coords.longitude.toFixed(7);
                if (latitudeInput) latitudeInput.value = lat;
                if (longitudeInput) longitudeInput.value = lng;
                setMapByQuery(`${lat},${lng}`);
                if (!locationInput.value.trim()) {
                    locationInput.value = `GPS location: ${lat}, ${lng}`;
                }
                if (mapStatus) mapStatus.textContent = `GPS captured: ${lat}, ${lng}. Admin will see the exact Google Maps point.`;
            },
            () => {
                if (mapStatus) mapStatus.textContent = 'Location permission was not allowed. You can still type a landmark manually.';
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 60000 }
        );
    });
}
