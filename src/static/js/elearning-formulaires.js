(() => {
  "use strict";

  function formatMinutes(seconds) {
    const minutes = Number(seconds) / 60;
    if (!Number.isFinite(minutes) || minutes <= 0) return "";
    return Number.isInteger(minutes) ? String(minutes) : minutes.toFixed(1).replace(/\.0$/, "");
  }

  function bindDurationForm(form) {
    const secondsInput = form.querySelector("#id_duree_secondes");
    const minutesInput = form.querySelector("[data-duree-minutes]");
    if (!secondsInput || !minutesInput) return;

    if (secondsInput.value && !minutesInput.value) {
      minutesInput.value = formatMinutes(secondsInput.value);
    }

    const sync = () => {
      const minutes = Number.parseFloat(minutesInput.value);
      secondsInput.value = Number.isFinite(minutes) && minutes > 0
        ? String(Math.round(minutes * 60))
        : "";
    };

    minutesInput.addEventListener("input", sync);
    form.addEventListener("submit", sync);
  }

  function bindLessonType(form) {
    const select = form.querySelector("#id_type_lecon");
    const panels = [...form.querySelectorAll("[data-type-lecon]")];
    if (!select || panels.length === 0) return;

    const refresh = () => {
      panels.forEach((panel) => {
        const visible = panel.dataset.typeLecon === select.value;
        panel.hidden = !visible;
        panel.setAttribute("aria-hidden", visible ? "false" : "true");
      });
    };

    select.addEventListener("change", refresh);
    refresh();
  }

  function bindAccessPolicy(form) {
    const select = form.querySelector("#id_politique_acces");
    const pricing = form.querySelector("[data-prix-module]");
    if (!select || !pricing) return;

    const refresh = () => {
      const visible = select.value === "achat";
      pricing.hidden = !visible;
      pricing.setAttribute("aria-hidden", visible ? "false" : "true");
    };

    select.addEventListener("change", refresh);
    refresh();
  }

  /* Module ou atelier de prédication : un atelier n'a ni code, ni niveau, ni
     discipline, ni cours, ni objectifs, ni crédits, ni attestation. Choisir
     « atelier » masque ces blocs ([data-seulement-formation]), adapte les
     intitulés ([data-texte-atelier] / [data-texte-formation]) et renumérote
     les étapes restantes. Le serveur neutralise de son côté les champs
     masqués : rien de ce qui a été saisi avant de changer d'avis ne
     s'enregistre en silence. */
  function bindGenre(form) {
    const choix = [...form.querySelectorAll('input[name="genre"]')];
    if (choix.length === 0) return;

    const reserves = [...form.querySelectorAll("[data-seulement-formation]")];
    const textes = [...document.querySelectorAll("[data-texte-atelier][data-texte-formation]")];
    const etapes = [...form.querySelectorAll("[data-etape]")];
    const politique = form.querySelector("#id_politique_acces");
    const creation = form.hasAttribute("data-creation");
    let politiqueChoisie = false;
    if (politique) politique.addEventListener("change", () => { politiqueChoisie = true; });

    const refresh = (changementDeNature) => {
      const atelier = choix.some((entree) => entree.checked && entree.value === "atelier");

      reserves.forEach((bloc) => {
        bloc.hidden = atelier;
        /* Un champ masqué et exigé bloquerait l'envoi sans qu'on puisse le voir. */
        bloc.querySelectorAll("input, select, textarea").forEach((champ) => {
          if (atelier && champ.required) {
            champ.dataset.exigePourModule = "true";
            champ.required = false;
          } else if (!atelier && champ.dataset.exigePourModule) {
            champ.required = true;
          }
        });
      });

      textes.forEach((element) => {
        element.textContent = atelier ? element.dataset.texteAtelier : element.dataset.texteFormation;
      });

      /* À la création seulement, et tant qu'on n'y a pas touché : un atelier
         s'ouvre sur octroi (les inscrits du secrétariat), un module aux
         inscrits de son parcours. */
      if (changementDeNature && creation && politique && !politiqueChoisie) {
        politique.value = atelier ? "sur_octroi" : "inscrit_parcours";
      }

      let rang = 0;
      etapes.forEach((etape) => {
        if (etape.closest("[hidden]")) return;
        rang += 1;
        etape.textContent = `Étape ${rang}`;
      });
    };

    choix.forEach((entree) => entree.addEventListener("change", () => refresh(true)));
    refresh(false);
  }

  document.querySelectorAll("[data-duree-minutes-form]").forEach(bindDurationForm);
  document.querySelectorAll("[data-lecon-form]").forEach(bindLessonType);
  document.querySelectorAll("[data-module-form]").forEach(bindAccessPolicy);
  document.querySelectorAll("[data-module-form]").forEach(bindGenre);
})();
