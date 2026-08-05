/* Initialisation autonome de Draftail dans les formulaires des portails.

   Le bundle officiel Wagtail écoute « w-draftail:init ». Dans l'admin, un
   contrôleur Stimulus émet cet événement ; ici nous le faisons directement,
   ce qui évite de charger le tableau de bord complet dans l'espace étudiant,
   enseignant, administratif ou secrétariat. */
(function () {
  "use strict";

  const SELECTEUR = "[data-editeur-draftail-portail]";
  let chargementSprite;

  function traduireCommandes(champ) {
    const traductions = {
      "Horizontal line": "Ligne horizontale",
      "Line break": "Saut de ligne",
      "Unpin toolbar": "Barre d’outils toujours visible",
    };
    champ.querySelectorAll(".Draftail-ToolbarButton[aria-label]").forEach((bouton) => {
      const lignes = bouton.getAttribute("aria-label").split("\n");
      if (traductions[lignes[0]]) {
        lignes[0] = traductions[lignes[0]];
        bouton.setAttribute("aria-label", lignes.join("\n"));
      }
    });
  }

  function activerRepli(input) {
    if (input.dataset.editeurDraftailRepli) return;
    input.dataset.editeurDraftailRepli = "1";
    const zone = document.createElement("textarea");
    zone.name = input.name;
    zone.id = `${input.id}-repli`;
    zone.className = "form-input";
    zone.rows = 12;
    zone.setAttribute("aria-label", "Zone d'édition simplifiée");
    try {
      const contenu = JSON.parse(input.value || "{}");
      zone.value = (contenu.blocks || []).map((bloc) => bloc.text || "").join("\n\n");
    } catch (_erreur) {
      zone.value = input.value || "";
    }
    input.disabled = true;
    input.insertAdjacentElement("afterend", zone);
    const libelle = document.querySelector(`label[for="${input.id}"]`);
    if (libelle) libelle.setAttribute("for", zone.id);
  }

  function chargerSprite(input) {
    if (chargementSprite) return chargementSprite;
    const adresse = input.getAttribute("data-iteag-icon-url");
    if (!adresse) return Promise.resolve();

    chargementSprite = fetch(adresse, { credentials: "same-origin" })
      .then((reponse) => {
        if (!reponse.ok) throw new Error(`Sprite Draftail indisponible (${reponse.status})`);
        return reponse.text();
      })
      .then((svg) => {
        let conteneur = document.querySelector("[data-draftail-sprite-portail]");
        if (!conteneur) {
          conteneur = document.createElement("div");
          conteneur.hidden = true;
          conteneur.setAttribute("data-draftail-sprite-portail", "");
          document.body.prepend(conteneur);
        }
        conteneur.innerHTML = svg;
      })
      .catch((erreur) => {
        // Le texte et les libellés restent utilisables si les pictogrammes ne
        // se chargent pas ; l'échec ne doit pas bloquer toute la rédaction.
        console.error(erreur);
      });
    return chargementSprite;
  }

  async function initialiser(input) {
    if (input.dataset.editeurDraftailInitialise) return;
    input.dataset.editeurDraftailInitialise = "1";

    await chargerSprite(input);
    let options = {};
    try {
      options = JSON.parse(input.getAttribute("data-w-init-detail-value") || "{}");
    } catch (erreur) {
      console.error("Configuration Draftail invalide", erreur);
    }

    input.dispatchEvent(
      new CustomEvent("w-draftail:init", {
        bubbles: true,
        detail: options,
      }),
    );

    if (typeof window.draftail === "undefined") {
      input.setAttribute(
        "data-editeur-draftail-erreur",
        JSON.stringify(window.iteagDraftailErrors || []),
      );
      activerRepli(input);
      return;
    }

    requestAnimationFrame(() => {
      const champ = input.closest(".editeur-riche-portail");
      const hauteur = input.getAttribute("data-iteag-min-height");
      if (champ && hauteur) {
        champ.style.setProperty("--iteag-editor-min-height", hauteur);
        traduireCommandes(champ);
      }
    });
    window.setTimeout(() => {
      const champ = input.closest(".editeur-riche-portail");
      if (champ && !champ.querySelector(".Draftail-Editor")) activerRepli(input);
    }, 750);
  }

  function demarrer(racine) {
    (racine || document).querySelectorAll(SELECTEUR).forEach(initialiser);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => demarrer(document), { once: true });
  } else {
    demarrer(document);
  }
  document.addEventListener("htmx:afterSwap", (evenement) => demarrer(evenement.target));
})();
