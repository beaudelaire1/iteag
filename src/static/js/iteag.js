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
      // Re-init reveals on new content
      initReveals();
      animateCounters();
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
        // Only set delay if not already set via CSS nth-child or inline
        if (!child.style.transitionDelay) {
          child.style.transitionDelay = (i * 120) + "ms";
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
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
