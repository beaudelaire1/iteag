(() => {
  "use strict";

  function transformerNavigation(nav) {
    if (!nav || nav.dataset.portalNavReady === "true") return;
    const enfants = Array.from(nav.children);
    const groupes = enfants.filter((element) => element.classList.contains("portal-nav-group"));
    if (!groupes.length) return;

    const fragment = document.createDocumentFragment();
    let details = null;
    let liens = null;

    enfants.forEach((element) => {
      if (element.classList.contains("portal-nav-group")) {
        details = document.createElement("details");
        details.className = "portal-nav-section";

        const summary = document.createElement("summary");
        const libelle = document.createElement("span");
        libelle.textContent = element.textContent.trim();
        const chevron = document.createElement("span");
        chevron.className = "portal-nav-section-chevron";
        chevron.setAttribute("aria-hidden", "true");
        chevron.textContent = "⌄";
        summary.append(libelle, chevron);

        liens = document.createElement("div");
        liens.className = "portal-nav-section-links";
        details.append(summary, liens);
        fragment.append(details);
        element.remove();
        return;
      }

      if (liens) liens.append(element);
      else fragment.append(element);
    });

    nav.replaceChildren(fragment);
    const sections = Array.from(nav.querySelectorAll(".portal-nav-section"));
    sections.forEach((section, index) => {
      section.open = Boolean(section.querySelector(".portal-nav-link.active")) || index === 0;
      section.addEventListener("toggle", () => {
        if (!section.open) return;
        sections.forEach((autre) => {
          if (autre !== section && !autre.querySelector(".portal-nav-link.active")) autre.open = false;
        });
      });
    });
    nav.dataset.portalNavReady = "true";
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-portal-nav]").forEach(transformerNavigation);
  });
})();
