/* ═══════════════════════════════════════════════════════════════
   ITEAG — Lecteur vidéo sécurisé
   Aucune adresse de fichier n'est présente dans la page : elle est
   demandée au serveur, qui revérifie le droit et délivre une adresse
   signée à durée de vie courte (ADR-001, ADR-005).

   Deux modes arrivent ici : « fichier » (adresse directe) et « hls »
   (manifeste segmenté, lu par hls.js auto-hébergé). Le mode « iframe »
   ne passe pas par ce script : il ne concerne que du contenu public,
   sans mesure de progression — le cadre tiers ne nous en donne pas.
   ═══════════════════════════════════════════════════════════════ */

(function () {
  "use strict";

  const conteneur = document.querySelector("[data-lecteur-video]");
  if (!conteneur) return;

  const video = conteneur.querySelector("[data-video]");
  const zoneMessage = conteneur.querySelector("[data-lecteur-message]");
  const boutonDemarrer = conteneur.querySelector("[data-demarrer-video]");
  const boutonsSaut = [...conteneur.querySelectorAll("[data-saut-video]")];
  const selectQualite = conteneur.querySelector("[data-qualite-video]");
  const qualiteActive = conteneur.querySelector("[data-qualite-active]");
  const urlLecture = conteneur.dataset.urlLecture;
  const urlProgression = conteneur.dataset.urlProgression;
  const positionReprise = parseInt(conteneur.dataset.positionReprise, 10) || 0;
  const intervalle = (parseInt(conteneur.dataset.intervalle, 10) || 15) * 1000;

  const CLE_QUALITE = "iteag_video_quality";
  const DUREE_PREFERENCE_MS = 180 * 24 * 60 * 60 * 1000;

  let adresseObtenue = false;
  let expireLe = 0;
  let dernierSignal = 0;
  let minuteur = null;
  let hls = null;
  let qualiteSession = "auto";

  /* ── Budget de reprises ──
     Une erreur de lecture signifie le plus souvent un jeton périmé, et
     redemander une adresse est la bonne réponse. Mais si l'échec est
     structurel — source illisible, vidéo absente chez le fournisseur — la
     nouvelle adresse échoue identiquement, et la reprise se rappelle
     elle-même : on a mesuré une demande toutes les 3 ms, l'onglet figé et la
     table d'audit qui se remplit à vue d'œil. Un serveur ne doit jamais
     pouvoir être martelé par sa propre page.

     D'où trois verrous : un plafond, un délai croissant, et un compteur remis
     à zéro dès qu'une lecture repart pour de bon. */
  const REPRISES_MAX = 3;
  const DELAI_REPRISE_MS = 1000;
  let reprises = 0;
  let repriseEnCours = false;

  function reprendreApresErreur() {
    if (repriseEnCours) return;
    if (reprises >= REPRISES_MAX) {
      afficherMessage("La lecture de cette vidéo a échoué. Rechargez la page ou signalez-le au secrétariat.");
      montrerBouton();
      return;
    }
    repriseEnCours = true;
    const attente = DELAI_REPRISE_MS * 2 ** reprises;
    reprises += 1;
    adresseObtenue = false;
    setTimeout(async () => {
      repriseEnCours = false;
      if (await preparerLecture()) {
        video.play().catch(() => montrerBouton());
      } else {
        montrerBouton();
      }
    }, attente);
  }

  function jetonCsrf() {
    const champ = document.querySelector("[name=csrfmiddlewaretoken]");
    if (champ) return champ.value;
    const cookie = document.cookie.match(/csrftoken=([^;]+)/);
    return cookie ? cookie[1] : "";
  }

  function afficherMessage(texte) {
    if (!zoneMessage) return;
    zoneMessage.textContent = texte;
    zoneMessage.hidden = false;
    zoneMessage.classList.remove("hidden");
  }

  function masquerMessage() {
    if (!zoneMessage) return;
    zoneMessage.hidden = true;
    zoneMessage.classList.add("hidden");
  }

  function montrerBouton() {
    if (!boutonDemarrer) return;
    boutonDemarrer.hidden = false;
    boutonDemarrer.classList.remove("hidden");
    boutonDemarrer.disabled = false;
  }

  function masquerBouton() {
    if (!boutonDemarrer) return;
    boutonDemarrer.hidden = true;
    boutonDemarrer.classList.add("hidden");
    boutonDemarrer.disabled = false;
  }

  /* ── Préférence facultative de qualité ── */
  function preferencesAutorisees() {
    return window.ITEAGConsent?.allows("preferences") === true;
  }

  function supprimerPreferenceQualite() {
    try {
      localStorage.removeItem(CLE_QUALITE);
    } catch (_erreur) {
      /* Le stockage peut être bloqué par le navigateur : la lecture continue. */
    }
  }

  function lirePreferenceQualite() {
    if (!preferencesAutorisees()) return "";
    try {
      const brut = localStorage.getItem(CLE_QUALITE);
      if (!brut) return "";
      const valeur = JSON.parse(brut);
      if (!valeur || Date.now() > Number(valeur.expireLe || 0)) {
        supprimerPreferenceQualite();
        return "";
      }
      return String(valeur.qualite || "");
    } catch (_erreur) {
      supprimerPreferenceQualite();
      return "";
    }
  }

  function memoriserPreferenceQualite(qualite) {
    qualiteSession = qualite;
    if (!preferencesAutorisees()) {
      supprimerPreferenceQualite();
      return;
    }
    try {
      localStorage.setItem(
        CLE_QUALITE,
        JSON.stringify({ qualite, expireLe: Date.now() + DUREE_PREFERENCE_MS })
      );
    } catch (_erreur) {
      /* Une préférence non enregistrée ne doit jamais bloquer la vidéo. */
    }
  }

  function preferenceQualiteVoulue() {
    if (qualiteSession !== "auto") return qualiteSession;
    return lirePreferenceQualite() || "auto";
  }

  window.addEventListener("iteag:consent-changed", () => {
    if (!preferencesAutorisees()) supprimerPreferenceQualite();
  });

  /* ── Contrôles complémentaires ── */
  function activerSauts() {
    const actif = Number.isFinite(video.duration) && video.duration > 0;
    boutonsSaut.forEach((bouton) => {
      bouton.disabled = !actif;
    });
  }

  function sauter(secondes) {
    if (!Number.isFinite(video.duration) || video.duration <= 0) return;
    const cible = Math.min(video.duration, Math.max(0, video.currentTime + secondes));
    video.currentTime = cible;
  }

  boutonsSaut.forEach((bouton) => {
    bouton.addEventListener("click", () => {
      const secondes = Number(bouton.dataset.sautVideo || 0);
      if (Number.isFinite(secondes)) sauter(secondes);
    });
  });

  video.addEventListener("loadedmetadata", activerSauts);
  video.addEventListener("durationchange", activerSauts);

  function afficherEtatQualite(texte) {
    if (qualiteActive) qualiteActive.textContent = texte;
  }

  function desactiverQualite(libelle) {
    if (!selectQualite) return;
    selectQualite.innerHTML = "";
    const option = document.createElement("option");
    option.value = "-1";
    option.textContent = libelle;
    selectQualite.append(option);
    selectQualite.disabled = true;
    afficherEtatQualite(libelle);
  }

  function niveauxParResolution() {
    const parHauteur = new Map();
    hls?.levels?.forEach((niveau, index) => {
      const hauteur = Number(niveau.height || 0);
      if (!hauteur) return;
      const precedent = parHauteur.get(hauteur);
      if (!precedent || Number(niveau.bitrate || 0) > precedent.bitrate) {
        parHauteur.set(hauteur, { index, hauteur, bitrate: Number(niveau.bitrate || 0) });
      }
    });
    return [...parHauteur.values()].sort((a, b) => b.hauteur - a.hauteur);
  }

  function appliquerQualiteVoulue() {
    if (!hls || !selectQualite) return;
    const voulue = preferenceQualiteVoulue();
    if (voulue === "auto") {
      selectQualite.value = "-1";
      hls.currentLevel = -1;
      return;
    }
    const option = [...selectQualite.options].find((item) => item.dataset.hauteur === voulue);
    if (!option) {
      qualiteSession = "auto";
      selectQualite.value = "-1";
      hls.currentLevel = -1;
      return;
    }
    selectQualite.value = option.value;
    hls.currentLevel = Number(option.value);
  }

  function configurerQualites() {
    if (!selectQualite || !hls) return;
    selectQualite.innerHTML = "";

    const auto = document.createElement("option");
    auto.value = "-1";
    auto.textContent = "Auto";
    auto.dataset.hauteur = "auto";
    selectQualite.append(auto);

    niveauxParResolution().forEach((niveau) => {
      const option = document.createElement("option");
      option.value = String(niveau.index);
      option.dataset.hauteur = String(niveau.hauteur);
      option.textContent = `${niveau.hauteur}p`;
      selectQualite.append(option);
    });

    selectQualite.disabled = selectQualite.options.length <= 1;
    appliquerQualiteVoulue();
    afficherEtatQualite(selectQualite.disabled ? "Qualité automatique" : "Auto · adaptation au débit");
  }

  if (selectQualite) {
    selectQualite.addEventListener("change", () => {
      if (!hls) return;
      const index = Number(selectQualite.value);
      if (index === -1) {
        hls.currentLevel = -1;
        memoriserPreferenceQualite("auto");
        afficherEtatQualite("Auto · adaptation au débit");
        return;
      }
      const option = selectQualite.selectedOptions[0];
      const hauteur = option?.dataset.hauteur || "auto";
      hls.currentLevel = index;
      memoriserPreferenceQualite(hauteur);
      afficherEtatQualite(`${hauteur}p · sélection manuelle`);
    });
  }

  /* ── Demande d'une adresse de lecture ── */
  async function obtenirAdresse() {
    let reponse;
    try {
      reponse = await fetch(urlLecture, {
        method: "POST",
        headers: { "X-CSRFToken": jetonCsrf(), "X-Requested-With": "XMLHttpRequest" },
        credentials: "same-origin",
      });
    } catch (_erreur) {
      afficherMessage("Le service vidéo est momentanément injoignable. Réessayez.");
      return null;
    }

    if (!reponse.ok) {
      const donnees = await reponse.json().catch(() => ({}));
      afficherMessage(donnees.erreur || "La lecture n'est pas disponible pour le moment.");
      return null;
    }

    const donnees = await reponse.json();
    // On renouvelle un peu avant l'échéance pour éviter une coupure en pleine lecture.
    expireLe = Date.now() + (donnees.expire_dans - 30) * 1000;
    masquerMessage();
    return { url: donnees.url, mode: donnees.mode || "fichier" };
  }

  /* ── Rattachement de la source selon le mode ── */

  // Safari lit le HLS nativement : lui imposer hls.js dégraderait la lecture
  // et couperait l'AirPlay. Encore faut-il reconnaître Safari.
  //
  // `canPlayType("application/vnd.apple.mpegurl")` ne le fait plus : Chrome y
  // répond « maybe » alors qu'il est incapable de lire un manifeste HLS. Sur
  // cette seule réponse, le lecteur collait l'adresse dans `video.src`,
  // n'utilisait jamais hls.js, et échouait en MediaError 4 — sur Chrome et
  // Edge, donc sur l'essentiel du public, donc sur tout le contenu Bunny.
  //
  // `webkitCurrentPlaybackTargetIsWireless` est propre à WebKit et c'est
  // précisément la propriété AirPlay que l'on cherche à préserver : le test
  // porte enfin sur ce qui motive l'exception.
  function hlsNatif() {
    return "webkitCurrentPlaybackTargetIsWireless" in video && video.canPlayType("application/vnd.apple.mpegurl") !== "";
  }

  function attacherHls(adresse) {
    if (hlsNatif()) {
      video.src = adresse;
      desactiverQualite("Auto · navigateur");
      return true;
    }
    if (typeof Hls === "undefined" || !Hls.isSupported()) {
      // Dernier recours : un navigateur sans MSE qui prétend lire le HLS vaut
      // mieux qu'un refus sec.
      if (video.canPlayType("application/vnd.apple.mpegurl") !== "") {
        video.src = adresse;
        desactiverQualite("Auto · navigateur");
        return true;
      }
      afficherMessage("Votre navigateur ne permet pas la lecture de cette vidéo.");
      return false;
    }
    if (hls) hls.destroy();
    hls = new Hls({
      lowLatencyMode: false,
      // Un flux HLS n'est pas un fichier : après le manifeste, le lecteur
      // demande les segments un par un. Le jeton Bunny est volontairement
      // placé dans le chemin du manifeste : les adresses relatives des
      // segments en héritent sans réécriture dans le navigateur.
    });
    hls.loadSource(adresse);
    hls.attachMedia(video);
    hls.on(Hls.Events.MANIFEST_PARSED, configurerQualites);
    hls.on(Hls.Events.LEVEL_SWITCHED, (_evenement, donnees) => {
      const niveau = hls.levels[donnees.level];
      if (!niveau?.height) return;
      if (hls.autoLevelEnabled) {
        afficherEtatQualite(`Auto · ${niveau.height}p`);
      } else {
        afficherEtatQualite(`${niveau.height}p · sélection manuelle`);
      }
    });
    hls.on(Hls.Events.ERROR, (_evenement, donnees) => {
      if (!donnees.fatal) return;
      // Une erreur réseau fatale signifie le plus souvent un jeton périmé :
      // on redemande une adresse plutôt que d'afficher un échec.
      if (donnees.type === Hls.ErrorTypes.NETWORK_ERROR) {
        reprendreApresErreur();
      } else {
        adresseObtenue = false;
        afficherMessage("La lecture a été interrompue. Rechargez la page.");
      }
    });
    return true;
  }

  async function preparerLecture() {
    if (adresseObtenue && Date.now() < expireLe) return true;

    const positionCourante = video.currentTime || positionReprise;
    const lecture = await obtenirAdresse();
    if (!lecture) return false;

    if (lecture.mode === "hls") {
      if (!attacherHls(lecture.url)) return false;
    } else {
      video.src = lecture.url;
      desactiverQualite("Qualité source");
    }
    adresseObtenue = true;
    masquerBouton();

    if (positionCourante > 0) {
      video.addEventListener(
        "loadedmetadata",
        () => {
          video.currentTime = positionCourante;
        },
        { once: true }
      );
    }
    return true;
  }

  async function lancerLecture() {
    if (boutonDemarrer) boutonDemarrer.disabled = true;
    if (await preparerLecture()) {
      video.play().then(demarrerSignaux).catch(() => montrerBouton());
    } else {
      montrerBouton();
    }
  }

  /* ── Signal de progression ── */
  function envoyerSignal(force) {
    const maintenant = Date.now();
    const delta = Math.round((maintenant - dernierSignal) / 1000);
    if (!force && delta < 1) return;
    dernierSignal = maintenant;

    fetch(urlProgression, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": jetonCsrf(),
      },
      credentials: "same-origin",
      body: JSON.stringify({
        position: Math.round(video.currentTime || 0),
        delta: delta,
      }),
    })
      .then((reponse) => (reponse.ok ? reponse.json() : null))
      .then((donnees) => {
        if (!donnees) return;
        const compteur = document.querySelector("[data-progression-module]");
        const barre = document.querySelector("[data-progression-barre]");
        if (compteur) compteur.textContent = donnees.pourcentage_module + " %";
        if (barre) barre.style.width = donnees.pourcentage_module + "%";
      })
      .catch(() => {
        /* Un signal perdu n'interrompt pas la lecture. */
      });
  }

  function demarrerSignaux() {
    if (minuteur) return;
    dernierSignal = Date.now();
    minuteur = setInterval(() => {
      if (!video.paused && !video.ended) envoyerSignal(false);
    }, intervalle);
  }

  function arreterSignaux() {
    if (!minuteur) return;
    clearInterval(minuteur);
    minuteur = null;
  }

  /* ── Branchements ── */

  // La première demande de lecture déclenche l'obtention de l'adresse.
  video.addEventListener("play", async (evenement) => {
    if (adresseObtenue && Date.now() < expireLe) {
      demarrerSignaux();
      return;
    }
    evenement.preventDefault();
    video.pause();
    if (await preparerLecture()) {
      video.play().then(demarrerSignaux).catch(() => {});
    } else {
      montrerBouton();
    }
  });

  // Un élément <video> sans source ne déclenche pas toujours « play » depuis
  // ses contrôles natifs. Ce bouton est donc le point d'entrée fiable : il
  // obtient d'abord l'adresse protégée, puis lance le lecteur.
  if (boutonDemarrer) {
    boutonDemarrer.addEventListener("click", lancerLecture);
  }

  video.addEventListener("pause", () => {
    if (!adresseObtenue) return;
    envoyerSignal(true);
    arreterSignaux();
  });

  video.addEventListener("ended", () => {
    envoyerSignal(true);
    arreterSignaux();
    montrerBouton();
  });

  // Une adresse expirée provoque une erreur réseau : on en redemande une.
  video.addEventListener("error", () => {
    if (!adresseObtenue) return;
    // `MEDIA_ERR_SRC_NOT_SUPPORTED` ne dit pas « adresse périmée » mais « je ne
    // sais pas lire ce format ». Une adresse neuve ne changerait rien : c'est
    // exactement l'échec qui bouclait à l'infini.
    if (video.error && video.error.code === 4) {
      adresseObtenue = false;
      afficherMessage("Le format de cette vidéo n'est pas lisible par votre navigateur.");
      montrerBouton();
      return;
    }
    reprendreApresErreur();
  });

  // Une lecture qui repart pour de bon solde le budget de reprises : la panne
  // suivante, éventuelle, repart d'un compteur neuf.
  video.addEventListener("playing", () => {
    reprises = 0;
  });

  // Dernier signal avant de quitter la page, pour ne pas perdre la position.
  window.addEventListener("pagehide", () => {
    if (adresseObtenue) envoyerSignal(true);
  });
})();
