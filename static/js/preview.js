/**
 * EduSpace Document & Image Viewer Modal Controller
 * Uses vendored pdf.js (3.11.174) for PDFs and native zoom/fit for images.
 */
(function () {
    'use strict';

    const WORKER_SRC = '/static/vendor/pdfjs/pdf.worker.min.js';
    const MAX_FIT_SCALE = 2.2;
    let pdfDoc = null;
    let currentPage = 1;
    let totalPages = 1;
    let pdfScale = 1.0;
    let fitMode = 'width';
    let imgScale = 1.0;
    let imgFit = true;
    let activeKind = null;
    let lastTrigger = null;
    let renderTask = null;
    let resizeTimer = null;

    function getEls() {
        return {
            modal: document.getElementById('previewModal'),
            dialog: document.getElementById('previewModalDialog'),
            body: document.getElementById('previewModalBody'),
            title: document.getElementById('previewModalTitle'),
            spinner: document.getElementById('previewLoading'),
            errorBox: document.getElementById('previewError'),
            errorMsg: document.getElementById('previewErrorMsg'),
            pdfWrap: document.getElementById('previewPdfWrap'),
            canvas: document.getElementById('previewPdfCanvas'),
            imgWrap: document.getElementById('previewImgWrap'),
            imgEl: document.getElementById('previewImgEl'),
            pageControls: document.getElementById('previewPageControls'),
            pageIndicator: document.getElementById('previewPageIndicator'),
            btnPrev: document.getElementById('previewPrevPage'),
            btnNext: document.getElementById('previewNextPage'),
            btnZoomOut: document.getElementById('previewZoomOut'),
            btnZoomIn: document.getElementById('previewZoomIn'),
            btnZoomFit: document.getElementById('previewZoomFit'),
            btnZoom100: document.getElementById('previewZoom100'),
            btnFullscreen: document.getElementById('previewFullscreenBtn')
        };
    }

    function canUseFullscreenApi(modalEl) {
        return Boolean(
            modalEl &&
            typeof modalEl.requestFullscreen === 'function' &&
            document.fullscreenEnabled !== false
        );
    }

    function showError(msg) {
        const els = getEls();
        els.spinner.classList.add('d-none');
        els.pdfWrap.classList.add('d-none');
        els.imgWrap.classList.add('d-none');
        els.pageControls.classList.add('d-none');
        els.errorMsg.textContent = msg;
        els.errorBox.classList.remove('d-none');
    }

    function updatePageIndicator() {
        const els = getEls();
        els.pageIndicator.textContent = `Page ${currentPage} of ${totalPages}`;
        els.btnPrev.disabled = currentPage <= 1;
        els.btnNext.disabled = currentPage >= totalPages;
    }

    function getAvailableWidth(els) {
        const wrapW = els.pdfWrap && els.pdfWrap.clientWidth ? els.pdfWrap.clientWidth : 0;
        const bodyW = els.body && els.body.clientWidth ? els.body.clientWidth : 0;
        const dialogW = els.dialog && els.dialog.clientWidth ? els.dialog.clientWidth : 0;
        const raw = wrapW || bodyW || dialogW || 720;
        return Math.max(280, raw - 32);
    }

    function renderPdfPage(num) {
        if (!pdfDoc) return;
        const els = getEls();
        if (renderTask) {
            try { renderTask.cancel(); } catch (e) { }
        }
        els.pdfWrap.classList.remove('d-none');
        pdfDoc.getPage(num).then(function (page) {
            const unscaled = page.getViewport({ scale: 1 });
            let scale = pdfScale;
            if (fitMode === 'width') {
                const avail = getAvailableWidth(els);
                scale = Math.min(MAX_FIT_SCALE, Math.max(0.5, avail / unscaled.width));
                pdfScale = scale;
            }
            const dpr = window.devicePixelRatio || 1;
            const viewport = page.getViewport({ scale: scale });
            const canvas = els.canvas;
            const ctx = canvas.getContext('2d');
            canvas.width = Math.floor(viewport.width * dpr);
            canvas.height = Math.floor(viewport.height * dpr);
            canvas.style.width = Math.floor(viewport.width) + 'px';
            canvas.style.height = Math.floor(viewport.height) + 'px';
            ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

            renderTask = page.render({ canvasContext: ctx, viewport: viewport });
            return renderTask.promise;
        }).then(function () {
            els.spinner.classList.add('d-none');
            els.pdfWrap.classList.remove('d-none');
            updatePageIndicator();
        }).catch(function (err) {
            if (err && err.name === 'RenderingCancelledException') return;
            showError('Could not render PDF page.');
        });
    }

    function applyImageZoom() {
        const els = getEls();
        const imgEl = els.imgEl;
        if (!imgEl) return;
        if (imgFit) {
            imgEl.style.maxWidth = '100%';
            const bodyH = els.body && els.body.clientHeight ? Math.max(240, els.body.clientHeight - 32) : 0;
            imgEl.style.maxHeight = bodyH ? bodyH + 'px' : '75vh';
            imgEl.style.width = 'auto';
            imgEl.style.height = 'auto';
        } else {
            imgEl.style.maxWidth = 'none';
            imgEl.style.maxHeight = 'none';
            const natW = imgEl.naturalWidth || 800;
            imgEl.style.width = Math.round(natW * imgScale) + 'px';
            imgEl.style.height = 'auto';
        }
    }

    function refitActiveContent() {
        if (activeKind === 'pdf' && pdfDoc && fitMode === 'width') {
            renderPdfPage(currentPage);
        } else if (activeKind === 'image' && imgFit) {
            applyImageZoom();
        }
    }

    function syncFullscreenUI(isFs) {
        const els = getEls();
        if (!els.modal) return;
        els.modal.classList.toggle('viewer-modal-fs', isFs);
        if (els.btnFullscreen) {
            els.btnFullscreen.setAttribute('aria-pressed', isFs ? 'true' : 'false');
            const icon = els.btnFullscreen.querySelector('i.ti');
            if (icon) {
                icon.classList.toggle('ti-maximize', !isFs);
                icon.classList.toggle('ti-minimize', isFs);
            }
        }
        requestAnimationFrame(function () {
            refitActiveContent();
        });
    }

    function openPreview(trigger) {
        const els = getEls();
        if (!els.modal) return;
        lastTrigger = trigger;

        const fileId = trigger.dataset.fileId;
        const title = trigger.dataset.fileTitle || 'View file';
        const ext = (trigger.dataset.fileExt || '').toLowerCase();
        const viewUrl = `/view/${encodeURIComponent(fileId)}`;

        els.title.textContent = title;
        els.errorBox.classList.add('d-none');
        els.pdfWrap.classList.add('d-none');
        els.imgWrap.classList.add('d-none');
        els.pageControls.classList.add('d-none');
        els.spinner.classList.remove('d-none');

        const bsModal = bootstrap.Modal.getOrCreateInstance(els.modal);
        bsModal.show();

        if (ext === 'pdf') {
            activeKind = 'pdf';
            els.btnZoom100.classList.add('d-none');
            if (!window.pdfjsLib) {
                showError('PDF viewer library failed to load.');
                return;
            }
            window.pdfjsLib.GlobalWorkerOptions.workerSrc = WORKER_SRC;
            fetch(viewUrl, { credentials: 'same-origin' })
                .then(function (res) {
                    if (!res.ok) {
                        return res.json().catch(function () { return {}; }).then(function (d) {
                            throw new Error(d.error || 'View not available for this file.');
                        });
                    }
                    return res.arrayBuffer();
                })
                .then(function (buf) {
                    return window.pdfjsLib.getDocument({ data: buf }).promise;
                })
                .then(function (doc) {
                    pdfDoc = doc;
                    totalPages = doc.numPages;
                    currentPage = 1;
                    fitMode = 'width';
                    els.pageControls.classList.remove('d-none');
                    renderPdfPage(currentPage);
                })
                .catch(function (err) {
                    showError(err.message || 'View not available for this file.');
                });
        } else if (ext === 'png' || ext === 'jpg' || ext === 'jpeg') {
            activeKind = 'image';
            imgFit = true;
            imgScale = 1.0;
            els.btnZoom100.classList.remove('d-none');
            fetch(viewUrl, { credentials: 'same-origin' })
                .then(function (res) {
                    if (!res.ok) {
                        return res.json().catch(function () { return {}; }).then(function (d) {
                            throw new Error(d.error || 'View not available for this file.');
                        });
                    }
                    return res.blob();
                })
                .then(function (blob) {
                    const objUrl = URL.createObjectURL(blob);
                    let imgEl = document.getElementById('previewImgEl');
                    if (!imgEl) {
                        imgEl = document.createElement('img');
                        imgEl.id = 'previewImgEl';
                        imgEl.alt = title;
                        imgEl.className = 'border shadow-sm';
                        els.imgWrap.appendChild(imgEl);
                    }
                    imgEl.onload = function () {
                        URL.revokeObjectURL(objUrl);
                        els.spinner.classList.add('d-none');
                        els.imgWrap.classList.remove('d-none');
                        applyImageZoom();
                    };
                    imgEl.src = objUrl;
                })
                .catch(function (err) {
                    showError(err.message || 'View not available for this image.');
                });
        } else {
            activeKind = null;
            showError('View not available for this file type.');
        }
    }

    function toggleFullscreen() {
        const els = getEls();
        if (!els.modal) return;
        if (canUseFullscreenApi(els.modal)) {
            if (document.fullscreenElement === els.modal) {
                document.exitFullscreen().catch(function () {
                    syncFullscreenUI(false);
                });
            } else {
                els.modal.requestFullscreen().catch(function () {
                    syncFullscreenUI(!els.modal.classList.contains('viewer-modal-fs'));
                });
            }
        } else {
            syncFullscreenUI(!els.modal.classList.contains('viewer-modal-fs'));
        }
    }

    function cleanupModal() {
        const els = getEls();
        if (document.fullscreenElement === els.modal && typeof document.exitFullscreen === 'function') {
            document.exitFullscreen().catch(function () { });
        }
        syncFullscreenUI(false);
        if (renderTask) {
            try { renderTask.cancel(); } catch (e) { }
            renderTask = null;
        }
        if (pdfDoc) {
            try { pdfDoc.destroy(); } catch (e) { }
            pdfDoc = null;
        }
        if (els.canvas) {
            els.canvas.width = 0;
            els.canvas.height = 0;
        }
        if (els.imgEl) {
            els.imgEl.remove();
        }
        activeKind = null;
        if (lastTrigger && typeof lastTrigger.focus === 'function') {
            lastTrigger.focus();
            lastTrigger = null;
        }
    }

    document.addEventListener('DOMContentLoaded', function () {
        const els = getEls();
        if (!els.modal) return;

        document.addEventListener('click', function (e) {
            const trigger = e.target.closest('.btn-preview');
            if (trigger) {
                e.preventDefault();
                openPreview(trigger);
            }
        });

        els.btnPrev.addEventListener('click', function () {
            if (activeKind === 'pdf' && currentPage > 1) {
                currentPage--;
                renderPdfPage(currentPage);
            }
        });
        els.btnNext.addEventListener('click', function () {
            if (activeKind === 'pdf' && currentPage < totalPages) {
                currentPage++;
                renderPdfPage(currentPage);
            }
        });
        els.btnZoomIn.addEventListener('click', function () {
            if (activeKind === 'pdf') {
                fitMode = 'custom';
                pdfScale = Math.min(3.0, pdfScale + 0.25);
                renderPdfPage(currentPage);
            } else if (activeKind === 'image') {
                imgFit = false;
                imgScale = Math.min(3.0, imgScale + 0.25);
                applyImageZoom();
            }
        });
        els.btnZoomOut.addEventListener('click', function () {
            if (activeKind === 'pdf') {
                fitMode = 'custom';
                pdfScale = Math.max(0.4, pdfScale - 0.25);
                renderPdfPage(currentPage);
            } else if (activeKind === 'image') {
                imgFit = false;
                imgScale = Math.max(0.25, imgScale - 0.25);
                applyImageZoom();
            }
        });
        els.btnZoomFit.addEventListener('click', function () {
            if (activeKind === 'pdf') {
                fitMode = 'width';
                renderPdfPage(currentPage);
            } else if (activeKind === 'image') {
                imgFit = true;
                applyImageZoom();
            }
        });
        els.btnZoom100.addEventListener('click', function () {
            if (activeKind === 'image') {
                imgFit = false;
                imgScale = 1.0;
                applyImageZoom();
            }
        });
        els.btnFullscreen.addEventListener('click', toggleFullscreen);

        // Track fullscreen state via fullscreenchange event
        document.addEventListener('fullscreenchange', function () {
            syncFullscreenUI(document.fullscreenElement === els.modal);
        });

        // Re-fit when modal finishes opening (accurate container width)
        els.modal.addEventListener('shown.bs.modal', function () {
            refitActiveContent();
        });

        els.modal.addEventListener('hidden.bs.modal', cleanupModal);

        // Re-fit on window resize when fit mode is active
        window.addEventListener('resize', function () {
            if (!els.modal.classList.contains('show')) return;
            clearTimeout(resizeTimer);
            resizeTimer = setTimeout(refitActiveContent, 100);
        });

        // Capture Escape when in browser fullscreen so first Esc exits fullscreen only
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && document.fullscreenElement === els.modal) {
                e.stopPropagation();
                return;
            }
        }, true);

        document.addEventListener('keydown', function (e) {
            if (!els.modal.classList.contains('show')) return;
            if (e.ctrlKey || e.altKey || e.metaKey) return;
            if (e.key === 'ArrowLeft') {
                e.preventDefault();
                els.btnPrev.click();
            } else if (e.key === 'ArrowRight') {
                e.preventDefault();
                els.btnNext.click();
            } else if (e.key === '+' || e.key === '=') {
                e.preventDefault();
                els.btnZoomIn.click();
            } else if (e.key === '-') {
                e.preventDefault();
                els.btnZoomOut.click();
            } else if (e.key === 'f' || e.key === 'F') {
                e.preventDefault();
                toggleFullscreen();
            }
        });
    });
})();
