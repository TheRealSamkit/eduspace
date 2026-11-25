/**
 * EduSpace Document & Image Preview Modal Controller
 * Uses vendored pdf.js (3.11.174) for PDFs and native zoom/pan for images.
 */
(function () {
    'use strict';

    const WORKER_SRC = '/static/vendor/pdfjs/pdf.worker.min.js';
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

    function getEls() {
        return {
            modal: document.getElementById('previewModal'),
            dialog: document.getElementById('previewModalDialog'),
            title: document.getElementById('previewModalTitle'),
            lockedBanner: document.getElementById('previewLockedBanner'),
            unlockLink: document.getElementById('previewUnlockBtn'),
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

    function renderPdfPage(num) {
        if (!pdfDoc) return;
        const els = getEls();
        if (renderTask) {
            try { renderTask.cancel(); } catch (e) { }
        }
        pdfDoc.getPage(num).then(function (page) {
            const unscaled = page.getViewport({ scale: 1 });
            let scale = pdfScale;
            if (fitMode === 'width') {
                const avail = Math.max(300, els.pdfWrap.clientWidth - 32);
                scale = avail / unscaled.width;
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
        if (imgFit) {
            els.imgEl.style.maxWidth = '100%';
            els.imgEl.style.width = 'auto';
        } else {
            els.imgEl.style.maxWidth = 'none';
            const natW = els.imgEl.naturalWidth || 800;
            els.imgEl.style.width = Math.round(natW * imgScale) + 'px';
        }
    }

    function openPreview(trigger) {
        const els = getEls();
        if (!els.modal) return;
        lastTrigger = trigger;

        const fileId = trigger.dataset.fileId;
        const title = trigger.dataset.fileTitle || 'Document Preview';
        const ext = (trigger.dataset.fileExt || '').toLowerCase();
        const locked = trigger.dataset.locked === 'true';
        const previewUrl = `/preview/${encodeURIComponent(fileId)}`;
        const downloadUrl = `/download/${encodeURIComponent(fileId)}`;

        els.title.textContent = title;
        els.errorBox.classList.add('d-none');
        els.pdfWrap.classList.add('d-none');
        els.imgWrap.classList.add('d-none');
        els.pageControls.classList.add('d-none');
        els.spinner.classList.remove('d-none');
        els.unlockLink.href = downloadUrl;
        els.lockedBanner.classList.toggle('d-none', !locked);

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
            fetch(previewUrl, { credentials: 'same-origin' })
                .then(function (res) {
                    if (!res.ok) {
                        return res.json().catch(function () { return {}; }).then(function (d) {
                            throw new Error(d.error || 'Preview not available for this file.');
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
                    showError(err.message || 'Preview not available for this file.');
                });
        } else if (ext === 'png' || ext === 'jpg' || ext === 'jpeg') {
            activeKind = 'image';
            imgFit = true;
            imgScale = 1.0;
            els.btnZoom100.classList.remove('d-none');
            fetch(previewUrl, { credentials: 'same-origin' })
                .then(function (res) {
                    if (!res.ok) {
                        return res.json().catch(function () { return {}; }).then(function (d) {
                            throw new Error(d.error || 'Preview not available for this file.');
                        });
                    }
                    return res.blob();
                })
                .then(function (blob) {
                    const objUrl = URL.createObjectURL(blob);
                    els.imgEl.onload = function () {
                        URL.revokeObjectURL(objUrl);
                        els.spinner.classList.add('d-none');
                        els.imgWrap.classList.remove('d-none');
                        applyImageZoom();
                    };
                    els.imgEl.src = objUrl;
                })
                .catch(function (err) {
                    showError(err.message || 'Preview not available for this image.');
                });
        } else {
            activeKind = null;
            showError('Preview not available for this file type.');
        }
    }

    function toggleFullscreen() {
        const els = getEls();
        if (!els.modal) return;
        if (document.fullscreenElement) {
            document.exitFullscreen().catch(function () { });
            els.dialog.classList.remove('modal-fullscreen');
        } else if (els.modal.requestFullscreen) {
            els.modal.requestFullscreen().catch(function () {
                els.dialog.classList.toggle('modal-fullscreen');
            });
        } else {
            els.dialog.classList.toggle('modal-fullscreen');
        }
    }

    function cleanupModal() {
        const els = getEls();
        if (document.fullscreenElement && document.exitFullscreen) {
            document.exitFullscreen().catch(function () { });
        }
        if (els.dialog) {
            els.dialog.classList.remove('modal-fullscreen');
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
            els.imgEl.removeAttribute('src');
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
        els.modal.addEventListener('hidden.bs.modal', cleanupModal);

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
