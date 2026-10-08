function open_tab(id) {
    const tab = new bootstrap.Tab(document.querySelector(`button[data-bs-target="#${id}"]`));
    tab.show();
}

document.addEventListener("DOMContentLoaded", function () {
    var hash = window.location.hash;
    if (!hash) {
        const params = new URLSearchParams(window.location.search);
        hash = "#" + params.get("tab");
    }
    if (hash) {
        const trigger = document.querySelector(`button[data-bs-target="${hash}"]`);
        if (trigger) {
            const tab = new bootstrap.Tab(trigger);
            tab.show();
        }
    }
});

function update_tab_overflow(tabs) {
    // compare against the wrapper's width: the list itself shrinks while the arrows are shown
    tabs.classList.toggle("overflowing", tabs.scrollWidth > tabs.parentElement.clientWidth + 1);
    const max_scroll = tabs.scrollWidth - tabs.clientWidth;
    tabs.classList.toggle("overflow-left", tabs.scrollLeft > 1);
    tabs.classList.toggle("overflow-right", tabs.scrollLeft < max_scroll - 1);
}

function add_tab_scroll_arrows(tabs) {
    // re-swapped list inside an existing scroller: reuse its arrows (they look up the list on click)
    if (tabs.parentElement.classList.contains("nav-tabs-scroller")) return;

    const scroller = document.createElement("div");
    scroller.className = "nav-tabs-scroller";
    tabs.parentNode.insertBefore(scroller, tabs);
    scroller.appendChild(tabs);

    [["left", -1], ["right", 1]].forEach(([side, direction]) => {
        const arrow = document.createElement("button");
        arrow.type = "button";
        arrow.className = `nav-tabs-arrow nav-tabs-arrow-${side}`;
        arrow.tabIndex = -1;
        arrow.setAttribute("aria-label", `Scroll tabs ${side}`);
        arrow.innerHTML = `<i class="bi bi-chevron-${side}"></i>`;
        arrow.addEventListener("click", () => {
            const list = scroller.querySelector(":scope > .nav-tabs");
            // jump all the way to the respective end so a single click reveals the remaining tabs
            list.scrollTo({ left: direction > 0 ? list.scrollWidth : 0, behavior: "smooth" });
        });
        scroller.appendChild(arrow);
    });
}

// fades the edges of .nav-tabs that hide tabs and shows scroll arrows (see modal.css); runs for initial page and htmx-swapped content
htmx.onLoad(function (root) {
    const tab_lists = Array.from(root.querySelectorAll(".nav-tabs"));
    if (root.matches(".nav-tabs")) tab_lists.push(root);

    tab_lists.forEach(tabs => {
        if (tabs.dataset.overflowInit) return;
        tabs.dataset.overflowInit = "true";
        add_tab_scroll_arrows(tabs);

        const update = () => update_tab_overflow(tabs);
        tabs.addEventListener("scroll", update, { passive: true });

        // observe children too: tab labels (e.g. counts) can change width without resizing the list itself
        const observer = new ResizeObserver(update);
        observer.observe(tabs);
        Array.from(tabs.children).forEach(child => observer.observe(child));
        update();
    });
});

document.querySelectorAll('.page-tabs button[data-bs-toggle="tab"]').forEach(button => {
    button.addEventListener('shown.bs.tab', function (event) {
        const hash = event.target.getAttribute('data-bs-target');
        if (hash) {
            history.replaceState(null, null, hash);
        }
    });
});
