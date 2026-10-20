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

window.Alert = (function () {
  /* --- SYSTEME DE MODAL (alert/confirm) --- */

  function createModal({ message, showCancel = false }) {
    return new Promise((resolve) => {

      const overlay = document.createElement("div");
      overlay.className = "alert__overlay";

      const buttons = [alertElement("button", "alert__ok", "OK")];
      if (showCancel) {
        buttons.push(alertElement("button", "alert__cancel", "Annuler"));
      }
      const modal = alertElement("div", "alert__modal", null, [
        alertElement("p", "alert__message", message),
        alertElement("div", "alert__buttons", null, buttons),
      ]);

      overlay.appendChild(modal);
      document.body.appendChild(overlay);

      modal.querySelector(".alert__ok").onclick = () => {
        overlay.remove();
        resolve(true);
      };

      const cancelBtn = modal.querySelector(".alert__cancel");
      if (cancelBtn) {
        cancelBtn.onclick = () => {
          overlay.remove();
          resolve(false);
        };
      }
    });
  }

  /* --- TOASTS --- */

  let toastContainer = null;

  function ensureToastContainer() {
    if (!toastContainer) {
      toastContainer = document.createElement("div");
      toastContainer.className = "alert__toast-container";
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

    let display_title;
    switch (type) {
      case "info":
        display_title = "Info";
        break;
      case "success":
        display_title = "Succès";
        break;
      case "error":
        display_title = "Erreur";
        break;
      case "warning":
        display_title = "Attention";
        break;
      default:
        display_title = "Titre";
        break;
    }

    if (title != "") {
      display_title = title
    }

    const duration_ms = duration * 1000;

    const content = [];
    if (has_title) {
      content.push(alertElement("h6", "alert__toast-title", display_title));
    }
    content.push(alertElement("p", "alert__toast-text", message));

    const toast = alertElement("div", `alert__toast alert__toast-${type}`, null, [
      alertElement("div", "alert__toast-content", null, content),
      alertElement("div", "alert__toast-progress-behind"),
      alertElement("div", "alert__toast-progress"),
    ]);
    toastContainer.appendChild(toast);

    requestAnimationFrame(() => {
      toast.classList.add("show");
    });

    const progressBar = toast.querySelector(".alert__toast-progress");
    progressBar.style.transition = `width ${duration_ms}ms linear`;
    void progressBar.offsetWidth;
    progressBar.style.width = "0%";
    requestAnimationFrame(() => {
      progressBar.style.width = "0%";
    });

    setTimeout(() => {
      toast.classList.remove("show");
      setTimeout(() => toast.remove(), 300);
    }, duration_ms);
  }

  /* --- POPOVER --- */
  async function confirmAt(element, message, {
    ok_data = {
      message: "Supprimer",
      class_suffix: 'pop-ok',
      order: 0
    },
    cancel_data = {
      message: "Annuler",
      class_suffix: 'pop-cancel',
      order: 1
    }
  } = {}) {
    const buttons_data = [ok_data, cancel_data]
    const ordered_buttons = Array(buttons_data.length)
    for (const button_data of buttons_data) {
      ordered_buttons[button_data.order] = button_data
    }

    const buttons = [];
    for (const button_data of ordered_buttons) {
      if (typeof button_data == 'undefined') {
        throw new Error(`Le bouton est vide.`);
      }

      buttons.push(
        alertElement("button", `alert__${button_data.class_suffix}`, button_data.message)
      );
    }
    const content = [
      alertElement("p", "alert__popover-message", message),
      alertElement("div", "alert__popover-buttons", null, buttons),
    ];
    const { pop, ready, close } = createPopoverBase(element, content);

    await ready;

    return new Promise((resolve) => {
      pop.querySelector(".alert__pop-ok").onclick = () => {
        pop.remove();
        resolve(true);
      };
      pop.querySelector(".alert__pop-cancel").onclick = () => {
        pop.remove();
        resolve(false);
      };

      close.then(() => resolve(false));
    });
  }

  return {
    alert(message) {
      return createModal({ message, showCancel: false });
    },
    confirm(message) {
      return createModal({ message, showCancel: true });
    },
    toast,
    confirmAt,
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

    pop = alertElement("div", "alert__popover", null, content);

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
