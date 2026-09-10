/* ITEAG — consentement cookies et stockage local facultatif.
 *
 * Les cookies de session et de sécurité sont nécessaires au service. Le choix
 * mémorisé ici ne pilote que les fonctionnalités facultatives, actuellement la
 * conservation des préférences d'interface (dont la qualité vidéo choisie).
 */
(function () {
  "use strict";

  const NOM_COOKIE = "iteag_cookie_consent";
  const DUREE_SECONDES = 60 * 60 * 24 * 180;
  const CHOIX_ESSENTIEL = "essential";
  const CHOIX_PREFERENCES = "preferences";
  const CLES_PREFERENCES_LOCALES = ["iteag_video_quality"];

  function lireCookie(nom) {
    const prefixe = `${nom}=`;
    return document.cookie
      .split(";")
      .map((morceau) => morceau.trim())
      .find((morceau) => morceau.startsWith(prefixe))
      ?.slice(prefixe.length) || "";
  }

  function choixActuel() {
    const valeur = decodeURIComponent(lireCookie(NOM_COOKIE));
    return [CHOIX_ESSENTIEL, CHOIX_PREFERENCES].includes(valeur) ? valeur : "";
  }

  function supprimerPreferencesLocales() {
    try {
      CLES_PREFERENCES_LOCALES.forEach((cle) => localStorage.removeItem(cle));
    } catch (_erreur) {
      /* Le navigateur peut interdire le stockage local ; rien à nettoyer. */
    }
  }

  function ecrireChoix(choix) {
    if (![CHOIX_ESSENTIEL, CHOIX_PREFERENCES].includes(choix)) return;
    if (choix === CHOIX_ESSENTIEL) supprimerPreferencesLocales();
    const secure = location.protocol === "https:" ? "; Secure" : "";
    document.cookie = `${NOM_COOKIE}=${encodeURIComponent(choix)}; Max-Age=${DUREE_SECONDES}; Path=/; SameSite=Lax${secure}`;
    window.dispatchEvent(new CustomEvent("iteag:consent-changed", { detail: { choice: choix } }));
  }

  function autorise(categorie) {
    if (categorie === "essential") return true;
    if (categorie === "preferences") return choixActuel() === CHOIX_PREFERENCES;
    return false;
  }

  function banniere() {
    return document.querySelector("[data-cookie-banner]");
  }

  /* Le serveur sert désormais la bannière déjà visible quand aucun choix n'est
   * enregistré : au chargement, il n'y a plus rien à dévoiler, et déplacer le
   * curseur vers un bouton que le visiteur n'a pas demandé déplacerait sa
   * lecture sans raison. La mise au point ne suit donc que l'ouverture
   * explicite, depuis « Gérer les cookies ». */
  function afficher(focaliser) {
    const element = banniere();
    if (!element) return;
    element.hidden = false;
    element.classList.remove("hidden");
    if (!focaliser) return;
    const premierBouton = element.querySelector("button[data-cookie-choice]");
    premierBouton?.focus({ preventScroll: true });
  }

  function masquer() {
    const element = banniere();
    if (!element) return;
    element.hidden = true;
    element.classList.add("hidden");
  }

  window.ITEAGConsent = {
    allows: autorise,
    choice: choixActuel,
    setChoice(choix) {
      ecrireChoix(choix);
      masquer();
    },
    open() {
      afficher(true);
    },
  };

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("[data-cookie-choice]").forEach((bouton) => {
      bouton.addEventListener("click", () => {
        const choix = bouton.dataset.cookieChoice;
        if (![CHOIX_ESSENTIEL, CHOIX_PREFERENCES].includes(choix)) return;
        ecrireChoix(choix);
        masquer();
      });
    });

    document.querySelectorAll("[data-cookie-settings]").forEach((bouton) => {
      bouton.addEventListener("click", () => afficher(true));
    });

    // Repli si le HTML a été mis en cache avant que le choix soit fait.
    if (!choixActuel()) afficher(false);
  });
})();
