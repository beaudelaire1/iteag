/* Capture les erreurs de chargement avant les dépendances Wagtail.

   Cette trace courte permet à l'adaptateur final d'activer un champ de repli
   au lieu de laisser une zone de rédaction invisible. */
(function () {
  "use strict";
  window.iteagDraftailErrors = [];
  // Draftail 6.4 utilise par défaut une barre flottante, visible seulement
  // après sélection. Dans un formulaire métier cela ressemble à un champ
  // dépourvu d'éditeur. Le mode « sticky » est prévu par Draftail lui-même et
  // garde les commandes au-dessus de la zone dès son ouverture.
  try {
    window.localStorage.setItem("wagtail:draftail-toolbar", "sticky");
  } catch (_erreur) {
    // Le stockage peut être interdit en navigation privée ; Draftail reste
    // alors utilisable via le bouton + et la commande « / ».
  }
  window.addEventListener("error", function (evenement) {
    window.iteagDraftailErrors.push({
      message: evenement.message || "Erreur de chargement",
      source: evenement.filename || "",
      ligne: evenement.lineno || 0,
    });
  });
})();
