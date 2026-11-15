import { getDocument, GlobalWorkerOptions } from "./vendor/pdf.min.mjs";

(() => {
  "use strict";

  const root = document.querySelector("[data-pdf-viewer]");
  const stage = document.querySelector("[data-pdf-stage]");
  const spread = document.querySelector("[data-pdf-spread]");
  if (!root || !stage || !spread) return;

  const canvases = {
    left: spread.querySelector('[data-pdf-canvas="left"]'),
    right: spread.querySelector('[data-pdf-canvas="right"]'),
  };
  const previous = root.querySelector("[data-pdf-prev]");
  const next = root.querySelector("[data-pdf-next]");
  const pageLabel = root.querySelector("[data-pdf-page-count]");
  const zoomLabel = root.querySelector("[data-pdf-zoom-label]");
  const errorMessage = stage.querySelector("[data-pdf-error]");
  const mobileQuery = window.matchMedia("(max-width: 760px)");

  GlobalWorkerOptions.workerSrc = new URL("./vendor/pdf.worker.min.mjs", import.meta.url).href;

  let documentPdf = null;
  let firstPage = 1;
  let zoomFactor = 1;
  let fitScale = 1;
  let renderTasks = [];
  let renderSequence = 0;
  let resizeTimer = null;

  const isMobile = () => mobileQuery.matches;
  const pagesPerView = () => (isMobile() ? 1 : 2);

  function cancelRendering() {
    renderTasks.forEach((task) => {
      try { task.cancel(); } catch (_) { /* tâche déjà terminée */ }
    });
    renderTasks = [];
  }

  function updateControls() {
    const lastPage = Math.min(documentPdf.numPages, firstPage + pagesPerView() - 1);
    pageLabel.textContent = lastPage === firstPage
      ? `Page ${firstPage} / ${documentPdf.numPages}`
      : `Pages ${firstPage}–${lastPage} / ${documentPdf.numPages}`;
    previous.disabled = firstPage <= 1;
    next.disabled = firstPage + pagesPerView() > documentPdf.numPages;
    zoomLabel.textContent = `${Math.round(zoomFactor * 100)} %`;
  }

  async function renderPage(pageNumber, canvas, scale, sequence) {
    const page = await documentPdf.getPage(pageNumber);
    if (sequence !== renderSequence) return;
    const viewport = page.getViewport({ scale });
    const pixelRatio = Math.min(window.devicePixelRatio || 1, 2.5);
    const context = canvas.getContext("2d", { alpha: false });

    canvas.width = Math.ceil(viewport.width * pixelRatio);
    canvas.height = Math.ceil(viewport.height * pixelRatio);
    canvas.style.width = `${Math.ceil(viewport.width)}px`;
    canvas.style.height = `${Math.ceil(viewport.height)}px`;

    const task = page.render({
      canvasContext: context,
      viewport,
      transform: pixelRatio === 1 ? null : [pixelRatio, 0, 0, pixelRatio, 0, 0],
      background: "#ffffff",
    });
    renderTasks.push(task);
    try {
      await task.promise;
    } catch (error) {
      if (error?.name !== "RenderingCancelledException") throw error;
    }
  }

  async function renderSpread() {
    if (!documentPdf) return;
    const sequence = ++renderSequence;
    cancelRendering();
    errorMessage.hidden = true;
    spread.hidden = false;

    const count = pagesPerView();
    const pageNumbers = Array.from(
      { length: count },
      (_, index) => firstPage + index,
    ).filter((number) => number <= documentPdf.numPages);

    const pages = await Promise.all(pageNumbers.map((number) => documentPdf.getPage(number)));
    if (sequence !== renderSequence) return;

    const widths = pages.map((page) => page.getViewport({ scale: 1 }).width);
    const heights = pages.map((page) => page.getViewport({ scale: 1 }).height);
    const availableWidth = Math.max(240, stage.clientWidth - (count === 2 ? 64 : 32));
    const availableHeight = Math.max(300, stage.clientHeight - 40);
    const totalPageWidth = widths.reduce((sum, width) => sum + width, 0);
    const maxPageHeight = Math.max(...heights);
    fitScale = Math.min(
      availableWidth / totalPageWidth,
      availableHeight / maxPageHeight,
      1.8,
    );
    const scale = fitScale * zoomFactor;

    canvases.left.hidden = false;
    canvases.right.hidden = count === 1 || pageNumbers.length < 2;
    spread.classList.toggle("is-single-page", count === 1);

    try {
      await renderPage(pageNumbers[0], canvases.left, scale, sequence);
      if (pageNumbers[1] && sequence === renderSequence) {
        await renderPage(pageNumbers[1], canvases.right, scale, sequence);
      }
      if (sequence === renderSequence) updateControls();
    } catch (error) {
      if (sequence !== renderSequence) return;
      console.error("Erreur de lecture PDF :", error);
      spread.hidden = true;
      errorMessage.hidden = false;
    }
  }

  function movePage(direction) {
    const step = pagesPerView();
    firstPage = Math.max(
      1,
      Math.min(documentPdf.numPages, firstPage + direction * step),
    );
    if (step === 2 && firstPage > 1) firstPage = Math.min(firstPage, Math.max(1, documentPdf.numPages - 1));
    renderSpread();
  }

  previous.addEventListener("click", () => movePage(-1));
  next.addEventListener("click", () => movePage(1));

  root.querySelector("[data-pdf-zoom-in]").addEventListener("click", () => {
    zoomFactor = Math.min(2.5, Math.round((zoomFactor + 0.15) * 100) / 100);
    renderSpread();
  });
  root.querySelector("[data-pdf-zoom-out]").addEventListener("click", () => {
    zoomFactor = Math.max(0.5, Math.round((zoomFactor - 0.15) * 100) / 100);
    renderSpread();
  });
  root.querySelector("[data-pdf-fit]").addEventListener("click", () => {
    zoomFactor = 1;
    renderSpread();
  });
  root.querySelector("[data-pdf-fullscreen]").addEventListener("click", async () => {
    try {
      if (!document.fullscreenElement) await stage.requestFullscreen();
      else await document.exitFullscreen();
    } catch (error) {
      console.warn("Plein écran indisponible :", error);
    }
  });

  document.addEventListener("keydown", (event) => {
    if (!documentPdf || event.altKey || event.ctrlKey || event.metaKey) return;
    if (event.key === "ArrowRight") movePage(1);
    if (event.key === "ArrowLeft") movePage(-1);
  });

  const observer = new ResizeObserver(() => {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(renderSpread, 120);
  });
  observer.observe(stage);
  mobileQuery.addEventListener("change", () => {
    firstPage = Math.max(1, firstPage);
    renderSpread();
  });

  getDocument({
    url: root.dataset.pdfUrl,
    withCredentials: true,
    cMapUrl: new URL("./vendor/pdfjs-cmaps/", import.meta.url).href,
    cMapPacked: true,
    standardFontDataUrl: new URL("./vendor/pdfjs-standard-fonts/", import.meta.url).href,
    wasmUrl: new URL("./vendor/pdfjs-wasm/", import.meta.url).href,
  }).promise.then((pdf) => {
    documentPdf = pdf;
    firstPage = 1;
    updateControls();
    return renderSpread();
  }).catch((error) => {
    console.error("Impossible de charger la brochure PDF :", error);
    spread.hidden = true;
    errorMessage.hidden = false;
    pageLabel.textContent = "Lecture indisponible";
  });

  window.addEventListener("pagehide", () => {
    cancelRendering();
    observer.disconnect();
    if (documentPdf) documentPdf.destroy();
  }, { once: true });
})();
