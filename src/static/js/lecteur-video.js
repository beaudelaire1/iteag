/* ═══════════════════════════════════════════════════════════════
   ITEAG — Lecteur vidéo sécurisé et propriétaire
   Bunny fournit le HLS, le CDN et les renditions. L'interface, les droits,
   la progression et l'expérience de lecture restent pilotés par ITEAG.
   ═══════════════════════════════════════════════════════════════ */

(function () {
  "use strict";

  const conteneur = document.querySelector("[data-lecteur-video]");
  if (!conteneur) return;

  const video = conteneur.querySelector("[data-video]");
  const zoneMessage = conteneur.querySelector("[data-lecteur-message]");
  const boutonDemarrer = conteneur.querySelector("[data-demarrer-video]");
  const boutonLecture = conteneur.querySelector("[data-video-toggle-play]");
  const iconeLecture = conteneur.querySelector("[data-play-icon]");
  const iconePause = conteneur.querySelector("[data-pause-icon]");
  const boutonsSaut = [...conteneur.querySelectorAll("[data-saut-video]")];
  const timeline = conteneur.querySelector("[data-video-timeline]");
  const tempsCourant = conteneur.querySelector("[data-video-current]");
  const tempsTotal = conteneur.querySelector("[data-video-duration]");
  const boutonMuet = conteneur.querySelector("[data-video-mute]");
  const iconeVolume = conteneur.querySelector("[data-volume-icon]");
  const iconeMuet = conteneur.querySelector("[data-muted-icon]");
  const volume = conteneur.querySelector("[data-video-volume]");
  const selectVitesse = conteneur.querySelector("[data-vitesse-video]");
  const selectSousTitres = conteneur.querySelector("[data-sous-titres-video]");
  const selectQualite = conteneur.querySelector("[data-qualite-video]");
  const qualiteActive = conteneur.querySelector("[data-qualite-active]");
  const boutonPip = conteneur.querySelector("[data-video-pip]");
  const boutonPleinEcran = conteneur.querySelector("[data-video-fullscreen]");
  const chargement = conteneur.querySelector("[data-video-loading]");
  const reprise = conteneur.querySelector("[data-reprise-video]");
  const repriseTemps = conteneur.querySelector("[data-reprise-temps]");
  const fin = conteneur.querySelector("[data-video-end]");
  const lienSuivant = conteneur.querySelector("[data-lecon-suivante]");
  const finCopie = conteneur.querySelector("[data-video-end-copy]");
  const boutonRejouer = conteneur.querySelector("[data-rejouer-video]");

  const urlLecture = conteneur.dataset.urlLecture;
  const urlProgression = conteneur.dataset.urlProgression;
  const positionReprise = parseInt(conteneur.dataset.positionReprise, 10) || 0;
  const intervalle = (parseInt(conteneur.dataset.intervalle, 10) || 15) * 1000;

  const CLE_QUALITE = "iteag_video_quality";
  const DUREE_PREFERENCE_MS = 180 * 24 * 60 * 60 * 1000;
  const REPRISES_MAX = 3;
  const DELAI_REPRISE_MS = 1000;

  let adresseObtenue = false;
  let expireLe = 0;
  let dernierSignal = 0;
  let minuteur = null;
  let hls = null;
  let qualiteSession = "auto";
  let positionDemandee = positionReprise;
  let reprises = 0;
  let repriseEnCours = false;

  function jetonCsrf() {
    const champ = document.querySelector("[name=csrfmiddlewaretoken]");
    if (champ) return champ.value;
    const cookie = document.cookie.match(/csrftoken=([^;]+)/);
    return cookie ? cookie[1] : "";
  }

  function formaterTemps(secondes) {
    const total = Math.max(0, Math.floor(Number(secondes) || 0));
    const heures = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const reste = total % 60;
    if (heures) return `${heures}:${String(minutes).padStart(2, "0")}:${String(reste).padStart(2, "0")}`;
    return `${minutes}:${String(reste).padStart(2, "0")}`;
  }

  function afficherMessage(texte) {
    if (!zoneMessage) return;
    zoneMessage.textContent = texte;
    zoneMessage.hidden = false;
  }

  function masquerMessage() {
    if (zoneMessage) zoneMessage.hidden = true;
  }

  function afficherChargement(actif) {
    if (chargement) chargement.hidden = !actif;
  }

  function montrerBouton() {
    if (!boutonDemarrer || !video.paused || (fin && !fin.hidden)) return;
    boutonDemarrer.hidden = false;
    boutonDemarrer.disabled = false;
  }

  function masquerBouton() {
    if (!boutonDemarrer) return;
    boutonDemarrer.hidden = true;
    boutonDemarrer.disabled = false;
  }

  function mettreAJourLecture() {
    const enLecture = !video.paused && !video.ended;
    if (iconeLecture) iconeLecture.hidden = enLecture;
    if (iconePause) iconePause.hidden = !enLecture;
    if (boutonLecture) boutonLecture.setAttribute("aria-label", enLecture ? "Mettre en pause" : "Lire la vidéo");
  }

  function mettreAJourVolume() {
    const muet = video.muted || video.volume === 0;
    if (iconeVolume) iconeVolume.hidden = muet;
    if (iconeMuet) iconeMuet.hidden = !muet;
    if (boutonMuet) boutonMuet.setAttribute("aria-label", muet ? "Rétablir le son" : "Couper le son");
    if (volume && document.activeElement !== volume) volume.value = String(muet ? 0 : video.volume);
  }

  function mettreAJourTemps() {
    if (tempsCourant) tempsCourant.textContent = formaterTemps(video.currentTime);
    if (tempsTotal) tempsTotal.textContent = formaterTemps(video.duration);
    if (timeline && Number.isFinite(video.duration) && video.duration > 0 && document.activeElement !== timeline) {
      timeline.value = String(video.currentTime);
    }
  }

  function activerNavigation() {
    const actif = Number.isFinite(video.duration) && video.duration > 0;
    boutonsSaut.forEach((bouton) => {
      bouton.disabled = !actif;
    });
    if (timeline) {
      timeline.disabled = !actif;
      timeline.max = actif ? String(video.duration) : "1000";
    }
    mettreAJourTemps();
  }

  /* ── Préférence facultative : qualité HLS ── */
  function preferencesAutorisees() {
    return window.ITEAGConsent?.allows("preferences") === true;
  }

  function supprimerPreferenceQualite() {
    try {
      localStorage.removeItem(CLE_QUALITE);
    } catch (_erreur) {
      /* Le stockage facultatif ne doit jamais bloquer la lecture. */
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
      /* Une préférence non mémorisée ne dégrade pas la vidéo. */
    }
  }

  function preferenceQualiteVoulue() {
    if (qualiteSession !== "auto") return qualiteSession;
    return lirePreferenceQualite() || "auto";
  }

  window.addEventListener("iteag:consent-changed", () => {
    if (!preferencesAutorisees()) supprimerPreferenceQualite();
  });

  /* ── Qualité Bunny/HLS ── */
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

  /* ── Sous-titres ── */
  function configurerSousTitres() {
    if (!selectSousTitres) return;
    const pistes = [...video.textTracks];
    selectSousTitres.innerHTML = "";

    const aucune = document.createElement("option");
    aucune.value = "-1";
    aucune.textContent = "CC · désactivés";
    selectSousTitres.append(aucune);

    const pistesHtml = [...video.querySelectorAll("track[kind='subtitles'], track[kind='captions']")];
    let indexDefaut = -1;
    pistes.forEach((piste, index) => {
      const option = document.createElement("option");
      option.value = String(index);
      option.textContent = piste.label || piste.language || `Piste ${index + 1}`;
      selectSousTitres.append(option);
      piste.mode = "disabled";
      if (pistesHtml[index]?.default) indexDefaut = index;
    });

    selectSousTitres.disabled = pistes.length === 0;
    if (indexDefaut >= 0) {
      pistes[indexDefaut].mode = "showing";
      selectSousTitres.value = String(indexDefaut);
    } else {
      selectSousTitres.value = "-1";
    }
  }

  if (selectSousTitres) {
    selectSousTitres.addEventListener("change", () => {
      const index = Number(selectSousTitres.value);
      [...video.textTracks].forEach((piste, pisteIndex) => {
        piste.mode = pisteIndex === index ? "showing" : "disabled";
      });
    });
  }

  /* ── Adresse de lecture protégée ── */
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
    expireLe = Date.now() + Math.max(0, donnees.expire_dans - 30) * 1000;
    masquerMessage();
    return { url: donnees.url, mode: donnees.mode || "fichier" };
  }

  function hlsNatif() {
    return "webkitCurrentPlaybackTargetIsWireless" in video && video.canPlayType("application/vnd.apple.mpegurl") !== "";
  }

  function attacherHls(adresse) {
    if (hlsNatif()) {
      video.src = adresse;
      video.load();
      desactiverQualite("Auto · navigateur");
      return Promise.resolve(true);
    }

    if (typeof Hls === "undefined" || !Hls.isSupported()) {
      if (video.canPlayType("application/vnd.apple.mpegurl") !== "") {
        video.src = adresse;
        video.load();
        desactiverQualite("Auto · navigateur");
        return Promise.resolve(true);
      }
      afficherMessage("Votre navigateur ne permet pas la lecture de cette vidéo.");
      return Promise.resolve(false);
    }

    if (hls) hls.destroy();
    hls = new Hls({ lowLatencyMode: false });

    return new Promise((resolve) => {
      let initialise = false;
      const conclure = (valeur) => {
        if (initialise) return;
        initialise = true;
        resolve(valeur);
      };

      hls.on(Hls.Events.MANIFEST_PARSED, () => {
        configurerQualites();
        conclure(true);
      });
      hls.on(Hls.Events.LEVEL_SWITCHED, (_evenement, donnees) => {
        const niveau = hls.levels[donnees.level];
        if (!niveau?.height) return;
        afficherEtatQualite(hls.autoLevelEnabled ? `Auto · ${niveau.height}p` : `${niveau.height}p · sélection manuelle`);
      });
      hls.on(Hls.Events.ERROR, (_evenement, donnees) => {
        if (!donnees.fatal) return;
        if (!initialise) {
          conclure(false);
          afficherMessage("La vidéo n'a pas pu être préparée. Réessayez.");
          return;
        }
        if (donnees.type === Hls.ErrorTypes.NETWORK_ERROR) reprendreApresErreur();
        else {
          adresseObtenue = false;
          afficherMessage("La lecture a été interrompue. Rechargez la page.");
        }
      });
      hls.loadSource(adresse);
      hls.attachMedia(video);
    });
  }

  function appliquerPositionDemandee() {
    if (positionDemandee <= 0 || !Number.isFinite(video.duration)) return;
    video.currentTime = Math.min(positionDemandee, Math.max(0, video.duration - 0.25));
  }

  async function preparerLecture() {
    if (adresseObtenue && Date.now() < expireLe) return true;
    if (adresseObtenue && Number.isFinite(video.currentTime)) positionDemandee = video.currentTime;

    afficherChargement(true);
    const lecture = await obtenirAdresse();
    if (!lecture) {
      afficherChargement(false);
      return false;
    }

    let attachee = true;
    if (lecture.mode === "hls") {
      attachee = await attacherHls(lecture.url);
    } else {
      video.src = lecture.url;
      video.load();
      desactiverQualite("Qualité source");
    }
    if (!attachee) {
      afficherChargement(false);
      return false;
    }

    adresseObtenue = true;
    masquerBouton();
    if (video.readyState >= 1) appliquerPositionDemandee();
    else video.addEventListener("loadedmetadata", appliquerPositionDemandee, { once: true });
    return true;
  }

  async function lancerLecture() {
    if (fin) fin.hidden = true;
    if (boutonDemarrer) boutonDemarrer.disabled = true;
    if (!(await preparerLecture())) {
      montrerBouton();
      return;
    }
    try {
      await video.play();
      demarrerSignaux();
    } catch (_erreur) {
      afficherChargement(false);
      montrerBouton();
    }
  }

  async function basculerLecture() {
    if (video.paused || video.ended) await lancerLecture();
    else video.pause();
  }

  /* ── Progression ── */
  function envoyerSignal(force) {
    if (!adresseObtenue) return;
    const maintenant = Date.now();
    const ecoule = dernierSignal ? (maintenant - dernierSignal) / 1000 : 0;
    const delta = Math.round(ecoule * Math.max(0.25, video.playbackRate || 1));
    if (!force && delta < 1) return;
    dernierSignal = maintenant;

    fetch(urlProgression, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": jetonCsrf() },
      credentials: "same-origin",
      body: JSON.stringify({ position: Math.round(video.currentTime || 0), delta }),
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
        /* Un signal perdu n'interrompt jamais la vidéo. */
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

  function reprendreApresErreur() {
    if (repriseEnCours) return;
    if (reprises >= REPRISES_MAX) {
      afficherChargement(false);
      afficherMessage("La lecture de cette vidéo a échoué. Rechargez la page ou signalez-le au secrétariat.");
      montrerBouton();
      return;
    }
    repriseEnCours = true;
    const attente = DELAI_REPRISE_MS * 2 ** reprises;
    reprises += 1;
    positionDemandee = video.currentTime || positionDemandee;
    adresseObtenue = false;
    setTimeout(async () => {
      repriseEnCours = false;
      await lancerLecture();
    }, attente);
  }

  /* ── Contrôles ITEAG ── */
  boutonsSaut.forEach((bouton) => {
    bouton.addEventListener("click", () => {
      if (!Number.isFinite(video.duration)) return;
      const secondes = Number(bouton.dataset.sautVideo || 0);
      video.currentTime = Math.min(video.duration, Math.max(0, video.currentTime + secondes));
    });
  });

  if (timeline) {
    timeline.addEventListener("input", () => {
      if (!Number.isFinite(video.duration)) return;
      video.currentTime = Math.min(video.duration, Math.max(0, Number(timeline.value)));
      mettreAJourTemps();
    });
  }

  if (boutonLecture) boutonLecture.addEventListener("click", basculerLecture);
  if (boutonDemarrer) boutonDemarrer.addEventListener("click", lancerLecture);
  video.addEventListener("click", basculerLecture);
  video.addEventListener("contextmenu", (evenement) => evenement.preventDefault());

  if (boutonMuet) {
    boutonMuet.addEventListener("click", () => {
      video.muted = !video.muted;
      mettreAJourVolume();
    });
  }

  if (volume) {
    volume.addEventListener("input", () => {
      video.volume = Number(volume.value);
      video.muted = video.volume === 0;
      mettreAJourVolume();
    });
  }

  if (selectVitesse) {
    selectVitesse.addEventListener("change", () => {
      if (!video.paused) envoyerSignal(true);
      video.playbackRate = Number(selectVitesse.value) || 1;
      dernierSignal = Date.now();
    });
  }

  if (boutonPip && document.pictureInPictureEnabled && video.requestPictureInPicture) {
    boutonPip.hidden = false;
    boutonPip.addEventListener("click", async () => {
      try {
        if (document.pictureInPictureElement) await document.exitPictureInPicture();
        else await video.requestPictureInPicture();
      } catch (_erreur) {
        /* Certains navigateurs bloquent PiP selon leur politique locale. */
      }
    });
  }

  async function basculerPleinEcran() {
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else if (conteneur.requestFullscreen) await conteneur.requestFullscreen();
      else if (video.webkitEnterFullscreen) video.webkitEnterFullscreen();
    } catch (_erreur) {
      /* Le plein écran peut être refusé hors geste utilisateur. */
    }
  }

  if (boutonPleinEcran) boutonPleinEcran.addEventListener("click", basculerPleinEcran);

  /* ── Reprise et fin de leçon ── */
  if (reprise) {
    masquerBouton();
    if (repriseTemps) repriseTemps.textContent = formaterTemps(positionReprise);
    reprise.querySelectorAll("[data-reprise-action]").forEach((bouton) => {
      bouton.addEventListener("click", async () => {
        positionDemandee = bouton.dataset.repriseAction === "restart" ? 0 : positionReprise;
        reprise.hidden = true;
        await lancerLecture();
      });
    });
  }

  function trouverLeconSuivante() {
    const liens = [...document.querySelectorAll('nav[aria-label="Leçons du module"] a.portal-nav-link')];
    const index = liens.findIndex((lien) => lien.getAttribute("aria-current") === "page");
    if (index < 0 || index >= liens.length - 1) return null;
    const suivant = liens[index + 1];
    const verrouillee = [...suivant.querySelectorAll(".sr-only")].some((element) =>
      element.textContent.toLowerCase().includes("verrouillée")
    );
    return verrouillee ? null : suivant;
  }

  function afficherFin() {
    if (!fin) return;
    const suivant = trouverLeconSuivante();
    if (lienSuivant && suivant) {
      const titre = suivant.querySelector(".truncate")?.textContent.trim() || "Leçon suivante";
      lienSuivant.href = suivant.href;
      lienSuivant.textContent = `Continuer · ${titre}`;
      lienSuivant.hidden = false;
      if (finCopie) finCopie.textContent = "Votre progression a été enregistrée. Vous pouvez continuer le module.";
    } else if (lienSuivant) {
      lienSuivant.hidden = true;
    }
    fin.hidden = false;
  }

  if (boutonRejouer) {
    boutonRejouer.addEventListener("click", async () => {
      if (fin) fin.hidden = true;
      positionDemandee = 0;
      if (Number.isFinite(video.duration)) video.currentTime = 0;
      await lancerLecture();
    });
  }

  /* ── Événements média ── */
  video.addEventListener("loadedmetadata", () => {
    activerNavigation();
    configurerSousTitres();
  });
  video.addEventListener("durationchange", activerNavigation);
  video.addEventListener("timeupdate", mettreAJourTemps);
  video.addEventListener("volumechange", mettreAJourVolume);

  video.addEventListener("play", () => {
    masquerBouton();
    mettreAJourLecture();
    demarrerSignaux();
  });
  video.addEventListener("playing", () => {
    reprises = 0;
    afficherChargement(false);
    masquerBouton();
    mettreAJourLecture();
  });
  video.addEventListener("pause", () => {
    mettreAJourLecture();
    if (!adresseObtenue || video.ended) return;
    envoyerSignal(true);
    arreterSignaux();
  });
  video.addEventListener("ended", () => {
    envoyerSignal(true);
    arreterSignaux();
    afficherChargement(false);
    masquerBouton();
    mettreAJourLecture();
    afficherFin();
  });

  ["loadstart", "waiting", "stalled", "seeking"].forEach((nom) => {
    video.addEventListener(nom, () => {
      if (adresseObtenue || nom === "loadstart") afficherChargement(true);
    });
  });
  ["canplay", "seeked"].forEach((nom) => video.addEventListener(nom, () => afficherChargement(false)));

  video.addEventListener("error", () => {
    if (!adresseObtenue) return;
    if (video.error && video.error.code === 4) {
      adresseObtenue = false;
      afficherChargement(false);
      afficherMessage("Le format de cette vidéo n'est pas lisible par votre navigateur.");
      montrerBouton();
      return;
    }
    reprendreApresErreur();
  });

  /* ── Raccourcis clavier, uniquement quand le lecteur a le focus ── */
  conteneur.addEventListener("keydown", async (evenement) => {
    const cible = evenement.target;
    if (cible instanceof HTMLInputElement || cible instanceof HTMLSelectElement || cible instanceof HTMLButtonElement || cible instanceof HTMLAnchorElement) return;

    const touche = evenement.key.toLowerCase();
    if (touche === " " || touche === "k") {
      evenement.preventDefault();
      await basculerLecture();
    } else if (touche === "arrowleft") {
      evenement.preventDefault();
      if (Number.isFinite(video.duration)) video.currentTime = Math.max(0, video.currentTime - 10);
    } else if (touche === "arrowright") {
      evenement.preventDefault();
      if (Number.isFinite(video.duration)) video.currentTime = Math.min(video.duration, video.currentTime + 10);
    } else if (touche === "m") {
      evenement.preventDefault();
      video.muted = !video.muted;
    } else if (touche === "f") {
      evenement.preventDefault();
      await basculerPleinEcran();
    }
  });

  configurerSousTitres();
  mettreAJourLecture();
  mettreAJourVolume();
  mettreAJourTemps();

  window.addEventListener("pagehide", () => {
    if (adresseObtenue) envoyerSignal(true);
  });
})();
