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

  /* ── Demande d'une adresse de lecture ── */
  async function obtenirAdresse() {
    const reponse = await fetch(urlLecture, {
      method: "POST",
      headers: { "X-CSRFToken": jetonCsrf(), "X-Requested-With": "XMLHttpRequest" },
      credentials: "same-origin",
    });

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
      // demande les segments un par un. Ces adresses sont résolues
      // relativement au manifeste, donc *sans* sa chaîne de requête — le
      // jeton d'accès y serait perdu et chaque segment refusé. On la
      // réapplique, sauf si le manifeste en a déjà fourni une.
      xhrSetup: (xhr, url) => {
        const requeteSignee = adresse.split("?")[1];
        if (!requeteSignee || url.includes("?")) return;
        xhr.open("GET", url + "?" + requeteSignee, true);
      },
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
    }
  });

  video.addEventListener("pause", () => {
    envoyerSignal(true);
    arreterSignaux();
  });

  video.addEventListener("ended", () => {
    envoyerSignal(true);
    arreterSignaux();
  });

  // Une adresse expirée provoque une erreur réseau : on en redemande une.
  video.addEventListener("error", async () => {
    if (!adresseObtenue) return;
    adresseObtenue = false;
    if (await preparerLecture()) video.play().catch(() => {});
  });

  // Dernier signal avant de quitter la page, pour ne pas perdre la position.
  window.addEventListener("pagehide", () => {
    if (adresseObtenue) envoyerSignal(true);
  });
})();
