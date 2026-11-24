// Lecture d'une note (#404) : le plan, rendu par le serveur, et les sections, posées par
// `note_outline.py`. Sans ce script, le plan reste affiché et la note se lit en entier.
//
// - Bouton « Plan » (cloné du gabarit) : affiche ou masque le plan ; l'état est celui du
//   plan de l'éditeur (#314, même clé de `localStorage`), affiché si rien n'est gardé.
// - Chaque titre de section reçoit un bouton qui la replie, comme un <details> : le
//   contenu passe en `hidden`, le titre reste. Aller à un titre (plan, lien, adresse)
//   déplie les sections qui le cachent.
// - Le titre de la section lue est mis en évidence dans le plan (`aria-current`).
(function () {
    "use strict";

    const STORAGE_KEY = "note-outline-hidden";
    const GRID_CLASS = "lg:grid-cols-[minmax(0,240mm)_16rem]";
    // Un titre est « lu » quand il passe sous ce seuil, depuis le haut de la zone qui défile.
    const READING_OFFSET = 96;

    const layout = document.querySelector("[data-note-reading]");
    const nav = document.getElementById("note-outline");
    if (!layout || !nav) return;
    const content = layout.querySelector("[data-note-content]");
    const scroller = document.getElementById("contenu") ?? document.scrollingElement;
    const links = [...nav.querySelectorAll('a[href^="#"]')];
    const list = nav.querySelector("ul");

    function targetOf(hash) {
        if (!hash || hash === "#") return null;
        try {
            return document.getElementById(decodeURIComponent(hash.slice(1)));
        } catch {
            return null;
        }
    }

    // --- Plan affiché ou masqué ---
    function storedHidden() {
        try {
            return localStorage.getItem(STORAGE_KEY) === "1";
        } catch {
            return false;
        }
    }

    function setHidden(hidden, toggle) {
        nav.hidden = hidden;
        layout.classList.toggle(GRID_CLASS, !hidden);
        toggle?.setAttribute("aria-expanded", String(!hidden));
    }

    const template = document.getElementById("outline-toggle");
    const header = document.querySelector("main header");
    if (template && header) {
        const toggle = template.content.firstElementChild.cloneNode(true);
        toggle.setAttribute("aria-controls", nav.id);
        header.querySelector("h1")?.after(toggle);
        setHidden(storedHidden(), toggle);
        toggle.addEventListener("click", () => {
            const hidden = !nav.hidden;
            setHidden(hidden, toggle);
            try {
                localStorage.setItem(STORAGE_KEY, hidden ? "1" : "0");
            } catch {
                // Un réglage non gardé n'empêche pas de lire.
            }
        });
    }

    // --- Sections repliables ---
    const icon = document.getElementById("section-toggle-icon");

    function setFolded(button, folded) {
        const body = document.getElementById(button.getAttribute("aria-controls"));
        if (!body) return;
        body.hidden = folded;
        button.setAttribute("aria-expanded", String(!folded));
        const title = button.dataset.title;
        button.setAttribute("aria-label", `${folded ? "Déplier" : "Replier"} la section « ${title} »`);
    }

    for (const section of content.querySelectorAll("section.note-section")) {
        const heading = section.firstElementChild;
        const body = heading?.nextElementSibling;
        if (!heading || !body?.classList.contains("note-section-body")) continue;
        const button = document.createElement("button");
        button.type = "button";
        button.className =
            "mr-1 inline-flex align-middle rounded text-slate-500 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-blue-700";
        button.setAttribute("aria-controls", body.id);
        button.dataset.title = heading.textContent.trim();
        if (icon) button.append(icon.content.firstElementChild.cloneNode(true));
        heading.prepend(button);
        setFolded(button, false);
        button.addEventListener("click", () => {
            setFolded(button, button.getAttribute("aria-expanded") === "true");
            highlight();
        });
    }

    /** Déplie les sections qui cachent `element`. */
    function reveal(element) {
        for (let body = element?.closest(".note-section-body"); body; body = body.parentElement.closest(".note-section-body")) {
            if (!body.hidden) continue;
            const button = content.querySelector(`button[aria-controls="${body.id}"]`);
            if (button) setFolded(button, false);
        }
    }

    function revealHash() {
        const target = targetOf(location.hash);
        if (!target) return;
        reveal(target);
        target.scrollIntoView();
    }

    // Avant la navigation vers l'ancre : la cible doit être visible pour qu'on y aille.
    document.addEventListener("click", (event) => {
        const link = event.target.closest?.('a[href^="#"]');
        if (link) reveal(targetOf(link.getAttribute("href")));
    });
    window.addEventListener("hashchange", revealHash);
    revealHash();

    // --- Section lue ---
    const headings = links.map((link) => targetOf(link.getAttribute("href")));
    let current = null;

    function highlight() {
        const top = (scroller === document.scrollingElement ? 0 : scroller.getBoundingClientRect().top) + READING_OFFSET;
        // Un titre caché par une section repliée n'a pas de boîte : il ne compte pas.
        const shown = (heading) => heading && heading.getClientRects().length > 0;
        let index = 0;
        headings.forEach((heading, i) => {
            if (shown(heading) && heading.getBoundingClientRect().top <= top) index = i;
        });
        // En bas de la page, les derniers titres n'atteignent jamais le seuil : le dernier
        // titre visible est alors celui qu'on lit.
        const box = scroller === document.scrollingElement ? document.documentElement : scroller;
        if (box.scrollTop > 0 && box.scrollTop + box.clientHeight >= box.scrollHeight - 2) {
            const last = headings.findLastIndex(shown);
            if (last > index) index = last;
        }
        const link = links[index];
        if (link === current) return;
        current?.removeAttribute("aria-current");
        link?.setAttribute("aria-current", "location");
        current = link;
        // Le titre lu reste visible dans la liste du plan, sans faire défiler la page.
        if (link && list) {
            const linkTop = link.offsetTop - list.offsetTop;
            if (linkTop < list.scrollTop) list.scrollTop = linkTop;
            else if (linkTop + link.offsetHeight > list.scrollTop + list.clientHeight) {
                list.scrollTop = linkTop + link.offsetHeight - list.clientHeight;
            }
        }
    }

    let pending = false;
    (scroller === document.scrollingElement ? window : scroller).addEventListener(
        "scroll",
        () => {
            if (pending) return;
            pending = true;
            requestAnimationFrame(() => {
                pending = false;
                highlight();
            });
        },
        { passive: true },
    );
    highlight();
})();
