(() => {
  "use strict";
  const stage = document.querySelector("[data-image-stage]");
  const image = document.querySelector("[data-brochure-image]");
  if (!stage || !image) return;

  const label = document.querySelector("[data-image-zoom-label]");
  const steps = [50, 75, 100, 125, 150, 175, 200, 225, 250, 275, 300];
  let zoom = 100;

  const render = () => {
    stage.dataset.zoom = String(zoom);
    if (label) label.textContent = zoom + " %";
  };

  document.querySelectorAll("[data-image-zoom]").forEach((button) => {
    button.addEventListener("click", () => {
      const action = button.dataset.imageZoom;
      if (action === "reset") {
        zoom = 100;
        stage.scrollTo({ top: 0, left: 0, behavior: "smooth" });
      } else {
        const index = steps.indexOf(zoom);
        zoom = steps[Math.max(0, Math.min(steps.length - 1, index + (action === "in" ? 1 : -1)))];
      }
      render();
    });
  });

  const printButton = document.querySelector("[data-image-print]");
  if (printButton) printButton.addEventListener("click", () => window.print());
  render();
})();
