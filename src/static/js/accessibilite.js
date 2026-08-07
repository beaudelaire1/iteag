/* Compléments d'accessibilité qui doivent s'exécuter avant iteag.js. */
(function () {
  "use strict";

  const mouvementReduit = window.matchMedia("(prefers-reduced-motion: reduce)");

  /* iteag.js ajoute un défilement doux aux ancres. En mouvement réduit, ce
     gestionnaire en phase de capture prend la main avant lui et effectue le
     même déplacement sans animation. */
  document.addEventListener(
    "click",
    (evenement) => {
      if (!mouvementReduit.matches) return;
      const lien = evenement.target.closest('a[href^="#"]');
      if (!lien) return;
      const href = lien.getAttribute("href");
      if (!href || href === "#") return;

      let cible;
      try {
        cible = document.querySelector(href);
      } catch (erreur) {
        return;
      }
      if (!cible) return;

      evenement.preventDefault();
      evenement.stopImmediatePropagation();
      cible.scrollIntoView({ behavior: "auto", block: "start" });
      history.pushState(null, "", href);
    },
    true
  );
})();
