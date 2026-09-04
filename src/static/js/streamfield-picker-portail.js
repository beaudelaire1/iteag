(() => {
  const SELECTEUR = '.streamfield-portail .c-sf-add-button';
  const MARQUEUR = 'iteagPickerPositionne';

  /**
   * Wagtail 7 crée le picker avec `placement: "bottom"`. Dans un portail où
   * le formulaire peut occuper toute la hauteur de l'écran, ce choix fait
   * sortir le panneau du viewport pour les points d'insertion bas.
   *
   * On ne remplace ni Tippy ni Popper : on ajuste l'instance officielle une
   * seule fois afin qu'elle choisisse le côté qui dispose réellement de la
   * place et qu'elle reste contenue dans le viewport.
   */
  const configurer = (bouton) => {
    if (!bouton || bouton.dataset[MARQUEUR] === 'true') return;

    const instance = bouton._tippy;
    if (!instance || typeof instance.setProps !== 'function') return;

    instance.setProps({
      placement: 'auto',
      popperOptions: {
        modifiers: [
          {
            name: 'flip',
            options: {
              allowedAutoPlacements: ['top', 'bottom'],
              fallbackPlacements: ['top', 'bottom'],
              padding: 8,
            },
          },
          {
            name: 'preventOverflow',
            options: {
              boundary: 'viewport',
              rootBoundary: 'viewport',
              padding: 8,
              altAxis: true,
              tether: true,
            },
          },
        ],
      },
    });

    bouton.dataset[MARQUEUR] = 'true';
  };

  const scanner = (racine = document) => {
    if (racine.matches?.(SELECTEUR)) configurer(racine);
    racine.querySelectorAll?.(SELECTEUR).forEach(configurer);
  };

  /**
   * Wagtail attache Tippy après avoir inséré le bouton. Un balayage déclenché
   * par l'insertion arrive donc parfois avant l'instance : `configurer` sortait
   * alors sans rien faire, et plus rien ne repassait sur ce bouton — qui
   * gardait le `placement: "bottom"` d'origine et ouvrait son panneau hors de
   * l'écran. On reconfigure donc aussi juste avant l'ouverture, en phase de
   * capture : à cet instant l'instance existe forcément.
   */
  const configurerAvantOuverture = (evenement) => {
    const bouton = evenement.target?.closest?.(SELECTEUR);
    if (bouton) configurer(bouton);
  };

  const demarrer = () => {
    scanner();

    ['mousedown', 'focusin', 'keydown'].forEach((evenement) => {
      document.addEventListener(evenement, configurerAvantOuverture, true);
    });

    const observateur = new MutationObserver((mutations) => {
      mutations.forEach((mutation) => {
        mutation.addedNodes.forEach((noeud) => {
          if (noeud.nodeType === Node.ELEMENT_NODE) scanner(noeud);
        });
      });
    });

    observateur.observe(document.body, { childList: true, subtree: true });
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', demarrer, { once: true });
  } else {
    demarrer();
  }
})();
