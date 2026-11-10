/* Ajout progressif d'étapes ; les champs natifs portent toutes les données. */
(() => {
    "use strict";

    function initialiser(racine) {
        if (racine.dataset.parcoursInitialise) return;
        const etapes = racine.querySelector("[data-parcours-etapes]");
        const modele = racine.querySelector("[data-parcours-modele]");
        const ajouter = racine.querySelector("[data-parcours-ajouter]");
        const total = racine.querySelector('input[name$="-TOTAL_FORMS"]');
        const annonce = racine.querySelector("[data-parcours-annonce]");
        if (!etapes || !modele || !ajouter || !total) return;

        racine.dataset.parcoursInitialise = "true";
        ajouter.hidden = false;
        ajouter.addEventListener("click", () => {
            const index = Number(total.value);
            const fragment = modele.content.cloneNode(true);
            fragment.querySelectorAll("*").forEach((element) => {
                for (const attribut of Array.from(element.attributes)) {
                    if (attribut.value.includes("__prefix__")) {
                        element.setAttribute(attribut.name, attribut.value.replaceAll("__prefix__", String(index)));
                    }
                }
            });
            const premierChamp = fragment.querySelector("input");
            etapes.appendChild(fragment);
            total.value = String(index + 1);
            if (annonce) annonce.textContent = "Une nouvelle étape a été ajoutée.";
            premierChamp?.focus();
        });
    }

    function initialiserTout() {
        document.querySelectorAll("[data-parcours-academique]").forEach(initialiser);
    }

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", initialiserTout);
    } else {
        initialiserTout();
    }
    document.addEventListener("htmx:afterSwap", initialiserTout);
})();
