(() => {
  "use strict";

  const racine = document.getElementById("paiement-checkout");
  if (!racine) return;

  const chargement = document.getElementById("paiement-chargement");
  const erreur = document.getElementById("paiement-erreur");
  const message = erreur?.querySelector("[data-paiement-message]");
  const boutonReessayer = erreur?.querySelector("[data-paiement-reessayer]");
  const jetonCsrf = document.querySelector('[name="csrfmiddlewaretoken"]')?.value;

  const afficherErreur = (detail) => {
    chargement?.classList.add("hidden");
    document.getElementById("stripe-checkout")?.classList.add("hidden");
    if (message && detail) message.textContent = detail;
    erreur?.classList.remove("hidden");
  };

  const initialiser = async () => {
    erreur?.classList.add("hidden");
    chargement?.classList.remove("hidden");

    if (typeof window.Stripe !== "function") {
      afficherErreur("La connexion sécurisée à Stripe a échoué.");
      return;
    }

    try {
      const stripe = window.Stripe(racine.dataset.clePubliable);
      const checkout = await stripe.initEmbeddedCheckout({
        fetchClientSecret: async () => {
          const reponse = await fetch(racine.dataset.sessionUrl, {
            method: "POST",
            credentials: "same-origin",
            headers: {
              "X-CSRFToken": jetonCsrf,
              "X-Requested-With": "XMLHttpRequest",
            },
          });
          const contenu = await reponse.json();

          if (contenu.redirect_url) {
            window.location.assign(contenu.redirect_url);
            return new Promise(() => {});
          }
          if (!reponse.ok || !contenu.client_secret) {
            throw new Error(contenu.message || "Le service de paiement ne répond pas.");
          }
          return contenu.client_secret;
        },
      });

      chargement?.classList.add("hidden");
      document.getElementById("stripe-checkout")?.classList.remove("hidden");
      checkout.mount("#stripe-checkout");
    } catch (cause) {
      afficherErreur(cause instanceof Error ? cause.message : "");
    }
  };

  boutonReessayer?.addEventListener("click", initialiser);
  initialiser();
})();
