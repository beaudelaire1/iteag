/* Valeurs de présentation dynamiques compatibles avec une CSP stricte.

   Le serveur transmet des données typées, jamais des déclarations CSS. Les
   seules écritures CSS autorisées ici sont une largeur bornée, un délai borné
   et une couleur hexadécimale validée. Les autres variations visuelles sont
   des états fermés qui ne font qu'ajouter des classes connues à l'avance. */
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

    scope.querySelectorAll("[data-pagination-state]").forEach((element) => {
      const courant = element.dataset.paginationState === "current";
      element.classList.toggle("pagination-current", courant);
      element.classList.toggle("pagination-available", !courant);
      if (courant) element.setAttribute("aria-current", "page");
    });

    scope.querySelectorAll("[data-question-choice-state]").forEach((element) => {
      const correct = element.dataset.questionChoiceState === "correct";
      element.classList.toggle("question-choice-correct", correct);
      element.classList.toggle("question-choice-neutral", !correct);
    });

    scope.querySelectorAll("[data-divider-state]").forEach((element) => {
      element.classList.toggle("conditional-divider", element.dataset.dividerState === "active");
    });

    scope.querySelectorAll("[data-deadline-state]").forEach((element) => {
      const urgent = element.dataset.deadlineState === "urgent";
      element.classList.toggle("deadline-urgent", urgent);
      element.classList.toggle("deadline-normal", !urgent);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => appliquer(document), { once: true });
  } else {
    appliquer(document);
  }

  document.addEventListener("htmx:afterSwap", (evenement) => appliquer(evenement.target));
})();
