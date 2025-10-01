function init_tooltips(container = document) {
    const tooltipTriggerList = container.querySelectorAll('[data-bs-toggle="tooltip"]:not([data-bs-tooltip-initialized])');
    tooltipTriggerList.forEach(tooltipTriggerEl => {
        new bootstrap.Tooltip(tooltipTriggerEl, { html: true });
        tooltipTriggerEl.setAttribute('data-bs-tooltip-initialized', 'true');
    });
}

document.addEventListener('DOMContentLoaded', () => init_tooltips());

document.addEventListener('htmx:afterSwap', (event) => {
    init_tooltips(event.detail.elt);
});