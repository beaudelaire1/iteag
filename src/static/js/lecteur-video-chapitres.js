/* ITEAG — Chapitres Bunny et miniatures de prévisualisation de la timeline. */
(function () {
  "use strict";

  const lecteur = document.querySelector("[data-lecteur-video]");
  if (!lecteur) return;

  const video = lecteur.querySelector("[data-video]");
  const timeline = lecteur.querySelector("[data-video-timeline]");

  function trouverUrlMetadata() {
    if (lecteur.dataset.urlMetadata) return lecteur.dataset.urlMetadata;
    const urlLecture = lecteur.dataset.urlLecture || "";
    return urlLecture.replace(/\/lecture\/?$/, "/metadata/");
  }

  const urlMetadata = trouverUrlMetadata();
  if (!video || !timeline || !urlMetadata) return;

  const shell = document.createElement("div");
  shell.className = "iteag-player__timeline-shell";
  timeline.parentNode.insertBefore(shell, timeline);
  shell.append(timeline);

  const marqueurs = document.createElement("div");
  marqueurs.className = "iteag-player__chapter-markers";
  marqueurs.setAttribute("aria-hidden", "true");
  shell.append(marqueurs);

  const apercu = document.createElement("div");
  apercu.className = "iteag-player__seek-preview";
  apercu.hidden = true;
  apercu.innerHTML = [
    '<div class="iteag-player__seek-image" data-seek-image aria-hidden="true"></div>',
    '<div class="iteag-player__seek-meta">',
    '<strong data-seek-time>0:00</strong>',
    '<span data-seek-chapter></span>',
    "</div>",
  ].join("");
  shell.append(apercu);

  const chapitreActif = document.createElement("div");
  chapitreActif.className = "iteag-player__chapter-current";
  chapitreActif.hidden = true;
  chapitreActif.setAttribute("aria-live", "polite");
  shell.insertAdjacentElement("afterend", chapitreActif);

  const imageApercu = apercu.querySelector("[data-seek-image]");
  const tempsApercu = apercu.querySelector("[data-seek-time]");
  const chapitreApercu = apercu.querySelector("[data-seek-chapter]");

  let chapitres = [];
  let prefixeSeek = "";
  let intervalleApercu = 2;
  let chapitreCourant = null;
  const feuillesChargees = new Map();

  function formaterTemps(secondes) {
    const total = Math.max(0, Math.floor(Number(secondes) || 0));
    const heures = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const reste = total % 60;
    if (heures) return `${heures}:${String(minutes).padStart(2, "0")}:${String(reste).padStart(2, "0")}`;
    return `${minutes}:${String(reste).padStart(2, "0")}`;
  }

  function chapitreA(secondes) {
    return chapitres.find((chapitre) => secondes >= chapitre.debut && secondes < chapitre.fin) || null;
  }

  function mettreAJourChapitreCourant() {
    if (!chapitres.length) {
      chapitreActif.hidden = true;
      chapitreCourant = null;
      return;
    }
    const trouve = chapitreA(video.currentTime || 0);
    if (!trouve) {
      chapitreActif.hidden = true;
      chapitreCourant = null;
      return;
    }
    if (chapitreCourant !== trouve) {
      chapitreCourant = trouve;
      chapitreActif.textContent = trouve.titre;
    }
    chapitreActif.hidden = false;
  }

  function rendreChapitres() {
    marqueurs.replaceChildren();
    if (!chapitres.length) {
      chapitreActif.hidden = true;
      return;
    }

    const dureeReference = Math.max(
      Number(video.duration) || 0,
      ...chapitres.map((chapitre) => chapitre.fin),
      1
    );

    chapitres.forEach((chapitre, index) => {
      if (chapitre.debut <= 0) return;
      const marqueur = document.createElement("button");
      marqueur.type = "button";
      marqueur.className = "iteag-player__chapter-marker";
      marqueur.style.left = `${Math.min(100, (chapitre.debut / dureeReference) * 100)}%`;
      marqueur.dataset.videoChapterMarker = String(index);
      marqueur.title = `${chapitre.titre} — ${formaterTemps(chapitre.debut)}`;
      marqueur.setAttribute("aria-label", `Aller au chapitre ${chapitre.titre}, ${formaterTemps(chapitre.debut)}`);
      marqueur.addEventListener("click", () => {
        if (!Number.isFinite(video.duration) || video.duration <= 0) return;
        video.currentTime = Math.min(video.duration, chapitre.debut);
        timeline.value = String(video.currentTime);
        mettreAJourChapitreCourant();
      });
      marqueurs.append(marqueur);
    });
    mettreAJourChapitreCourant();
  }

  function positionApercu(evenement) {
    const rect = timeline.getBoundingClientRect();
    if (!rect.width || !Number.isFinite(video.duration) || video.duration <= 0) return null;
    const x = Math.min(rect.right, Math.max(rect.left, evenement.clientX));
    const ratio = (x - rect.left) / rect.width;
    return {
      secondes: Math.min(video.duration, Math.max(0, ratio * video.duration)),
      x: x - shell.getBoundingClientRect().left,
    };
  }

  function appliquerSprite(secondes) {
    if (!prefixeSeek || !imageApercu) {
      if (imageApercu) imageApercu.hidden = true;
      return;
    }

    const pas = Math.max(1, Number(intervalleApercu) || 2);
    const imageIndex = Math.floor(secondes / pas);
    const feuilleIndex = Math.floor(imageIndex / 36);
    const cellule = imageIndex % 36;
    const colonne = cellule % 6;
    const ligne = Math.floor(cellule / 6);
    const url = `${prefixeSeek}_${feuilleIndex}.jpg`;

    const appliquer = () => {
      imageApercu.hidden = false;
      imageApercu.style.backgroundImage = `url("${url}")`;
      imageApercu.style.backgroundPosition = `${colonne * 20}% ${ligne * 20}%`;
    };

    if (feuillesChargees.get(url) === true) {
      appliquer();
      return;
    }
    if (feuillesChargees.get(url) === false) {
      imageApercu.hidden = true;
      return;
    }

    const image = new Image();
    feuillesChargees.set(url, null);
    image.onload = () => {
      feuillesChargees.set(url, true);
      appliquer();
    };
    image.onerror = () => {
      feuillesChargees.set(url, false);
      imageApercu.hidden = true;
    };
    image.src = url;
  }

  function afficherApercu(evenement) {
    const position = positionApercu(evenement);
    if (!position) return;

    apercu.hidden = false;
    const largeur = apercu.offsetWidth || 196;
    const marge = 8;
    const x = Math.max(largeur / 2 + marge, Math.min(shell.clientWidth - largeur / 2 - marge, position.x));
    apercu.style.left = `${x}px`;

    tempsApercu.textContent = formaterTemps(position.secondes);
    const chapitre = chapitreA(position.secondes);
    chapitreApercu.textContent = chapitre ? chapitre.titre : "";
    appliquerSprite(position.secondes);
  }

  function masquerApercu() {
    apercu.hidden = true;
  }

  timeline.addEventListener("pointermove", afficherApercu);
  timeline.addEventListener("pointerenter", afficherApercu);
  timeline.addEventListener("pointerleave", masquerApercu);
  timeline.addEventListener("pointercancel", masquerApercu);
  timeline.addEventListener("blur", masquerApercu);

  video.addEventListener("loadedmetadata", () => {
    if (video.videoWidth > 0 && video.videoHeight > 0) {
      imageApercu.style.aspectRatio = `${video.videoWidth} / ${video.videoHeight}`;
    }
    rendreChapitres();
  });
  video.addEventListener("durationchange", rendreChapitres);
  video.addEventListener("timeupdate", mettreAJourChapitreCourant);

  fetch(urlMetadata, {
    method: "GET",
    credentials: "same-origin",
    headers: { "X-Requested-With": "XMLHttpRequest" },
  })
    .then((reponse) => (reponse.ok ? reponse.json() : null))
    .then((donnees) => {
      if (!donnees) return;
      chapitres = Array.isArray(donnees.chapitres)
        ? donnees.chapitres
            .map((chapitre) => ({
              titre: String(chapitre.titre || "").trim(),
              debut: Number(chapitre.debut || 0),
              fin: Number(chapitre.fin || 0),
            }))
            .filter((chapitre) => chapitre.titre && chapitre.fin > chapitre.debut)
            .sort((a, b) => a.debut - b.debut)
        : [];
      prefixeSeek = String(donnees.seek_url_prefix || "");
      intervalleApercu = Math.max(1, Number(donnees.intervalle_apercu) || 2);
      rendreChapitres();
    })
    .catch(() => {
      /* Les métadonnées enrichissent le lecteur mais ne conditionnent jamais la lecture. */
    });
})();
