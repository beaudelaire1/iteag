import { getDocument, GlobalWorkerOptions } from "./vendor/pdf.min.mjs";

(() => {
  "use strict";

  const root = document.querySelector("[data-pdf-viewer]");
  const stage = document.querySelector("[data-pdf-stage]");
  const spread = document.querySelector("[data-pdf-spread]");
  if (!root || !stage || !spread) return;

  const previous = root.querySelector("[data-pdf-prev]");
  const next = root.querySelector("[data-pdf-next]");
  const pageLabel = root.querySelector("[data-pdf-page-count]");
  const zoomLabel = root.querySelector("[data-pdf-zoom-label]");
  const errorMessage = stage.querySelector("[data-pdf-error]");

  GlobalWorkerOptions.workerSrc = new URL("./vendor/pdf.worker.min.mjs", import.meta.url).href;

  let documentPdf = null;
  let currentPage = 1;
  let zoomFactor = 1;
  let renderTasks = [];
  let renderSequence = 0;
  let resizeTimer = null;
  let pageObserver = null;
  let canvases = [];

  function cancelRendering() {
    renderTasks.forEach((task) => {
      try { task.cancel(); } catch (_) { /* tâche déjà terminée */ }
    });
    renderTasks = [];
  }

  function updateControls() {
    if (!documentPdf) return;
    pageLabel.textContent = `Page ${currentPage} / ${documentPdf.numPages}`;
    previous.disabled = currentPage <= 1;
    next.disabled = currentPage >= documentPdf.numPages;
    zoomLabel.textContent = `${Math.round(zoomFactor * 100)} %`;
  }

  function goToPage(pageNumber) {
    if (!documentPdf) return;
    currentPage = Math.max(1, Math.min(documentPdf.numPages, pageNumber));
    canvases[currentPage - 1]?.scrollIntoView({ behavior: "smooth", block: "start" });
    updateControls();
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

  async function renderDocument() {
    if (!documentPdf) return;
    const sequence = ++renderSequence;
    cancelRendering();
    errorMessage.hidden = true;
    spread.hidden = false;

    try {
      const pages = await Promise.all(
        Array.from({ length: documentPdf.numPages }, (_, index) => documentPdf.getPage(index + 1)),
      );
      if (sequence !== renderSequence) return;

      const maxPageWidth = Math.max(...pages.map((page) => page.getViewport({ scale: 1 }).width));
      const availableWidth = Math.max(240, stage.clientWidth - 48);
      const fitScale = Math.min(availableWidth / maxPageWidth, 1.8);
      const scale = fitScale * zoomFactor;

      if (pageObserver) pageObserver.disconnect();
      spread.replaceChildren();
      canvases = pages.map((_, index) => {
        const canvas = document.createElement("canvas");
        canvas.className = "brochure-pdf-page";
        canvas.setAttribute("aria-label", `Page PDF ${index + 1}`);
        spread.appendChild(canvas);
        return canvas;
      });

      pageObserver = new IntersectionObserver((entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (visible) {
          currentPage = Number(visible.target.dataset.pageNumber);
          updateControls();
        }
      }, { root: stage, threshold: [0.25, 0.5, 0.75] });

      canvases.forEach((canvas, index) => {
        canvas.dataset.pageNumber = String(index + 1);
        pageObserver.observe(canvas);
      });

      for (let index = 0; index < canvases.length; index += 1) {
        if (sequence !== renderSequence) return;
        await renderPage(index + 1, canvases[index], scale, sequence);
      }

      if (sequence === renderSequence) {
        currentPage = Math.min(currentPage, documentPdf.numPages);
        updateControls();
      }
    } catch (error) {
      if (sequence !== renderSequence) return;
      console.error("Erreur de lecture PDF :", error);
      spread.hidden = true;
      errorMessage.hidden = false;
    }
  }

  previous.addEventListener("click", () => goToPage(currentPage - 1));
  next.addEventListener("click", () => goToPage(currentPage + 1));

  root.querySelector("[data-pdf-zoom-in]").addEventListener("click", () => {
    zoomFactor = Math.min(2.5, Math.round((zoomFactor + 0.15) * 100) / 100);
    renderDocument();
  });
  root.querySelector("[data-pdf-zoom-out]").addEventListener("click", () => {
    zoomFactor = Math.max(0.5, Math.round((zoomFactor - 0.15) * 100) / 100);
    renderDocument();
  });
  root.querySelector("[data-pdf-fit]").addEventListener("click", () => {
    zoomFactor = 1;
    renderDocument();
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
    if (event.key === "ArrowDown" || event.key === "ArrowRight") goToPage(currentPage + 1);
    if (event.key === "ArrowUp" || event.key === "ArrowLeft") goToPage(currentPage - 1);
  });

  const observer = new ResizeObserver(() => {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(renderDocument, 180);
  });
  observer.observe(stage);

  getDocument({
    url: root.dataset.pdfUrl,
    withCredentials: true,
    cMapUrl: new URL("./vendor/pdfjs-cmaps/", import.meta.url).href,
    cMapPacked: true,
    standardFontDataUrl: new URL("./vendor/pdfjs-standard-fonts/", import.meta.url).href,
  }).promise.then((pdf) => {
    documentPdf = pdf;
    currentPage = 1;
    updateControls();
    return renderDocument();
  }).catch((error) => {
    console.error("Impossible de charger la brochure PDF :", error);
    spread.hidden = true;
    errorMessage.hidden = false;
    pageLabel.textContent = "Lecture indisponible";
  });

  window.addEventListener("pagehide", () => {
    cancelRendering();
    observer.disconnect();
    if (pageObserver) pageObserver.disconnect();
    if (documentPdf) documentPdf.destroy();
  }, { once: true });
})();
