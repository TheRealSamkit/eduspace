/**
 * EduSpace Keyboard Shortcuts and Help Modal
 * 
 * Single source of truth driving:
 * (a) Keyboard event routing & sequence handling (G then key)
 * (b) Dynamic shortcut help modal
 * (c) Research safety gating during active evaluation tasks
 */

(function () {
    'use strict';

    // Single source of truth for all application shortcuts
    const SHORTCUTS_DEF = [
        {
            key: 'g b',
            sequence: ['g', 'b'],
            keysDisplay: ['G', 'B'],
            group: 'Navigation',
            description: 'Browse repository',
            tooltip: 'Browse (G then B)',
            targetShortcut: 'g b',
            adminOnly: false
        },
        {
            key: 'g u',
            sequence: ['g', 'u'],
            keysDisplay: ['G', 'U'],
            group: 'Navigation',
            description: 'Upload study material',
            tooltip: 'Upload (G then U)',
            targetShortcut: 'g u',
            adminOnly: false
        },
        {
            key: 'g d',
            sequence: ['g', 'd'],
            keysDisplay: ['G', 'D'],
            group: 'Navigation',
            description: 'Personal dashboard',
            tooltip: 'Dashboard (G then D)',
            targetShortcut: 'g d',
            adminOnly: false
        },
        {
            key: 'g t',
            sequence: ['g', 't'],
            keysDisplay: ['G', 'T'],
            group: 'Navigation',
            description: 'Test mode (timed tasks)',
            tooltip: 'Test Mode (G then T)',
            targetShortcut: 'g t',
            adminOnly: false
        },
        {
            key: 'g s',
            sequence: ['g', 's'],
            keysDisplay: ['G', 'S'],
            group: 'Navigation',
            description: 'System Usability Scale survey',
            tooltip: 'SUS Survey (G then S)',
            targetShortcut: 'g s',
            adminOnly: false
        },
        {
            key: 'g f',
            sequence: ['g', 'f'],
            keysDisplay: ['G', 'F'],
            group: 'Navigation',
            description: 'Usability feedback',
            tooltip: 'Feedback (G then F)',
            targetShortcut: 'g f',
            adminOnly: false
        },
        {
            key: 'g a',
            sequence: ['g', 'a'],
            keysDisplay: ['G', 'A'],
            group: 'Navigation',
            description: 'Admin moderation panel',
            tooltip: 'Admin Panel (G then A)',
            targetShortcut: 'g a',
            adminOnly: true
        },
        {
            key: 'g l',
            sequence: ['g', 'l'],
            keysDisplay: ['G', 'L'],
            group: 'Navigation',
            description: 'Baseline study data entry',
            tooltip: 'Baseline Data (G then L)',
            targetShortcut: 'g l',
            adminOnly: true
        },
        {
            key: 't',
            keysDisplay: ['T'],
            group: 'Interface',
            description: 'Toggle light / dark theme',
            tooltip: 'Toggle theme (T)',
            handler: 'toggleTheme',
            adminOnly: false
        },
        {
            key: '/',
            keysDisplay: ['/'],
            group: 'Interface',
            description: 'Focus search field (Browse page)',
            tooltip: 'Press / to search',
            handler: 'focusSearch',
            adminOnly: false
        },
        {
            key: '?',
            keysDisplay: ['?'],
            group: 'Interface',
            description: 'Keyboard shortcuts help modal',
            tooltip: 'Keyboard shortcuts (?)',
            handler: 'showHelp',
            adminOnly: false
        },
        {
            key: 'Escape',
            keysDisplay: ['Esc'],
            group: 'Interface',
            description: 'Close dialog / dismiss active toast',
            tooltip: 'Dismiss (Esc)',
            handler: 'dismiss',
            adminOnly: false
        }
    ];

    window.SHORTCUTS_DEF = SHORTCUTS_DEF;

    let pendingG = false;
    let pendingTimer = null;
    let taskDisabledToastShown = false;
    let lastActiveElement = null;

    function isInsideEditableOrInput(e) {
        const active = document.activeElement;
        if (!active) return false;
        const tag = active.tagName.toLowerCase();
        if (['input', 'textarea', 'select'].includes(tag)) return true;
        if (active.isContentEditable) return true;
        if (active.closest('dialog') || active.closest('.modal')) {
            if (['input', 'textarea', 'select'].includes(tag)) return true;
        }
        return false;
    }

    function isTaskActive() {
        if (window.TaskTracker && typeof window.TaskTracker.get === 'function') {
            const task = window.TaskTracker.get();
            if (task) return true;
        }
        const banner = document.getElementById('task-active-banner');
        return !!(banner && banner.style.display !== 'none');
    }

    function getPendingHintEl() {
        let el = document.getElementById('shortcut-pending-hint');
        if (!el) {
            el = document.createElement('div');
            el.id = 'shortcut-pending-hint';
            el.className = 'position-fixed bottom-0 start-0 m-3 px-3 py-2 bg-body border rounded-3 shadow-sm small text-body';
            el.style.zIndex = '1090';
            el.style.display = 'none';
            el.innerHTML = '<kbd class="border px-1 me-1">G</kbd> <span class="text-body-secondary">then B, U, D, T, S, F...</span>';
            document.body.appendChild(el);
        }
        return el;
    }

    function showPendingHint() {
        const hint = getPendingHintEl();
        hint.style.display = 'block';
    }

    function hidePendingHint() {
        const hint = document.getElementById('shortcut-pending-hint');
        if (hint) {
            hint.style.display = 'none';
        }
    }

    function triggerNavigation(shortcutKey) {
        const link = document.querySelector(`[data-shortcut="${shortcutKey}"]`);
        if (link && link.href) {
            if (window.logEvent) {
                window.logEvent('shortcut', window.location.pathname, shortcutKey);
            }
            window.location.href = link.href;
            return true;
        }
        return false;
    }

    function buildShortcutsModal() {
        let modalEl = document.getElementById('shortcutsHelpModal');
        if (modalEl) return modalEl;

        const isAdmin = !!document.querySelector('[data-shortcut="g a"]');
        const groups = ['Navigation', 'Interface'];

        modalEl = document.createElement('div');
        modalEl.className = 'modal fade';
        modalEl.id = 'shortcutsHelpModal';
        modalEl.tabIndex = -1;
        modalEl.setAttribute('aria-labelledby', 'shortcutsModalTitle');
        modalEl.setAttribute('aria-hidden', 'true');

        let rowsHtml = '';
        groups.forEach(function (groupName) {
            rowsHtml += `<tr><th colspan="2" class="bg-body-tertiary text-uppercase text-body-secondary small fw-semibold py-2 px-3">${groupName}</th></tr>`;
            SHORTCUTS_DEF.filter(function (s) {
                return s.group === groupName && (!s.adminOnly || isAdmin);
            }).forEach(function (s) {
                const kbdHtml = s.keysDisplay.map(function (k) {
                    return `<kbd class="border px-2 py-1 mx-1">${k}</kbd>`;
                }).join('');
                rowsHtml += `
                    <tr>
                        <td class="text-nowrap ps-3 py-2" style="width: 140px;">${kbdHtml}</td>
                        <td class="text-body-secondary pe-3 py-2 small">${s.description}</td>
                    </tr>
                `;
            });
        });

        modalEl.innerHTML = `
            <div class="modal-dialog modal-dialog-centered">
                <div class="modal-content shadow">
                    <div class="modal-header py-3 px-4 border-bottom">
                        <h2 class="modal-title h6 fw-semibold text-body mb-0" id="shortcutsModalTitle">
                            <i class="ti ti-keyboard me-2 fs-5" aria-hidden="true"></i>Keyboard shortcuts
                        </h2>
                        <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
                    </div>
                    <div class="modal-body p-0">
                        <div class="table-responsive">
                            <table class="table table-hover align-middle mb-0">
                                <tbody>
                                    ${rowsHtml}
                                </tbody>
                            </table>
                        </div>
                    </div>
                    <div class="modal-footer py-2 px-4 bg-body-tertiary">
                        <span class="small text-body-secondary">Press <kbd class="border px-1">Esc</kbd> to close</span>
                        <button type="button" class="btn btn-sm btn-outline-secondary ms-auto" data-bs-dismiss="modal">Close</button>
                    </div>
                </div>
            </div>
        `;

        document.body.appendChild(modalEl);

        modalEl.addEventListener('hidden.bs.modal', function () {
            if (lastActiveElement && typeof lastActiveElement.focus === 'function') {
                lastActiveElement.focus();
            }
        });

        return modalEl;
    }

    function openHelpModal() {
        lastActiveElement = document.activeElement;
        const modalEl = buildShortcutsModal();
        const bsModal = bootstrap.Modal.getOrCreateInstance(modalEl);
        bsModal.show();
        if (window.logEvent) {
            window.logEvent('shortcut', window.location.pathname, '?');
        }
    }

    function closeHelpModal() {
        const modalEl = document.getElementById('shortcutsHelpModal');
        if (modalEl && modalEl.classList.contains('show')) {
            const bsModal = bootstrap.Modal.getInstance(modalEl);
            if (bsModal) {
                bsModal.hide();
                return true;
            }
        }
        return false;
    }

    document.addEventListener('keydown', function (e) {
        // Ignore with modifier keys (Ctrl, Alt, Meta)
        if (e.ctrlKey || e.altKey || e.metaKey) {
            return;
        }

        // Ignore auto-repeat
        if (e.repeat) {
            return;
        }

        // Ignore when typing inside form fields, inputs, contenteditable
        if (isInsideEditableOrInput(e)) {
            // Still allow Esc inside form fields if not closed by native dialog
            if (e.key === 'Escape') {
                if (closeHelpModal()) {
                    e.preventDefault();
                } else if (window.dismissTopToast && window.dismissTopToast()) {
                    e.preventDefault();
                }
            }
            return;
        }

        const key = e.key;
        const isLoggedIn = !!document.querySelector('.app-sidebar');

        // Escape handler: close modal or dismiss top toast
        if (key === 'Escape') {
            if (pendingG) {
                pendingG = false;
                clearTimeout(pendingTimer);
                hidePendingHint();
                e.preventDefault();
                return;
            }
            if (closeHelpModal()) {
                e.preventDefault();
                return;
            }
            if (window.dismissTopToast && window.dismissTopToast()) {
                e.preventDefault();
                return;
            }
            return;
        }

        // Help Modal (?)
        if (key === '?' || (key === '/' && e.shiftKey)) {
            e.preventDefault();
            openHelpModal();
            return;
        }

        // Theme toggle (T or t) - available to all (logged in and guests)
        if (key === 't' || key === 'T') {
            if (pendingG) {
                // If G was pressed, G T means Test Mode!
                // Fall through to sequence logic below
            } else {
                e.preventDefault();
                if (window.toggleTheme) {
                    window.toggleTheme();
                    if (window.logEvent) {
                        window.logEvent('shortcut', window.location.pathname, 't');
                    }
                }
                return;
            }
        }

        // Research Validity Check: Disable navigation shortcuts & '/' during active Test Mode
        if (isTaskActive()) {
            if (key === '/' || key === 'g' || key === 'G' || pendingG) {
                e.preventDefault();
                if (pendingG) {
                    pendingG = false;
                    clearTimeout(pendingTimer);
                    hidePendingHint();
                }
                if (!taskDisabledToastShown && window.showToast) {
                    window.showToast('Keyboard shortcuts are disabled during test tasks.', 'warning');
                    taskDisabledToastShown = true;
                }
                return;
            }
        }

        // Search field focus (/) on Browse page
        if (key === '/') {
            const searchField = document.querySelector('input[name="q"], #browseSearchInput, #searchQuery');
            if (searchField) {
                e.preventDefault();
                searchField.focus();
                searchField.select();
                if (window.logEvent) {
                    window.logEvent('shortcut', window.location.pathname, '/');
                }
            }
            return;
        }

        // Navigation two-key sequence: G then [B, U, D, T, S, F, A, L]
        if (!isLoggedIn) {
            // Guests only get T and ?
            return;
        }

        if (!pendingG) {
            if (key === 'g' || key === 'G') {
                pendingG = true;
                showPendingHint();
                pendingTimer = setTimeout(function () {
                    pendingG = false;
                    hidePendingHint();
                }, 1500);
            }
        } else {
            // Second key of sequence pressed
            pendingG = false;
            clearTimeout(pendingTimer);
            hidePendingHint();

            const secondKey = key.toLowerCase();
            const seqKey = 'g ' + secondKey;
            const executed = triggerNavigation(seqKey);
            if (executed) {
                e.preventDefault();
            }
        }
    });

    document.addEventListener('DOMContentLoaded', function () {
        // Build help modal on demand or when dropdown item is clicked
        const modalTrigger = document.getElementById('btn-shortcuts-modal');
        if (modalTrigger) {
            modalTrigger.addEventListener('click', function (e) {
                e.preventDefault();
                openHelpModal();
            });
        }
    });
})();
