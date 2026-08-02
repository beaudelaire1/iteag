/* ═══════════════════════════════════════════════════════════════
   ITEAG — JavaScript Global · Standard Trait d'Union Studio
   Vanilla JS · IntersectionObserver · HTMX events
   Architecture propriétaire — zéro dépendance externe
   ═══════════════════════════════════════════════════════════════ */

(function () {
  "use strict";

  /* ── 1. Scroll Reveal (IntersectionObserver) ── */
  const revealObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("revealed");
          revealObserver.unobserve(entry.target);
        }
      });
    },
    { threshold: 0.06, rootMargin: "0px 0px -60px 0px" }
  );

  function initReveals() {
    document
      .querySelectorAll(".reveal:not(.revealed), .reveal-left:not(.revealed), .reveal-right:not(.revealed), .reveal-scale:not(.revealed), .reveal-fade:not(.revealed), .reveal-blur:not(.revealed), .text-reveal-line:not(.revealed), .border-draw:not(.revealed)")
      .forEach((el) => {
        revealObserver.observe(el);
      });
  }

  /* ── 2. Navigation scroll effect ── */
  function initNavScroll() {
    const nav = document.querySelector(".nav-premium");
    if (!nav) return;
    const onScroll = () => {
      nav.classList.toggle("scrolled", window.scrollY > 20);
    };
    window.addEventListener("scroll", onScroll, { passive: true });
    onScroll();
  }

  /* ── 3. Counter animation (stat numbers) ── */
  function animateCounters() {
    const counters = document.querySelectorAll("[data-counter]");
    if (!counters.length) return;

    const counterObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          const el = entry.target;
          const target = parseInt(el.dataset.counter, 10);
          const suffix = el.dataset.counterSuffix || "";
          const duration = 2000;
          const start = performance.now();

          el.classList.add("counted");

          function step(now) {
            const progress = Math.min((now - start) / duration, 1);
            const eased = 1 - Math.pow(1 - progress, 4); // easeOutQuart
            el.textContent = Math.round(target * eased).toLocaleString("fr-FR") + suffix;
            if (progress < 1) requestAnimationFrame(step);
          }
          requestAnimationFrame(step);
          counterObserver.unobserve(el);
        });
      },
      { threshold: 0.3 }
    );
    counters.forEach((el) => counterObserver.observe(el));
  }

  /* ── 4. HTMX event handlers ── */
  function initHTMX() {
    // CSRF token injection
    document.body.addEventListener("htmx:configRequest", (e) => {
      const match = document.cookie.match(/csrftoken=([^;]+)/);
      if (match) e.detail.headers["X-CSRFToken"] = match[1];
      const hidden = document.querySelector("[name=csrfmiddlewaretoken]");
      if (hidden) e.detail.headers["X-CSRFToken"] = hidden.value;
    });

    // Fade-in newly swapped content
    document.body.addEventListener("htmx:afterSwap", (e) => {
      e.detail.target.classList.add("htmx-swap-fade");
      // Ré-initialisation sur le contenu fraîchement inséré
      initReveals();
      animateCounters();
      initMessagesFlash();
      initOnglets();
    });

    // Loading state management
    document.body.addEventListener("htmx:beforeRequest", (e) => {
      const trigger = e.detail.elt;
      if (trigger && trigger.dataset.htmxLoading) {
        trigger.classList.add("opacity-50", "pointer-events-none");
      }
    });
    document.body.addEventListener("htmx:afterRequest", (e) => {
      const trigger = e.detail.elt;
      if (trigger && trigger.dataset.htmxLoading) {
        trigger.classList.remove("opacity-50", "pointer-events-none");
      }
    });
  }

  /* ── 5. Smooth anchor scroll (complement to CSS scroll-behavior) ── */
  function initSmoothAnchors() {
    document.querySelectorAll('a[href^="#"]').forEach((anchor) => {
      anchor.addEventListener("click", (e) => {
        const target = document.querySelector(anchor.getAttribute("href"));
        if (!target) return;
        e.preventDefault();
        target.scrollIntoView({ behavior: "smooth", block: "start" });
        // Update URL without jump
        history.pushState(null, "", anchor.getAttribute("href"));
      });
    });
  }

  /* ── 6. Stagger reveal (CSS natif — échelonnement progressif) ── */
  function initStagger() {
    document.querySelectorAll("[data-motion-stagger]").forEach((container) => {
      const children = Array.from(container.children);
      children.forEach((child, i) => {
        if (!child.classList.contains("reveal") &&
            !child.classList.contains("reveal-left") &&
            !child.classList.contains("reveal-right") &&
            !child.classList.contains("reveal-scale") &&
            !child.classList.contains("reveal-blur")) {
          child.classList.add("reveal");
        }
        // Une cascade courte conserve le rythme visuel sans faire attendre les
        // derniers éléments d'une grille pendant plus d'une seconde.
        if (!child.style.transitionDelay) {
          child.style.transitionDelay = Math.min(i * 45, 300) + "ms";
        }
      });
    });

    // Hero entrance — progressive reveal with cinematic delay
    const heroes = document.querySelectorAll("[data-motion-hero]");
    heroes.forEach((hero) => {
      hero.classList.add("reveal");
      // Force immediate reveal for hero (above fold)
      requestAnimationFrame(() => {
        hero.classList.add("revealed");
      });
    });
  }

  /* ── 7. Progress bar animation ── */
  function initProgressBars() {
    document.querySelectorAll("[data-progress]").forEach((bar) => {
      const fill = bar.querySelector(".progress-bar-fill");
      if (!fill) return;
      const observer = new IntersectionObserver(
        (entries) => {
          entries.forEach((entry) => {
            if (entry.isIntersecting) {
              fill.style.width = bar.dataset.progress + "%";
              observer.unobserve(bar);
            }
          });
        },
        { threshold: 0.5 }
      );
      observer.observe(bar);
    });
  }

  /* ── 8. Parallax-lite (scroll depth subtil) ── */
  function initParallax() {
    const elements = document.querySelectorAll("[data-parallax]");
    if (!elements.length) return;

    function updateParallax() {
      const scrollY = window.scrollY;
      elements.forEach((el) => {
        const speed = parseFloat(el.dataset.parallax) || 0.1;
        const rect = el.getBoundingClientRect();
        const center = rect.top + rect.height / 2;
        const offset = (center - window.innerHeight / 2) * speed;
        el.style.transform = "translateY(" + offset + "px)";
      });
    }

    // Use rAF throttle for performance
    let ticking = false;
    window.addEventListener("scroll", () => {
      if (!ticking) {
        requestAnimationFrame(() => {
          updateParallax();
          ticking = false;
        });
        ticking = true;
      }
    }, { passive: true });
    updateParallax();
  }

  /* ── 9. Text reveal — line-by-line entrance ── */
  function initTextReveal() {
    document.querySelectorAll(".text-reveal-line").forEach((el) => {
      // Wrap inner text in span if not already wrapped
      if (!el.querySelector("span")) {
        const span = document.createElement("span");
        span.textContent = el.textContent;
        el.textContent = "";
        el.appendChild(span);
      }
    });
    // The .revealed class is added by the standard revealObserver
  }

  /* ── 10. Menu mobile ── */

  /**
   * Affiche ou masque un élément par l'attribut « hidden ».
   *
   * « element.hidden = true » ne vaut que pour le HTML : SVGElement n'expose
   * pas cette propriété, l'affectation posait une propriété inerte sur l'objet
   * et l'attribut ne bougeait pas. Les deux icônes du bouton étant des SVG, la
   * croix ne s'affichait jamais et le trait triple ne disparaissait pas — le
   * menu s'ouvrait sans que le bouton le dise.
   */
  function afficher(element, visible) {
    if (!element) return;
    if (visible) element.removeAttribute("hidden");
    else element.setAttribute("hidden", "");
  }

  function initMenuMobile() {
    const bouton = document.querySelector("[data-nav-toggle]");
    const panneau = document.querySelector("[data-nav-panel]");
    if (!bouton || !panneau) return;

    const iconeOuvrir = bouton.querySelector("[data-nav-icone-ouvrir]");
    const iconeFermer = bouton.querySelector("[data-nav-icone-fermer]");
    const grandEcran = window.matchMedia("(min-width: 1024px)");

    function definir(ouvert) {
      bouton.setAttribute("aria-expanded", String(ouvert));
      afficher(panneau, ouvert);
      afficher(iconeOuvrir, !ouvert);
      afficher(iconeFermer, ouvert);
      // Le fond ne défile plus derrière le menu ouvert.
      document.documentElement.classList.toggle("menu-ouvert", ouvert);
    }

    bouton.addEventListener("click", () => {
      definir(bouton.getAttribute("aria-expanded") !== "true");
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") definir(false);
    });
    // Un lien suivi referme le panneau.
    panneau.addEventListener("click", (e) => {
      if (e.target.closest("a")) definir(false);
    });
    // Passé en grand écran, le panneau est masqué par la mise en page mais son
    // état resterait « ouvert » — et le défilement, bloqué.
    grandEcran.addEventListener("change", (e) => {
      if (e.matches) definir(false);
    });
  }

  /* ── 10 bis. Rubriques de la barre publique ──
     Les panneaux s'ouvrent en CSS, au survol et à la prise de focus : c'est ce
     qui les rend atteignables sans script. Mais au doigt, « :hover » ne se
     déclenche pas — sur une tablette assez large pour recevoir la barre de
     bureau, le premier appui suivait le lien de l'intitulé et le panneau ne
     s'ouvrait jamais. Ses entrées étaient alors hors de portée.

     Le complément ci-dessous n'ajoute qu'un cas : sans survol, le premier
     appui ouvre, le second suit le lien. Rien n'est retiré. */
  function initRubriques() {
    const rubriques = document.querySelectorAll("[data-rubrique]");
    if (!rubriques.length) return;

    function fermerTous(sauf) {
      rubriques.forEach((rubrique) => {
        if (rubrique === sauf) return;
        rubrique.classList.remove("ouverte");
        const intitule = rubrique.querySelector("[data-rubrique-intitule]");
        if (intitule) intitule.setAttribute("aria-expanded", "false");
      });
    }

    rubriques.forEach((rubrique) => {
      const intitule = rubrique.querySelector("[data-rubrique-intitule]");
      if (!intitule) return;
      // L'état n'est annoncé que là où il existe, c'est-à-dire dès qu'il y a un
      // script pour le tenir à jour.
      intitule.setAttribute("aria-expanded", "false");

      intitule.addEventListener("click", (e) => {
        // Évalué à chaque fois : un appareil hybride change de mode d'entrée
        // en cours de séance.
        if (!window.matchMedia("(hover: none)").matches) return;
        if (rubrique.classList.contains("ouverte")) return; // second appui : on suit le lien
        e.preventDefault();
        fermerTous(rubrique);
        rubrique.classList.add("ouverte");
        intitule.setAttribute("aria-expanded", "true");
      });

      // Le survol et le focus ouvrent le panneau en CSS ; l'état annoncé aux
      // technologies d'assistance doit dire la même chose.
      rubrique.addEventListener("mouseenter", () => intitule.setAttribute("aria-expanded", "true"));
      rubrique.addEventListener("mouseleave", () => {
        if (!rubrique.classList.contains("ouverte")) intitule.setAttribute("aria-expanded", "false");
      });
      rubrique.addEventListener("focusin", () => intitule.setAttribute("aria-expanded", "true"));
      rubrique.addEventListener("focusout", (e) => {
        if (rubrique.contains(e.relatedTarget)) return;
        if (!rubrique.classList.contains("ouverte")) intitule.setAttribute("aria-expanded", "false");
      });
    });

    document.addEventListener("click", (e) => {
      if (!e.target.closest("[data-rubrique]")) fermerTous(null);
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") fermerTous(null);
    });
  }

  /* ── 11. Menus déroulants (clic extérieur, Échap) ── */
  function initMenusDeroulants() {
    const menus = document.querySelectorAll("[data-dropdown]");
    if (!menus.length) return;

    function fermerTous(sauf) {
      menus.forEach((menu) => {
        if (menu === sauf) return;
        menu.querySelector("[data-dropdown-toggle]").setAttribute("aria-expanded", "false");
        menu.querySelector("[data-dropdown-panel]").hidden = true;
      });
    }

    menus.forEach((menu) => {
      const bouton = menu.querySelector("[data-dropdown-toggle]");
      const panneau = menu.querySelector("[data-dropdown-panel]");
      if (!bouton || !panneau) return;

      bouton.addEventListener("click", (e) => {
        e.stopPropagation();
        const ouvrir = bouton.getAttribute("aria-expanded") !== "true";
        fermerTous(menu);
        bouton.setAttribute("aria-expanded", String(ouvrir));
        panneau.hidden = !ouvrir;
      });
    });

    document.addEventListener("click", () => fermerTous(null));
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") fermerTous(null);
    });
  }

  /* ── 12. Messages flash (fermeture manuelle ou automatique) ── */
  function initMessagesFlash() {
    document.querySelectorAll("[data-flash]").forEach((flash) => {
      if (flash.dataset.flashInit) return;
      flash.dataset.flashInit = "1";

      function masquer() {
        flash.classList.add("flash-sortant");
        flash.addEventListener("transitionend", () => flash.remove(), { once: true });
        // Filet si la transition ne se déclenche pas (mouvement réduit).
        setTimeout(() => flash.remove(), 400);
      }

      const fermeture = flash.querySelector("[data-flash-close]");
      if (fermeture) fermeture.addEventListener("click", masquer);

      const delai = parseInt(flash.dataset.flash, 10);
      if (delai > 0) setTimeout(masquer, delai);
    });
  }

  /* ── 13. Affichage du mot de passe ── */
  function initRevelationMotDePasse() {
    document.querySelectorAll("[data-password-toggle]").forEach((bouton) => {
      const champ = document.getElementById(bouton.dataset.passwordToggle);
      if (!champ) return;
      const iconeAffiche = bouton.querySelector("[data-password-icone-affiche]");
      const iconeMasque = bouton.querySelector("[data-password-icone-masque]");

      bouton.addEventListener("click", () => {
        const devientVisible = champ.type === "password";
        champ.type = devientVisible ? "text" : "password";
        bouton.setAttribute("aria-pressed", String(devientVisible));
        bouton.setAttribute(
          "aria-label",
          devientVisible ? "Masquer le mot de passe" : "Afficher le mot de passe"
        );
        // Deux SVG : « afficher » passe par l'attribut, faute de quoi rien ne
        // bougerait — voir le commentaire de la fonction.
        afficher(iconeAffiche, !devientVisible);
        afficher(iconeMasque, devientVisible);
      });
    });
  }

  /* ── 14. Onglets ── */
  function initOnglets() {
    document.querySelectorAll("[data-tabs]").forEach((groupe) => {
      const boutons = groupe.querySelectorAll("[data-tab]");
      const panneaux = groupe.querySelectorAll("[data-tab-panel]");
      if (!boutons.length) return;

      function activer(nom) {
        boutons.forEach((b) => {
          b.setAttribute("aria-selected", String(b.dataset.tab === nom));
        });
        panneaux.forEach((p) => {
          p.hidden = p.dataset.tabPanel !== nom;
        });
      }

      const noms = Array.from(boutons, (bouton) => bouton.dataset.tab);
      boutons.forEach((b) =>
        b.addEventListener("click", () => {
          activer(b.dataset.tab);
          history.replaceState(null, "", `#${b.dataset.tab}`);
        })
      );
      document.querySelectorAll("[data-tab-trigger]").forEach((declencheur) => {
        if (!noms.includes(declencheur.dataset.tabTrigger)) return;
        declencheur.addEventListener("click", () => activer(declencheur.dataset.tabTrigger));
      });

      const ongletDemande = window.location.hash.slice(1);
      activer(noms.includes(ongletDemande) ? ongletDemande : boutons[0].dataset.tab);
    });
  }

  /* ── Alertes effaçables ──
     Un bandeau qu'on ne peut pas écarter finit par ne plus être lu, et occupe
     le haut de l'écran à chaque visite. Écarté, il mémorise la valeur qu'il
     annonçait — le nombre de cours ouverts, par exemple — et reparaît de
     lui-même dès que cette valeur change. Écarter « pour toujours » ferait
     manquer l'annonce suivante.

     L'alerte est rendue avec « hidden » et n'est révélée qu'ici : sans script,
     rien ne clignote à l'affichage. En contrepartie elle reste invisible si le
     script ne s'exécute pas — c'est un rappel, jamais une information dont la
     page dépend.

     Le stockage local peut être refusé (navigation privée stricte, réglage
     d'entreprise) : dans ce cas l'alerte s'affiche et s'écarte pour la session
     en cours, sans erreur. */
  function memoireLocale() {
    try {
      const essai = "__iteag__";
      window.localStorage.setItem(essai, "1");
      window.localStorage.removeItem(essai);
      return window.localStorage;
    } catch (e) {
      return null;
    }
  }

  function initAlertesEffacables() {
    const memoire = memoireLocale();

    document.querySelectorAll("[data-alerte-effacable]").forEach((alerte) => {
      const cle = "alerte:" + alerte.getAttribute("data-alerte-effacable");
      const valeur = alerte.getAttribute("data-alerte-valeur") || "1";

      if (memoire && memoire.getItem(cle) === valeur) return;
      alerte.removeAttribute("hidden");

      const fermer = alerte.querySelector("[data-alerte-fermer]");
      if (!fermer) return;
      fermer.addEventListener("click", () => {
        alerte.setAttribute("hidden", "");
        if (memoire) memoire.setItem(cle, valeur);
      });
    });
  }

  /* ── Boot ── */
  function boot() {
    initNavScroll();
    initTextReveal();
    initReveals();
    animateCounters();
    initHTMX();
    initSmoothAnchors();
    initProgressBars();
    initStagger();
    initParallax();
    initMenuMobile();
    initRubriques();
    initMenusDeroulants();
    initMessagesFlash();
    initRevelationMotDePasse();
    initOnglets();
    initAlertesEffacables();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
