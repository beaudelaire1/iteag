/* Maintien de la session pendant qu'on travaille, avertissement avant qu'elle
   ne se ferme.

   La session expire après trente minutes sans requête (cahier des charges,
   ETU-001). Remplir un long formulaire n'en fait aucune : l'expiration tombait
   au milieu de la saisie, et « Enregistrer » renvoyait vers la connexion en
   perdant le texte.

   Deux règles, et seulement deux :
   - si la personne a tapé, cliqué ou fait défiler depuis la dernière
     prolongation, on prolonge (au plus toutes les cinq minutes) ;
   - si rien ne s'est passé depuis vingt-cinq minutes, on prévient, avec un
     bouton pour rester connecté. Une vraie inactivité ferme donc toujours la
     session, comme prévu.

   Plusieurs onglets partagent l'heure du dernier échange avec le serveur
   (localStorage) : un onglet oublié ne prévient pas à tort quand un autre
   travaille. */
(function () {
  "use strict";

  const racine = document.getElementById("session-active");
  if (!racine) return;

  const duree = (parseInt(racine.dataset.duree, 10) || 1800) * 1000;
  const adresse = racine.dataset.prolonger;
  const connexion = racine.dataset.connexion;
  const avance = Math.min(5 * 60 * 1000, duree / 3);
  const intervalleMin = Math.min(5 * 60 * 1000, duree / 4);
  const CLE = "iteag-session-echange";

  const dialogue = racine.querySelector("[data-session-dialogue]");
  const texte = racine.querySelector("[data-session-texte]");
  const boutonRester = racine.querySelector("[data-session-rester]");
  const lienReconnexion = racine.querySelector("[data-session-reconnexion]");

  let dernierEchange = Date.now();
  let derniereActivite = Date.now();
  let expiree = false;

  function lireEchangePartage() {
    try {
      const valeur = parseInt(window.localStorage.getItem(CLE), 10);
      if (valeur > dernierEchange) dernierEchange = valeur;
    } catch (erreur) {
      /* stockage indisponible : chaque onglet compte pour lui-même */
    }
  }

  function ecrireEchangePartage() {
    try {
      window.localStorage.setItem(CLE, String(dernierEchange));
    } catch (erreur) {
      /* rien à faire */
    }
  }

  function jeton() {
    const champ = document.querySelector('input[name="csrfmiddlewaretoken"]');
    return champ ? champ.value : "";
  }

  function prolonger() {
    const envoi = new FormData();
    envoi.append("csrfmiddlewaretoken", jeton());
    return fetch(adresse, {
      method: "POST",
      body: envoi,
      credentials: "same-origin",
      headers: { "X-Requested-With": "XMLHttpRequest" },
      redirect: "manual",
    })
      .then((reponse) => {
        if (reponse.status === 204) {
          dernierEchange = Date.now();
          ecrireEchangePartage();
          fermerDialogue();
          return true;
        }
        return false;
      })
      .catch(() => false);
  }

  function ouvrirDialogue(message) {
    texte.textContent = message;
    if (dialogue.hidden) {
      dialogue.hidden = false;
      boutonRester.focus();
    }
  }

  function fermerDialogue() {
    dialogue.hidden = true;
  }

  function marquerExpiree() {
    expiree = true;
    boutonRester.hidden = true;
    lienReconnexion.hidden = false;
    lienReconnexion.href = `${connexion}?next=${encodeURIComponent(window.location.pathname + window.location.search)}`;
    ouvrirDialogue(
      "Votre session s’est fermée après 30 minutes sans activité. Ce qui n’a pas été enregistré est encore " +
        "affiché : copiez-le si besoin, puis reconnectez-vous."
    );
  }

  function surActivite() {
    derniereActivite = Date.now();
  }

  ["keydown", "pointerdown", "input", "wheel", "touchstart"].forEach((type) => {
    document.addEventListener(type, surActivite, { passive: true, capture: true });
  });

  boutonRester.addEventListener("click", () => {
    prolonger().then((ok) => {
      if (!ok) marquerExpiree();
    });
  });

  function verifier() {
    if (expiree) return;
    lireEchangePartage();
    const maintenant = Date.now();

    if (derniereActivite > dernierEchange && maintenant - dernierEchange >= intervalleMin) {
      prolonger();
      return;
    }

    const restant = duree - (maintenant - dernierEchange);
    if (restant <= 0) {
      marquerExpiree();
    } else if (restant <= avance) {
      const minutes = Math.max(1, Math.round(restant / 60000));
      ouvrirDialogue(
        `Sans activité de votre part, votre session va se fermer dans ${minutes} minute${minutes > 1 ? "s" : ""}.`
      );
    } else if (!dialogue.hidden) {
      fermerDialogue();
    }
  }

  window.setInterval(verifier, 30 * 1000);
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") verifier();
  });
})();
