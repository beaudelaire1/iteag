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
  const urlLecture = conteneur.dataset.urlLecture;
  const urlProgression = conteneur.dataset.urlProgression;
  const positionReprise = parseInt(conteneur.dataset.positionReprise, 10) || 0;
  const intervalle = (parseInt(conteneur.dataset.intervalle, 10) || 15) * 1000;

  let adresseObtenue = false;
  let expireLe = 0;
  let dernierSignal = 0;
  let minuteur = null;
  let hls = null;

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
  // et couperait l'AirPlay.
  function hlsNatif() {
    return video.canPlayType("application/vnd.apple.mpegurl") !== "";
  }

  function attacherHls(adresse) {
    if (hlsNatif()) {
      video.src = adresse;
      return true;
    }
    if (typeof Hls === "undefined" || !Hls.isSupported()) {
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
    hls.on(Hls.Events.ERROR, (_evenement, donnees) => {
      if (!donnees.fatal) return;
      // Une erreur réseau fatale signifie le plus souvent un jeton périmé :
      // on redemande une adresse plutôt que d'afficher un échec.
      adresseObtenue = false;
      if (donnees.type === Hls.ErrorTypes.NETWORK_ERROR) {
        preparerLecture().then((pret) => {
          if (pret) video.play().catch(() => {});
        });
      } else {
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
  video.addEventListener("error", async () => {
    if (!adresseObtenue) return;
    adresseObtenue = false;
    if (await preparerLecture()) {
      video.play().catch(() => montrerBouton());
    } else {
      montrerBouton();
    }
  });

  // Dernier signal avant de quitter la page, pour ne pas perdre la position.
  window.addEventListener("pagehide", () => {
    if (adresseObtenue) envoyerSignal(true);
  });
})();
