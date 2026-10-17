// Feed cards (.element-banner with a .feed-title link) are clickable as a whole:
// a click anywhere on the card that is not on a button/link/input forwards to the title link.
const CLICKABLE_CARD_IGNORE = "a, button, input, select, textarea, label, .btn, [role='button']";

function card_link_from_event(e) {
    const card = e.target.closest(".element-banner");
    if (!card) return null;

    const link = card.querySelector(".feed-title a");
    if (!link) return null;

    const interactive = e.target.closest(CLICKABLE_CARD_IGNORE);
    if (interactive && card.contains(interactive)) return null;

    // don't hijack text selection
    if (window.getSelection().toString().length > 0) return null;

    return link;
}

document.addEventListener("click", function (e) {
    if (e.button !== 0) return;
    const link = card_link_from_event(e);
    if (!link) return;

    const href = link.getAttribute("href");
    if (href && (e.ctrlKey || e.metaKey || e.shiftKey)) {
        window.open(href, "_blank");
        return;
    }
    // forwards to htmx / bootstrap modal triggers as well as plain hrefs
    link.click();
});

// middle click opens in a new tab like a regular link
document.addEventListener("auxclick", function (e) {
    if (e.button !== 1) return;
    const link = card_link_from_event(e);
    const href = link && link.getAttribute("href");
    if (!href) return;
    e.preventDefault();
    window.open(href, "_blank");
});
