// Lecture d'une note (#404) : le plan, rendu par le serveur, et les sections, posées par
// `note_outline.py`. Sans ce script, le plan reste affiché et la note se lit en entier.
//
// - Bouton « Plan » (cloné du gabarit) : affiche ou masque le plan ; l'état est celui du
//   plan de l'éditeur (#314, même clé de `localStorage`), affiché si rien n'est gardé.
//   Sur une fenêtre étroite, il s'ouvre par-dessus la note et n'est pas gardé.
// - Chaque titre de section reçoit un bouton qui la replie, comme un <details> : le
//   contenu passe en `hidden`, le titre reste. Aller à un titre (plan, lien, adresse)
//   déplie les sections qui le cachent.
// - Le titre de la section lue est mis en évidence dans le plan (`aria-current`).
//
// Aussi pour la vue « Document » de la recherche (#431), remplacée par htmx : tout est
// alors remis en place sur le nouveau document, et les écouteurs de l'ancien sont retirés.
(function () {
    "use strict";

    // Un retour en arrière de htmx relance les scripts de la page : une seule mise en place.
    if (window.noteReadingStart) return window.noteReadingStart();

    let reading = null;
    let stop = null;

    function start() {
        const layout = document.querySelector("[data-note-reading]");
        if (layout === reading) return;
        const first = !stop;
        stop?.abort();
        reading = layout;
        stop = new AbortController();
        if (layout) setUp(layout, stop.signal, first);
    }

    const STORAGE_KEY = "note-outline-hidden";
    // Un titre est « lu » quand il passe sous la place des ancres (`scroll-padding`), et
    // un peu plus bas.
    const READING_MARGIN = 24;

    function setUp(layout, signal, first) {
        const nav = document.getElementById("note-outline");
        if (!nav) return;
        // Les classes que le script pose sont écrites dans le gabarit (reading.html).
        const { wide: wideQuery, wideGrid, floatingCell, floatingPlan, floatingList } = layout.dataset;
        const classes = (text) => text.split(" ");
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
            layout.classList.toggle(wideGrid, !hidden);
            toggle?.setAttribute("aria-expanded", String(!hidden));
        }

        // Fenêtre étroite : le plan n'a pas de colonne. Posé sur la feuille, en haut à droite, il
        // s'ouvre depuis le bouton où qu'on soit dans la note, et se referme une fois le titre
        // choisi. Feuille et plan partagent une case de la grille : rien ne bouge à l'ouverture.
        const wide = window.matchMedia(wideQuery);
        const template = document.getElementById("outline-toggle");
        const slot = document.querySelector("[data-outline-slot]");
        if (template && slot) {
            const toggle = template.content.firstElementChild.cloneNode(true);
            toggle.setAttribute("aria-controls", nav.id);
            // Remplacé : htmx garde le bouton posé dans une page où l'on revient.
            slot.replaceChildren(toggle);
            signal.addEventListener("abort", () => toggle.remove());
            nav.classList.add(...classes(floatingCell), ...classes(floatingPlan));
            list?.classList.add(...classes(floatingList));
            layout.querySelector("[data-note-frame]")?.classList.add(...classes(floatingCell));

            const reset = () => setHidden(wide.matches ? storedHidden() : true, toggle);
            reset();
            wide.addEventListener("change", reset, { signal });
            toggle.addEventListener("click", () => {
                const hidden = !nav.hidden;
                setHidden(hidden, toggle);
                if (!wide.matches) {
                    // Dans la page, le plan vient après la note : le clavier y va directement.
                    if (!hidden) {
                        highlight();
                        showCurrent();
                        (current ?? links[0])?.focus({ preventScroll: true });
                    }
                    return;
                }
                try {
                    localStorage.setItem(STORAGE_KEY, hidden ? "1" : "0");
                } catch {
                    // Un réglage non gardé n'empêche pas de lire.
                }
            });

            const floating = () => !wide.matches && !nav.hidden;
            nav.addEventListener("click", (event) => {
                if (floating() && event.target.closest("a")) setHidden(true, toggle);
            });
            document.addEventListener("pointerdown", (event) => {
                if (floating() && !nav.contains(event.target) && !toggle.contains(event.target)) setHidden(true, toggle);
            }, { signal });
            document.addEventListener("keydown", (event) => {
                if (event.key !== "Escape" || !floating()) return;
                setHidden(true, toggle);
                toggle.focus({ preventScroll: true });
            }, { signal });
        }

        // --- Sections repliables ---
        const icon = document.getElementById("section-toggle-icon");
        // Le texte d'un titre est celui du plan : sans la marque d'un lien (« nouvel onglet »).
        const titles = new Map(links.map((link) => [targetOf(link.getAttribute("href")), link.textContent.trim()]));

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
            heading?.querySelector("[data-section-toggle]")?.remove();
            const body = heading?.nextElementSibling;
            if (!heading || !body?.classList.contains("note-section-body")) continue;
            const button = document.createElement("button");
            button.type = "button";
            button.dataset.sectionToggle = "";
            button.className =
                "mr-1 inline-flex align-middle rounded text-slate-500 hover:bg-slate-100 focus-visible:outline-2 focus-visible:outline-blue-700";
            button.setAttribute("aria-controls", body.id);
            button.dataset.title = titles.get(heading) ?? heading.textContent.trim();
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
        }, { signal });
        window.addEventListener("hashchange", revealHash, { signal });
        if (first) revealHash();

        // --- Section lue ---
        const headings = links.map((link) => targetOf(link.getAttribute("href")));
        let current = null;

        /** Le titre lu reste visible dans la liste du plan, sans faire défiler la page. */
        function showCurrent() {
            if (!current || !list || nav.hidden) return;
            const linkTop = current.offsetTop - list.offsetTop;
            if (linkTop < list.scrollTop) list.scrollTop = linkTop;
            else if (linkTop + current.offsetHeight > list.scrollTop + list.clientHeight) {
                list.scrollTop = linkTop + current.offsetHeight - list.clientHeight;
            }
        }

        function highlight() {
            const edge = scroller === document.scrollingElement ? 0 : scroller.getBoundingClientRect().top;
            const top = edge + (parseFloat(getComputedStyle(scroller).scrollPaddingTop) || 0) + READING_MARGIN;
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
            showCurrent();
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
            { passive: true, signal },
        );
        highlight();

        // En-tête collant dont la hauteur change avec la largeur (recherche) : le plan et les
        // ancres se placent dessous.
        const bar = document.querySelector("[data-reading-bar]");
        if (bar) {
            const observer = new ResizeObserver(() => {
                scroller.style.setProperty("--reading-top", `${bar.offsetHeight}px`);
            });
            observer.observe(bar);
            signal.addEventListener("abort", () => observer.disconnect());
        }
    }

    window.noteReadingStart = start;
    start();
    document.addEventListener("htmx:afterSettle", start);
    document.addEventListener("htmx:historyRestore", start);
})();
