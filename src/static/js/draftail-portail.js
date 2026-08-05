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

  /* Repli : l'éditeur n'a pas pu se charger du tout.

     Deux règles, apprises d'un défaut coûteux. Le repli remplaçait le champ
     par un « textarea » portant le même « name », après avoir aplati le
     contenu à « bloc.text » — sans gras, sans titre, sans alignement. Ouvrir
     un document formaté puis enregistrer suffisait donc à le détruire, et rien
     ne le signalait : la barre d'outils restait affichée au-dessus du champ de
     repli, si bien que les boutons paraissaient simplement inopérants.

     1. **On ne jette jamais le contenu.** Le champ d'origine garde sa valeur et
        reste celui qui est envoyé ; la zone de secours ne sert qu'à ajouter du
        texte, et n'écrase pas ce qui existe.
     2. **On le dit.** Un éditeur dégradé qui se tait laisse croire à une panne
        de formatage. */
  function activerRepli(input, raison) {
    if (input.dataset.editeurDraftailRepli) return;
    input.dataset.editeurDraftailRepli = "1";

    const champ = input.closest(".editeur-riche-portail");
    // La barre d'outils d'un éditeur qui n'a pas démarré ne commande rien :
    // la laisser visible est la source même du « les boutons ne font rien ».
    if (champ) {
      champ.querySelectorAll(".Draftail-Toolbar").forEach((barre) => barre.remove());
      champ.classList.add("editeur-riche-portail--degrade");
    }

    const avis = document.createElement("p");
    avis.className = "form-erreur";
    avis.setAttribute("role", "alert");
    avis.textContent =
      "L'éditeur de texte n'a pas pu se charger" +
      (raison ? ` (${raison})` : "") +
      ". Le contenu déjà enregistré est conservé ; la mise en forme n'est pas modifiable pour l'instant.";
    input.insertAdjacentElement("beforebegin", avis);

    // Le champ d'origine reste actif et reste celui qui part au serveur : sa
    // valeur est le contenu réel, formatage compris.
    input.type = "hidden";
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
      activerRepli(input, "script absent");
      return;
    }

    const champ = input.closest(".editeur-riche-portail");
    if (!champ) return;

    const hauteur = input.getAttribute("data-iteag-min-height");
    if (hauteur) champ.style.setProperty("--iteag-editor-min-height", hauteur);

    /* On **observe** l'apparition de l'éditeur au lieu de parier sur un délai.

       Un « setTimeout » de 750 ms était une course : Draftail a 739 Ko de
       script à analyser avant de peindre, et sur une machine chargée il arrive
       après. Le repli se déclenchait alors sur un éditeur parfaitement
       fonctionnel, qui finissait par apparaître par-dessus — d'où des boutons
       présents et sans effet.

       Le délai qui subsiste n'est plus une limite de patience mais un filet :
       dix secondes, au-delà desquelles le script est réellement en panne. */
    if (champ.querySelector(".Draftail-Editor")) {
      traduireCommandes(champ);
      return;
    }

    const observateur = new MutationObserver(() => {
      if (!champ.querySelector(".Draftail-Editor")) return;
      observateur.disconnect();
      window.clearTimeout(filet);
      traduireCommandes(champ);
    });
    observateur.observe(champ, { childList: true, subtree: true });

    const filet = window.setTimeout(() => {
      observateur.disconnect();
      if (!champ.querySelector(".Draftail-Editor")) activerRepli(input, "délai dépassé");
    }, 10000);
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
