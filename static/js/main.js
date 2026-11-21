/**
 * StudyExchange Main JavaScript
 * Handles:
 * - Bootstrap form validation
 * - Submit button spinners
 * - Automated usage logging (clicks, form errors) via POST /api/event
 * - Test mode (task timer, click and error tracking across navigation)
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
        // 1. Bootstrap standard client validation
        const forms = document.querySelectorAll('.needs-validation');
        Array.prototype.slice.call(forms).forEach(function (form) {
            form.addEventListener('submit', function (event) {
                if (!form.checkValidity()) {
                    event.preventDefault();
                    event.stopPropagation();
                    // Increment task errors if task is running
                    TaskTracker.incrementErrors();
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

                    // Show spinner on submit button
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
    });

    // Make TaskTracker available globally
    window.TaskTracker = TaskTracker;
})();
