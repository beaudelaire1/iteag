(function () {
  "use strict";

  const formulaire = document.getElementById("formulaire-commande");
  if (!formulaire) return;

  const destination = formulaire.querySelector("[name=pays]");
  const typeLivraison = formulaire.querySelector("[name=type_livraison]");
  const frais = document.getElementById("frais-livraison");
  const total = document.getElementById("total-commande");
  const message = document.getElementById("message-livraison");
  const bouton = document.getElementById("bouton-commande");
  const alerteFormulaire = document.getElementById("alerte-livraison-formulaire");
  const erreurFormulaire = document.getElementById("erreur-livraison-formulaire");
  const formatEuro = new Intl.NumberFormat("fr-FR", {
    style: "currency",
    currency: "EUR",
  });
  let controleur = null;

  function indisponible(texte) {
    frais.textContent = "Indisponible";
    total.textContent = "—";
    message.textContent = texte;
    message.classList.add("text-red-700");
    erreurFormulaire.textContent = texte;
    alerteFormulaire.classList.remove("hidden");
    bouton.disabled = true;
  }

  async function actualiser() {
    if (!destination.value || !typeLivraison.value) {
      indisponible("Choisissez une destination et un type de livraison.");
      return;
    }

    if (controleur) controleur.abort();
    controleur = new AbortController();
    bouton.disabled = true;
    frais.textContent = "Calcul…";
    message.textContent = "Calcul du tarif à partir du panier…";
    message.classList.remove("text-red-700");
    alerteFormulaire.classList.add("hidden");

    const url = new URL(formulaire.dataset.devisUrl, window.location.origin);
    url.searchParams.set("destination", destination.value);
    url.searchParams.set("type_livraison", typeLivraison.value);

    try {
      const reponse = await fetch(url, {
        headers: { Accept: "application/json" },
        signal: controleur.signal,
      });
      const donnees = await reponse.json();
      if (!reponse.ok || !donnees.disponible) {
        indisponible(donnees.message || "Aucun tarif n'est disponible.");
        return;
      }

      frais.textContent = donnees.livraison_offerte
        ? "Offerte"
        : formatEuro.format(Number(donnees.frais_livraison));
      total.textContent = formatEuro.format(Number(donnees.total_commande));
      message.textContent = donnees.livraison_offerte
        ? `Livraison offerte : le panier atteint ${formulaire.dataset.seuilLivraisonOfferte} €.`
        : "Frais de livraison calculés.";
      message.classList.remove("text-red-700");
      alerteFormulaire.classList.add("hidden");
      bouton.disabled = false;
    } catch (erreur) {
      if (erreur.name !== "AbortError") {
        indisponible("Veuillez actualiser la page pour recalculer les frais de livraison.");
      }
    }
  }

  destination.addEventListener("change", actualiser);
  typeLivraison.addEventListener("change", actualiser);
  actualiser();
})();
