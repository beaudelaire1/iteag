/* Indique qu'une page contient encore du contenu sous la zone visible. */
(function () {
  "use strict";

  function initIndicateurDefilement() {
    const bouton = document.querySelector("[data-indicateur-defilement]");
    if (!bouton || bouton.dataset.indicateurInit === "1") return;

    bouton.dataset.indicateurInit = "1";
    const mouvementReduit = window.matchMedia("(prefers-reduced-motion: reduce)");
    let raf = null;

    function hauteurVisible() {
      return window.visualViewport
        ? window.visualViewport.height
        : document.documentElement.clientHeight;
    }

    function mettreAJour() {
      raf = null;
      const racine = document.documentElement;
      const hauteur = hauteurVisible();
      const position = window.scrollY || racine.scrollTop || 0;
      const reste = racine.scrollHeight - (position + hauteur);

      // Quelques pixels de tolérance évitent un clignotement au voisinage du bas.
      bouton.hidden = reste <= 56;
    }

    function demanderMiseAJour() {
      if (raf !== null) return;
      raf = window.requestAnimationFrame(mettreAJour);
    }

    bouton.addEventListener("click", function () {
      const distance = Math.max(Math.round(hauteurVisible() * 0.78), 320);
      window.scrollBy({
        top: distance,
        left: 0,
        behavior: mouvementReduit.matches ? "auto" : "smooth",
      });
    });

    window.addEventListener("scroll", demanderMiseAJour, { passive: true });
    window.addEventListener("resize", demanderMiseAJour, { passive: true });

    if (window.visualViewport) {
      window.visualViewport.addEventListener("resize", demanderMiseAJour, { passive: true });
      window.visualViewport.addEventListener("scroll", demanderMiseAJour, { passive: true });
    }

    if ("ResizeObserver" in window && document.body) {
      const observateur = new ResizeObserver(demanderMiseAJour);
      observateur.observe(document.body);
      const principal = document.getElementById("main-content");
      if (principal) observateur.observe(principal);
    }

    document.body.addEventListener("htmx:afterSwap", demanderMiseAJour);
    mettreAJour();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initIndicateurDefilement);
  } else {
    initIndicateurDefilement();
  }
})();
