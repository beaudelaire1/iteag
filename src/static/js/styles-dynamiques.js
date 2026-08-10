/* Valeurs de présentation dynamiques compatibles avec une CSP stricte.

   Le serveur transmet des données, jamais des déclarations CSS. Ce module ne
   sait appliquer que trois propriétés précisément autorisées et valide leur
   domaine avant de toucher à CSSOM :
   - pourcentage de largeur : nombre borné entre 0 et 100 ;
   - délai de transition : entier borné entre 0 et 2000 ms ;
   - couleur de groupe : hexadécimal #RRGGBB uniquement.

   Aucun nom de propriété ni fragment CSS ne vient de l'utilisateur. */
(function () {
  "use strict";

  function nombreBorne(valeur, minimum, maximum) {
    const nombre = Number.parseFloat(String(valeur ?? "").trim());
    if (!Number.isFinite(nombre)) return null;
    return Math.min(maximum, Math.max(minimum, nombre));
  }

  function appliquer(racine) {
    const scope = racine || document;

    scope.querySelectorAll("[data-progress-width]").forEach((element) => {
      const pourcentage = nombreBorne(element.dataset.progressWidth, 0, 100);
      if (pourcentage === null) return;
      element.style.width = `${pourcentage}%`;
      if (!element.hasAttribute("aria-valuenow")) {
        element.setAttribute("aria-valuenow", String(Math.round(pourcentage)));
      }
    });

    scope.querySelectorAll("[data-transition-delay]").forEach((element) => {
      const delai = nombreBorne(element.dataset.transitionDelay, 0, 2000);
      if (delai === null) return;
      element.style.transitionDelay = `${Math.round(delai)}ms`;
    });

    scope.querySelectorAll("[data-background-color]").forEach((element) => {
      const couleur = String(element.dataset.backgroundColor || "").trim();
      if (!/^#[0-9a-fA-F]{6}$/.test(couleur)) return;
      element.style.backgroundColor = couleur;
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => appliquer(document), { once: true });
  } else {
    appliquer(document);
  }

  document.addEventListener("htmx:afterSwap", (evenement) => appliquer(evenement.target));
})();
