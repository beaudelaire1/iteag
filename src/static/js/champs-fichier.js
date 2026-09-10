/* ITEAG — habillage francophone des champs de dépôt de fichier.
 *
 * Le bouton d'un « input type=file » appartient au navigateur : son intitulé
 * suit la langue du navigateur, jamais celle de la page. Un visiteur dont le
 * système est en anglais lisait donc « Choose file / No file chosen » au
 * milieu d'un formulaire de candidature entièrement français, et rien dans le
 * document ne pouvait le corriger.
 *
 * La seule issue est de masquer le contrôle natif et d'en dessiner un. Ce
 * script le fait par-dessus le HTML servi, jamais à sa place : sans lui, le
 * champ natif reste visible et fonctionne. Le champ natif reste également le
 * seul à porter la valeur — le bouton dessiné ne fait que le déclencher.
 */
(function () {
  "use strict";

  const AUCUN = "Aucun fichier choisi";

  /** Nom du fichier choisi, ou l'annonce qu'il n'y en a pas. */
  function etat(entree) {
    const fichiers = entree.files;
    if (!fichiers || fichiers.length === 0) return AUCUN;
    if (fichiers.length === 1) return fichiers[0].name;
    return `${fichiers.length} fichiers choisis`;
  }

  function habiller(enveloppe) {
    if (enveloppe.dataset.champFichierPret === "oui") return;
    const entree = enveloppe.querySelector("input[type=file]");
    if (!entree) return;

    const bouton = document.createElement("button");
    bouton.type = "button";
    bouton.className = "champ-fichier__bouton";
    bouton.textContent = "Choisir un fichier";
    // Le champ natif reste dans l'ordre de tabulation et ouvre déjà le
    // sélecteur à l'espace ou à l'entrée. Laisser le bouton dessiné focusable
    // ferait deux arrêts pour un seul contrôle, dont un invisible ; il est
    // donc une commande de souris, doublée par le champ qu'il déclenche.
    bouton.tabIndex = -1;
    bouton.setAttribute("aria-hidden", "true");
    bouton.addEventListener("click", () => entree.click());

    const nom = document.createElement("span");
    nom.className = "champ-fichier__nom";
    nom.textContent = etat(entree);

    // Le nom du fichier change sans que l'utilisateur clavier ne voie la
    // boîte de dialogue : on l'annonce.
    nom.setAttribute("role", "status");

    entree.addEventListener("change", () => {
      nom.textContent = etat(entree);
      enveloppe.classList.toggle("champ-fichier--rempli", entree.files.length > 0);
    });

    // Le focus part sur le champ natif, devenu invisible : sans ce relais,
    // rien ne montrerait où l'on se trouve en naviguant au clavier.
    entree.addEventListener("focus", () => enveloppe.classList.add("champ-fichier--focus"));
    entree.addEventListener("blur", () => enveloppe.classList.remove("champ-fichier--focus"));

    enveloppe.append(bouton, nom);
    enveloppe.classList.add("champ-fichier--habille");
    enveloppe.dataset.champFichierPret = "oui";
  }

  function initChampsFichier(racine) {
    (racine || document).querySelectorAll("[data-champ-fichier]").forEach(habiller);
  }

  document.addEventListener("DOMContentLoaded", () => initChampsFichier());
  // Un fragment échangé par HTMX arrive après coup et n'a pas été habillé.
  document.body?.addEventListener("htmx:afterSwap", (evenement) => initChampsFichier(evenement.detail.target));
})();
