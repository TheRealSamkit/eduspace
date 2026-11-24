/**
 * EduSpace Toast Notification Manager
 * 
 * Provides:
 * - window.showToast(message, category)
 * - Auto-hide timing: success/info 4s, warning 6s, danger 8s
 * - Pause on hover and focus
 * - Max 3 visible toasts with queued overflow
 * - Study-safe: clicks do not count towards Test Mode telemetry
 */

(function () {
    'use strict';

    const MAX_VISIBLE_TOASTS = 3;
    const toastQueue = [];
    let visibleToastCount = 0;

    const CATEGORY_MAP = {
        success: {
            bg: 'text-bg-success',
            icon: 'ti-circle-check',
            role: 'status',
            live: 'polite',
            delay: 4000,
            closeClass: 'btn-close-white'
        },
        info: {
            bg: 'text-bg-info',
            icon: 'ti-info-circle',
            role: 'status',
            live: 'polite',
            delay: 4000,
            closeClass: ''
        },
        warning: {
            bg: 'text-bg-warning',
            icon: 'ti-alert-triangle',
            role: 'alert',
            live: 'assertive',
            delay: 6000,
            closeClass: ''
        },
        danger: {
            bg: 'text-bg-danger',
            icon: 'ti-alert-circle',
            role: 'alert',
            live: 'assertive',
            delay: 8000,
            closeClass: 'btn-close-white'
        },
        error: {
            bg: 'text-bg-danger',
            icon: 'ti-alert-circle',
            role: 'alert',
            live: 'assertive',
            delay: 8000,
            closeClass: 'btn-close-white'
        }
    };

    function getContainer() {
        let container = document.getElementById('toastContainer');
        if (!container) {
            container = document.createElement('div');
            container.id = 'toastContainer';
            container.className = 'toast-container position-fixed';
            container.setAttribute('aria-live', 'polite');
            container.setAttribute('aria-atomic', 'true');
            document.body.appendChild(container);
        }
        return container;
    }

    function createToastElement(message, category) {
        const catKey = (category && CATEGORY_MAP[category]) ? category : 'info';
        const config = CATEGORY_MAP[catKey];

        const toast = document.createElement('div');
        toast.className = `toast align-items-center border-0 ${config.bg} mb-2 shadow-sm`;
        toast.setAttribute('role', config.role);
        toast.setAttribute('aria-live', config.live);
        toast.setAttribute('aria-atomic', 'true');
        toast.dataset.category = catKey;
        toast.dataset.delay = config.delay;

        const flex = document.createElement('div');
        flex.className = 'd-flex';

        const body = document.createElement('div');
        body.className = 'toast-body d-flex align-items-center gap-2';

        const icon = document.createElement('i');
        icon.className = `ti ${config.icon} fs-5 flex-shrink-0`;
        icon.setAttribute('aria-hidden', 'true');

        const textDiv = document.createElement('div');
        textDiv.className = 'toast-message-text';
        textDiv.textContent = message;

        body.appendChild(icon);
        body.appendChild(textDiv);

        const closeBtn = document.createElement('button');
        closeBtn.type = 'button';
        closeBtn.className = `btn-close ${config.closeClass} me-2 m-auto`;
        closeBtn.setAttribute('data-bs-dismiss', 'toast');
        closeBtn.setAttribute('aria-label', 'Close');

        flex.appendChild(body);
        flex.appendChild(closeBtn);
        toast.appendChild(flex);

        return toast;
    }

    function setupToastLifecycle(toastEl, delay) {
        let timerId = null;
        let startTime = Date.now();
        let remainingTime = delay;
        let isPaused = false;

        const bsToast = new bootstrap.Toast(toastEl, { autohide: false });

        function startTimer() {
            if (isPaused) return;
            startTime = Date.now();
            timerId = setTimeout(function () {
                bsToast.hide();
            }, remainingTime);
        }

        function pauseTimer() {
            if (timerId) {
                clearTimeout(timerId);
                timerId = null;
                const elapsed = Date.now() - startTime;
                remainingTime = Math.max(1000, remainingTime - elapsed);
                isPaused = true;
            }
        }

        function resumeTimer() {
            if (isPaused) {
                isPaused = false;
                startTimer();
            }
        }

        toastEl.addEventListener('mouseenter', pauseTimer);
        toastEl.addEventListener('mouseleave', resumeTimer);
        toastEl.addEventListener('focusin', pauseTimer);
        toastEl.addEventListener('focusout', resumeTimer);

        toastEl.addEventListener('hidden.bs.toast', function () {
            if (timerId) clearTimeout(timerId);
            toastEl.remove();
            visibleToastCount = Math.max(0, visibleToastCount - 1);
            processQueue();
        });

        visibleToastCount++;
        bsToast.show();
        startTimer();
    }

    function processQueue() {
        const container = getContainer();
        while (visibleToastCount < MAX_VISIBLE_TOASTS && toastQueue.length > 0) {
            const item = toastQueue.shift();
            let toastEl;
            let delay;

            if (item.element) {
                toastEl = item.element;
                delay = parseInt(toastEl.dataset.delay || toastEl.dataset.bsDelay || '4000', 10);
            } else {
                toastEl = createToastElement(item.message, item.category);
                container.appendChild(toastEl);
                delay = parseInt(toastEl.dataset.delay, 10);
            }

            setupToastLifecycle(toastEl, delay);
        }
    }

    window.showToast = function (message, category) {
        if (!message) return;
        toastQueue.push({ message: String(message), category: category || 'info' });
        processQueue();
    };

    window.dismissTopToast = function () {
        const container = document.getElementById('toastContainer');
        if (!container) return false;
        const visibleToast = container.querySelector('.toast.show');
        if (visibleToast) {
            const inst = bootstrap.Toast.getInstance(visibleToast);
            if (inst) {
                inst.hide();
                return true;
            }
        }
        return false;
    };

    // Initialize pre-rendered server toasts on DOM ready
    document.addEventListener('DOMContentLoaded', function () {
        const container = document.getElementById('toastContainer');
        if (container) {
            const serverToasts = Array.from(container.querySelectorAll('.toast'));
            serverToasts.forEach(function (toastEl) {
                const cat = toastEl.dataset.category || 'info';
                const delay = parseInt(toastEl.dataset.delay || toastEl.dataset.bsDelay || '4000', 10);
                toastQueue.push({ element: toastEl, category: cat, delay: delay });
            });
            processQueue();
        }
    });
})();
