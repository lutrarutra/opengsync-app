// Navbar search (insiders only): htmx fetches results, this handles open/close and the keyboard.
(function () {
    const root = document.getElementById("global-search");
    if (!root) return;

    const input = root.querySelector(".gs-input");
    const select = root.querySelector(".gs-kind");
    const results = root.querySelector(".gs-results");
    let active = -1;

    function items() {
        return Array.from(results.querySelectorAll(".gs-result"));
    }

    function setActive(index) {
        const list = items();
        list.forEach((el, i) => el.classList.toggle("active", i === index));
        active = index;
        if (index >= 0 && list[index]) list[index].scrollIntoView({ block: "nearest" });
    }

    function open() {
        root.classList.add("open");
    }

    function close() {
        root.classList.remove("open");
        setActive(-1);
    }

    function follow(link, newTab) {
        if (newTab) window.open(link.href, "_blank");
        else window.location.href = link.href;
    }

    input.addEventListener("focus", open);
    select.addEventListener("focus", open);

    // the collapsed bar is mostly icon on small screens: clicking anywhere on it focuses the input
    root.querySelector(".gs-form").addEventListener("mousedown", (e) => {
        if (e.target.closest(".gs-input, .gs-kind, .gs-results")) return;
        e.preventDefault();
        input.focus();
    });

    // close on clicks outside; focusout is unreliable because Safari does not focus links on click
    document.addEventListener("mousedown", (e) => {
        if (!root.contains(e.target)) close();
    });

    results.addEventListener("htmx:afterSwap", () => {
        setActive(-1);
        // a slow response must not reopen a search the user already left
        if (root.contains(document.activeElement)) open();
    });

    results.addEventListener("mousemove", (e) => {
        const item = e.target.closest(".gs-result");
        if (item) setActive(items().indexOf(item));
    });

    results.addEventListener("click", (e) => {
        const more = e.target.closest("[data-gs-kind]");
        if (!more) return;
        e.preventDefault();
        select.value = more.dataset.gsKind;
        select.dispatchEvent(new Event("change", { bubbles: true }));
        input.focus();
    });

    input.addEventListener("keydown", (e) => {
        const list = items();
        if (e.key === "ArrowDown" && list.length) {
            e.preventDefault();
            setActive((active + 1) % list.length);
        } else if (e.key === "ArrowUp" && list.length) {
            e.preventDefault();
            setActive(active <= 0 ? list.length - 1 : active - 1);
        } else if (e.key === "Enter") {
            e.preventDefault();
            const target = list[active >= 0 ? active : 0];
            if (target) follow(target, e.metaKey || e.ctrlKey);
        } else if (e.key === "Escape") {
            // keep the query: browsers clear type="search" inputs on Escape
            e.preventDefault();
            close();
            input.blur();
        }
    });

    // "/" or Ctrl/Cmd+K focuses the search from anywhere on the page
    document.addEventListener("keydown", (e) => {
        const typing = e.target instanceof Element && e.target.closest("input, textarea, select, [contenteditable]");
        const shortcut = (e.key === "k" && (e.metaKey || e.ctrlKey)) || (e.key === "/" && !typing && !e.metaKey && !e.ctrlKey);
        if (!shortcut) return;
        e.preventDefault();
        input.focus();
        input.select();
    });
})();
