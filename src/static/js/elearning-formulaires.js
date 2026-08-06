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

  document.querySelectorAll("[data-duree-minutes-form]").forEach(bindDurationForm);
  document.querySelectorAll("[data-lecon-form]").forEach(bindLessonType);
  document.querySelectorAll("[data-module-form]").forEach(bindAccessPolicy);
})();
