// Élément avec sa classe et, s'il y a lieu, son texte, placé tel quel (#142) :
// un message qui contient du HTML s'affiche, il n'est pas interprété.
function alertElement(tag, className, text = null, children = []) {
  const element = document.createElement(tag);
  element.className = className;
  if (text !== null) {
    element.textContent = text;
  }
  element.append(...children);
  return element;
}

// Forme commune des alertes (#154), celle des boutons pour les coins.
const ALERT_SHAPE = "rounded-xl border border-slate-200 bg-white p-3 shadow-lg";

// Icône d'un toast : SVG rendu par le gabarit de base (<template id="alert-icon-…">),
// cloné ici, plutôt qu'une police chargée depuis Internet (#218).
function alertIcon(name, className) {
  const icon = document.getElementById(`alert-icon-${name}`).content.firstElementChild.cloneNode(true);
  icon.classList.add(...className.split(" "));
  return icon;
}

window.Alert = (function () {
  /* --- TOASTS --- */

  // Par type : titre, icône, liseré, couleur du titre et de l'icône, barre de progression.
  // Classes écrites en entier, pour que Tailwind les trouve.
  const TOAST_TYPES = {
    info: { title: "Info", icon: "info", border: "border-l-blue-700", text: "text-blue-800", bar: "bg-blue-500" },
    success: { title: "Succès", icon: "check_circle", border: "border-l-green-700", text: "text-green-800", bar: "bg-green-500" },
    warning: { title: "Attention", icon: "warning", border: "border-l-amber-500", text: "text-amber-800", bar: "bg-amber-400" },
    error: { title: "Erreur", icon: "error", border: "border-l-red-700", text: "text-red-800", bar: "bg-red-500" },
  };

  let toastContainer = null;

  function ensureToastContainer() {
    if (!toastContainer) {
      toastContainer = alertElement(
        "div", "fixed top-4 right-4 z-[999999] flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2"
      );
      document.body.appendChild(toastContainer);
    }
  }

  function toast(message, options = {}) {
    ensureToastContainer();

    const {
      type = "info",
      has_title = true,
      title = "",
      duration = 5
    } = options;
    const style = TOAST_TYPES[type] ?? TOAST_TYPES.info;
    const duration_ms = duration * 1000;

    const text = [];
    if (has_title) {
      text.push(alertElement("p", `font-semibold ${style.text}`, title || style.title));
    }
    text.push(alertElement("p", "", message));

    const icon = alertIcon(style.icon, style.text);

    // Barre animée par alert_system.css : le script ne donne que la durée.
    const progressBar = alertElement("div", `alert__toast-progress absolute bottom-0 left-0 h-1 ${style.bar}`);
    progressBar.style.animationDuration = `${duration_ms}ms`;
    const toast = alertElement(
      "div",
      `alert__toast relative overflow-hidden ${ALERT_SHAPE} border-l-4 ${style.border}`,
      null,
      [alertElement("div", "flex items-start gap-2", null, [icon, alertElement("div", "min-w-0", null, text)]), progressBar]
    );
    toast.setAttribute("role", type === "error" ? "alert" : "status");
    toastContainer.appendChild(toast);

    requestAnimationFrame(() => {
      toast.classList.add("show");
    });

    setTimeout(() => {
      toast.classList.remove("show");
      setTimeout(() => toast.remove(), 300);
    }, duration_ms);
  }

  return {
    toast,
  };
})();

// content : éléments du contenu de la popover (voir alertElement).
function createPopoverBase(
  element, content,
  alignment = { "top": "top", "left": "right" }, margin_element_px = 5, margin_window_px = 10
) {
  let pop;
  let resolveReady;
  const ready = new Promise((resolve) => {
    resolveReady = resolve;
  });
  const close = new Promise((resolveClose) => {
    document.querySelectorAll(".alert__popover").forEach(el => el.remove());

    pop = alertElement("div", `alert__popover absolute z-[999999] min-w-48 max-w-80 select-none ${ALERT_SHAPE}`, null, content);

    document.body.appendChild(pop);

    resolveReady();

    // Positionnement selon l'alignement demandé
    const rect = element.getBoundingClientRect();
    const popRect = pop.getBoundingClientRect();

    let top = 0;
    let left = 0;

    if (alignment.hasOwnProperty('top') == true && alignment.hasOwnProperty('bottom') == true){
      console.error("Le popover ne doit pas avoir un alignement top et bottom définis en même temps.");
    } else if (alignment.hasOwnProperty('top') == true) {
      switch (alignment.top) {
        case "top":
          top = rect.top + window.scrollY;
          break;
        case "bottom":
          top = rect.bottom + window.scrollY + margin_element_px;
          break;
        default:
          console.warn(`Alignement top '${alignment.top}' non géré.`);
      }
    } else if (alignment.hasOwnProperty('bottom') == true) {
      switch (alignment.bottom) {
        default:
          console.warn(`Alignement bottom '${alignment.bottom}' non géré.`);
      }
    } else {
      console.error("Le popover doit avoir un alignement top ou bottom défini.");
    }

    if (alignment.hasOwnProperty('left') == true && alignment.hasOwnProperty('right') == true){
      console.error("Le popover ne doit pas avoir un alignement left et right définis en même temps.");
    } else if (alignment.hasOwnProperty('left') == true) {
      switch (alignment.left) {
        case "right":
          left = rect.right + window.scrollX + margin_element_px;
          break;
        case "left":
          left = rect.left + window.scrollX;
          break;
        default:
          console.warn(`Alignement left '${alignment.left}' non géré.`);
      }
    } else if (alignment.hasOwnProperty('right') == true) {
      switch (alignment.right) {
        default:
          console.warn(`Alignement right '${alignment.right}' non géré.`);
      }
    } else {
      console.error("Le popover doit avoir un alignement left ou right défini.");
    }

    // Ajustement si ça déborde à droite
    if (left + popRect.width > window.innerWidth - margin_window_px) {
      left = rect.left + window.scrollX - popRect.width - margin_window_px;
    }
    // Débordement en haut
    if (top < margin_window_px) top = margin_window_px;
    // Débordement en bas
    if (top + popRect.height > window.innerHeight + window.scrollY - margin_window_px) {
      top = window.innerHeight + window.scrollY - popRect.height - margin_window_px;
    }

    pop.style.top = top + "px";
    pop.style.left = left + "px";

    // Click en dehors = fermer
    const outsideClick = (e) => {
      if (!pop.contains(e.target) && e.target !== element) {
        pop.remove();
        resolveClose(false);
        document.removeEventListener("click", outsideClick);
      }
    };
    setTimeout(() => {
      document.addEventListener("click", outsideClick);
    });
  });

  return { pop, ready, close };
}
