/**
 * StudyExchange Main JavaScript
 * Handles:
 * - Bootstrap form validation (without double-submission)
 * - Submit button spinners
 * - Automated usage logging (clicks, form errors) via POST /api/event
 * - Test mode (task timer, click and error tracking across navigation)
 * - Live credit UI sync (/api/credits)
 * - Client-side dark mode theme toggle (localStorage)
 */

(function () {
    'use strict';

    // CSRF helper
    function getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    // API Event logger
    window.logEvent = function (eventType, page, detail) {
        try {
            fetch('/api/event', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': getCsrfToken()
                },
                body: JSON.stringify({
                    event_type: eventType,
                    page: page || window.location.pathname,
                    detail: typeof detail === 'object' ? JSON.stringify(detail) : String(detail || '')
                })
            }).catch(function (err) {
                // Silently swallow network errors for analytics logging
            });
        } catch (e) {
            // ignore
        }
    };

    // Credit UI real-time sync
    window.updateCreditUI = function (credits) {
        document.querySelectorAll('.credit-balance-val').forEach(function (el) {
            el.textContent = credits;
        });
    };

    window.refreshCredits = function () {
        fetch('/api/credits')
            .then(function (res) { return res.json(); })
            .then(function (data) {
                if (data && typeof data.credits === 'number') {
                    window.updateCreditUI(data.credits);
                }
            })
            .catch(function () {});
    };

    // Sync theme toggle icons with current data-bs-theme
    function syncThemeIcons() {
        const currentTheme = document.documentElement.getAttribute('data-bs-theme') || 'light';
        document.querySelectorAll('.theme-toggle-icon').forEach(function (icon) {
            if (currentTheme === 'dark') {
                icon.classList.remove('ti-moon');
                icon.classList.add('ti-sun');
            } else {
                icon.classList.remove('ti-sun');
                icon.classList.add('ti-moon');
            }
        });
    }

    // Theme Toggle Handler via localStorage (Zero server round-trip)
    window.toggleTheme = function () {
        const html = document.documentElement;
        const currentTheme = html.getAttribute('data-bs-theme') || 'light';
        const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
        html.setAttribute('data-bs-theme', newTheme);
        try {
            localStorage.setItem('theme', newTheme);
        } catch (e) {}
        syncThemeIcons();
    };

    // --- Task Test Mode Tracker ---
    const TASK_STORAGE_KEY = 'studyexchange_active_task';

    window.TaskTracker = {
        get: function () {
            try {
                const data = localStorage.getItem(TASK_STORAGE_KEY);
                return data ? JSON.parse(data) : null;
            } catch (e) {
                return null;
            }
        },
        start: function (taskName) {
            const task = {
                task_name: taskName,
                started_at: Date.now(),
                clicks: 0,
                errors: 0
            };
            localStorage.setItem(TASK_STORAGE_KEY, JSON.stringify(task));
            this.updateBanner();
        },
        incrementClicks: function () {
            const task = this.get();
            if (task) {
                task.clicks = (task.clicks || 0) + 1;
                localStorage.setItem(TASK_STORAGE_KEY, JSON.stringify(task));
                this.updateBanner();
            }
        },
        incrementErrors: function () {
            const task = this.get();
            if (task) {
                task.errors = (task.errors || 0) + 1;
                localStorage.setItem(TASK_STORAGE_KEY, JSON.stringify(task));
                this.updateBanner();
            }
        },
        finish: function (success) {
            const task = this.get();
            if (!task) return null;
            const durationSec = Math.max(1, Math.round((Date.now() - task.started_at) / 1000));
            const result = {
                task_name: task.task_name,
                started_at: new Date(task.started_at).toISOString(),
                ended_at: new Date().toISOString(),
                duration_sec: durationSec,
                clicks: task.clicks,
                errors: task.errors,
                success: success ? 1 : 0
            };
            localStorage.removeItem(TASK_STORAGE_KEY);
            this.updateBanner();
            return result;
        },
        cancel: function () {
            localStorage.removeItem(TASK_STORAGE_KEY);
            this.updateBanner();
        },
        updateBanner: function () {
            const banner = document.getElementById('task-active-banner');
            if (!banner) return;
            const task = this.get();
            if (task) {
                banner.style.display = 'block';
                const taskNameEl = document.getElementById('task-banner-name');
                const taskClicksEl = document.getElementById('task-banner-clicks');
                const taskErrorsEl = document.getElementById('task-banner-errors');
                if (taskNameEl) taskNameEl.textContent = task.task_name;
                if (taskClicksEl) taskClicksEl.textContent = task.clicks || 0;
                if (taskErrorsEl) taskErrorsEl.textContent = task.errors || 0;
            } else {
                banner.style.display = 'none';
            }
        }
    };

    // Document Ready setup
    document.addEventListener('DOMContentLoaded', function () {
        // Sync theme icons immediately on DOM ready
        syncThemeIcons();

        // 1. Bootstrap standard client validation
        const forms = document.querySelectorAll('.needs-validation');
        Array.prototype.slice.call(forms).forEach(function (form) {
            form.addEventListener('submit', function (event) {
                if (!form.checkValidity()) {
                    event.preventDefault();
                    event.stopPropagation();
                    // Increment task errors if task is running
                    TaskTracker.incrementErrors();
                    if (window.showToast) {
                        window.showToast('Please correct the highlighted form fields before submitting.', 'warning');
                    }
                    // Log error event
                    const invalidFields = Array.from(form.querySelectorAll(':invalid'))
                        .map(function (el) { return el.name || el.id; });
                    window.logEvent('validation_error', window.location.pathname, { fields: invalidFields });
                } else {
                    // Prevent accidental double submissions
                    if (form.dataset.submitting === 'true') {
                        event.preventDefault();
                        return;
                    }
                    form.dataset.submitting = 'true';

                    // Show spinner on submit button without re-triggering submit
                    const submitBtn = form.querySelector('button[type="submit"]');
                    if (submitBtn && !submitBtn.dataset.noSpinner) {
                        submitBtn.classList.add('disabled');
                        submitBtn.setAttribute('aria-busy', 'true');
                        submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2" role="status" aria-hidden="true"></span>Processing...';
                    }
                }
                form.classList.add('was-validated');
            }, false);
        });

        // 2. Global click tracking (debounced for UI performance)
        let clickBatch = 0;
        let clickTimer = null;
        document.addEventListener('click', function (e) {
            // Clicks on toasts (including close button) must NOT be counted by Test Mode tracker
            if (e.target.closest('.toast') || e.target.closest('.toast-container')) {
                return;
            }
            // Check if clicking inside interactive elements
            const target = e.target.closest('a, button, input[type="submit"], .clickable');
            if (target) {
                TaskTracker.incrementClicks();
                clickBatch++;
                if (!clickTimer) {
                    clickTimer = setTimeout(function () {
                        if (clickBatch > 0) {
                            window.logEvent('user_click', window.location.pathname, { count: clickBatch, last_target: target.tagName });
                            clickBatch = 0;
                        }
                        clickTimer = null;
                    }, 2000);
                }

                // If downloading a file, schedule instant credit chip sync
                const href = target.getAttribute('href') || '';
                if (href.indexOf('/download/') !== -1) {
                    setTimeout(window.refreshCredits, 600);
                    setTimeout(window.refreshCredits, 2000);
                }
            }
        });

        // 3. Initialize task banner state
        TaskTracker.updateBanner();

        // 4. Star rating widget helper (sync radio input with hover/click)
        const ratingInputs = document.querySelectorAll('.star-rating-input input');
        ratingInputs.forEach(function (radio) {
            radio.addEventListener('change', function () {
                const label = document.getElementById('selected-star-text');
                if (label) {
                    label.textContent = radio.value + ' star' + (radio.value > 1 ? 's' : '');
                }
            });
        });

        // 5. Theme toggle buttons listener
        document.querySelectorAll('.btn-theme-toggle').forEach(function (btn) {
            btn.addEventListener('click', function (e) {
                e.preventDefault();
                window.toggleTheme();
            });
        });

        // 6. Accessible Bootstrap tooltips initialization (hover-capable devices only)
        let tooltipInstances = [];
        function initTooltips() {
            if (!window.matchMedia('(hover: hover)').matches) return;
            const triggerList = Array.from(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
            tooltipInstances = triggerList.map(function (el) {
                return new bootstrap.Tooltip(el, {
                    trigger: 'hover focus',
                    delay: { show: 400, hide: 0 },
                    container: 'body'
                });
            });
        }
        initTooltips();

        // Dismiss tooltip immediately when its target is clicked
        document.addEventListener('click', function (e) {
            const el = e.target.closest('[data-bs-toggle="tooltip"]');
            if (el) {
                const inst = bootstrap.Tooltip.getInstance(el);
                if (inst) inst.hide();
            }
        });

        window.addEventListener('pagehide', function () {
            tooltipInstances.forEach(function (t) {
                try { t.dispose(); } catch (e) {}
            });
            tooltipInstances = [];
        });
    });

    // Make TaskTracker available globally
    window.TaskTracker = TaskTracker;
})();
