async function tableColumnOptions(element) {
    var pop_html = `
    <p>Test</p>
    `
    const { pop, ready, close } = createPopoverBase(element, pop_html, 
        alignment={ "top": "bottom", "left": "left" }
    );

    await ready;

    return new Promise((resolve) => {
        close.then(() => resolve(false));
    });
}

document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".table-column-head__more").forEach(button => {
        button.addEventListener("click", event => {
            event.stopPropagation();
            event.preventDefault();

            const columnButton = button.closest("a");

            tableColumnOptions(columnButton);
        });
    });
});
