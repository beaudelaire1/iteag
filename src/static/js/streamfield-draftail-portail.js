(() => {
    "use strict";

    const RACINE = ".streamfield-portail";
    const EVENEMENT = "draftail:toolbar";

    const ancrerBarres = () => {
        const racine = document.querySelector(RACINE);
        if (!racine || !racine.querySelector(".Draftail-Editor__wrapper")) {
            return;
        }

        // Wagtail synchronise officiellement les InlineToolbar via cet
        // événement. On l'utilise sans modifier la préférence persistante :
        // le choix du portail ne pollue ainsi pas le back-office.
        document.dispatchEvent(
            new CustomEvent(EVENEMENT, {
                detail: { toolbar: "sticky" },
            }),
        );
    };

    const installer = () => {
        const racine = document.querySelector(RACINE);
        if (!racine) {
            return;
        }

        let planifie = false;
        const planifier = () => {
            if (planifie) {
                return;
            }
            planifie = true;
            window.requestAnimationFrame(() => {
                planifie = false;
                ancrerBarres();
            });
        };

        // Les blocs RichText peuvent être présents au chargement ou ajoutés
        // ensuite par le StreamField. Le même contrat doit valoir dans les
        // deux cas.
        const observateur = new MutationObserver(planifier);
        observateur.observe(racine, { childList: true, subtree: true });

        planifier();
        window.setTimeout(ancrerBarres, 50);
        window.setTimeout(ancrerBarres, 250);
        window.setTimeout(ancrerBarres, 1000);
    };

    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", installer, { once: true });
    } else {
        installer();
    }
})();
