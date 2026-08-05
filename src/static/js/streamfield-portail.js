/* Amorçage des champs StreamField hors de l'administration Wagtail.

   Dans l'admin, un contrôleur Stimulus « w-block » construit le champ à partir
   des attributs « data-w-block-* ». Les portails ne chargent pas Stimulus : le
   « div » restait donc un div, aucun champ n'était créé, et l'envoi du
   formulaire partait sans « corps-count ». Le serveur levait alors une
   « MultiValueDictKeyError » — un 500 pour un formulaire simplement vide.

   Ce script fait ce que ferait le contrôleur, et rien de plus : il dépaquette
   la définition du bloc via telepath, puis demande au bloc de se rendre dans
   son emplacement. Même approche que « draftail-portail.js », qui émet à la
   main l'événement que Stimulus émettrait. */
(function () {
  "use strict";

  const SELECTEUR = '[data-block][data-controller="w-block"]';

  function amorcer(emplacement) {
    if (emplacement.dataset.blocPortailAmorce) return;

    // Sans telepath, rien à tenter : le champ resterait à moitié construit,
    // ce qui est pire qu'un champ absent — on croirait pouvoir écrire.
    if (!window.telepath || !window.telepath.unpack) {
      console.error("StreamField : telepath n'est pas chargé, le champ reste inerte.");
      return;
    }

    let definition;
    let arguments_;
    try {
      definition = window.telepath.unpack(JSON.parse(emplacement.dataset.wBlockDataValue));
      arguments_ = JSON.parse(emplacement.dataset.wBlockArgumentsValue || "[]");
    } catch (erreur) {
      console.error("StreamField : configuration illisible", erreur);
      return;
    }

    emplacement.dataset.blocPortailAmorce = "1";

    /* « render » attend (emplacement, préfixe, état initial, erreurs), mais
       « data-w-block-arguments-value » ne porte que les deux derniers — il vaut
       « [[], null] ». Le préfixe vient de l'identifiant de l'élément : c'est le
       nom du champ, celui qui donnera « corps-count », « corps-0-type », etc.

       L'oublier ne lève rien : le préfixe devenait le tableau vide, les champs
       naissaient sous des noms absurdes, et la zone restait visuellement vide —
       un intitulé « Compte rendu des débats » sans rien dessous. */
    definition.render(emplacement, emplacement.id, ...arguments_);
  }

  function demarrer(racine) {
    (racine || document).querySelectorAll(SELECTEUR).forEach(amorcer);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => demarrer(document), { once: true });
  } else {
    demarrer(document);
  }
  document.addEventListener("htmx:afterSwap", (evenement) => demarrer(evenement.target));
})();
