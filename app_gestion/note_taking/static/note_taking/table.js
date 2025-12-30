async function tableColumnOptions(columnButton) {
    var pop_html = `
    <p>Test</p>
    `
    const { pop, ready, close } = createPopoverBase(columnButton, pop_html, 
        alignment={ "top": "bottom", "left": "left" }
    );
    
    await ready;
    pop.classList.add("table-column-options-popover");
    columnButton.classList.add("table-column-head--active-popover");

    return new Promise((resolve) => {
        close.then(() => {
            columnButton.classList.remove("table-column-head--active-popover");
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
