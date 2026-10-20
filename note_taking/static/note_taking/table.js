async function tableColumnOptions(columnButton) {
    var pop_html = `
    <p>Test</p>
    `
    const { pop, ready, close } = createPopoverBase(columnButton, pop_html, 
        alignment={ "top": "bottom", "left": "left" }
    );
    
    await ready;
    // Classes écrites en entier ; la popover de base est dans le layer components.
    pop.classList.add(
        "w-fit", "min-w-auto", "rounded-[0.6rem]", "border",
        "border-slate-300", "text-[0.85rem]",
    );
    columnButton.dataset.active = "";

    return new Promise((resolve) => {
        close.then(() => {
            delete columnButton.dataset.active;
            resolve(false);
        });
    });
}

document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".table-column-head__options").forEach(button => {
        button.addEventListener("click", event => {
            event.stopPropagation();
            event.preventDefault();

            const columnButton = button.closest(".table-column-head");

            tableColumnOptions(columnButton);
        });
    });

    document.querySelectorAll(".table-column-head").forEach(button => {
        if (button.href === undefined) {
            button.addEventListener("click", event => {
                event.stopPropagation();
                event.preventDefault();

                optionsButton = button.querySelector(".table-column-head__options");
                optionsButton.click();
            });
        }
    });
});
