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
