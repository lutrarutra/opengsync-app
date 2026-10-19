// Thin top-of-page progress bar: trickles towards ~90% while waiting, completes on load.
// Driven by full page navigations (link clicks, form submits) and htmx requests.
// Only shown if loading takes longer than SHOW_DELAY_MS, so quick loads don't flicker.
(function () {
    const STORAGE_KEY = "page-loader-progress";
    const SHOW_DELAY_MS = 150;
    const TRICKLE_MS = 12000;  // time to creep from 0 to 90%
    const TRICKLE_EASING = "cubic-bezier(0.1, 0.65, 0.25, 1)";  // fast start, long slow tail

    const root = document.getElementById("page-loader");
    if (!root) return;
    const bar = root.querySelector(".page-loader-bar");

    let visible = false;
    let showTimer = null;
    let hideTimer = null;
    let pendingHtmx = 0;

    // Current (possibly mid-transition) scale of the bar
    function currentProgress() {
        const m = getComputedStyle(bar).transform.match(/^matrix\(([^,]+)/);
        return m ? parseFloat(m[1]) : 0;
    }

    function setBar(value, transition) {
        bar.style.transition = transition;
        bar.style.transform = `scaleX(${value})`;
    }

    function show(from) {
        showTimer = null;
        clearTimeout(hideTimer);
        visible = true;
        root.classList.add("active");
        // Jump to the start value, then let a single long CSS transition carry it to 90%
        setBar(Math.max(currentProgress(), from), "none");
        bar.offsetWidth;  // force reflow so the jump isn't animated
        const remaining = Math.max(0.1, (0.9 - from) / 0.9);
        setBar(0.9, `transform ${Math.round(TRICKLE_MS * remaining)}ms ${TRICKLE_EASING}`);
    }

    function start(from = 0.08, delay = SHOW_DELAY_MS) {
        if (visible || showTimer) return;
        if (delay <= 0) show(from);
        else showTimer = setTimeout(function () { show(from); }, delay);
    }

    function done() {
        if (showTimer) {
            // Finished before the bar was ever shown
            clearTimeout(showTimer);
            showTimer = null;
            return;
        }
        if (!visible) return;
        visible = false;
        // A new transition starts from the current animated value, so this continues smoothly
        setBar(1, "transform 200ms ease-out");
        hideTimer = setTimeout(function () {
            root.classList.remove("active");
            hideTimer = setTimeout(function () { setBar(0, "none"); }, 300);
        }, 200);
    }

    // --- Initial page load: continue the bar if the previous page was already showing it ---
    let resumed = null;
    try {
        const saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "null");
        sessionStorage.removeItem(STORAGE_KEY);
        if (saved && Date.now() - saved.t < 10000) resumed = Math.min(saved.p, 0.9);
    } catch (e) { /* storage unavailable */ }

    if (document.readyState !== "complete") {
        if (resumed !== null) start(resumed, 0);
        else start();
        window.addEventListener("load", done, { once: true });
    }

    // --- Full page navigations ---
    function isNavigatingLink(a, event) {
        if (!a || !a.href) return false;
        if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return false;
        if (a.target && a.target !== "_self") return false;
        if (a.hasAttribute("download")) return false;
        if (a.hasAttribute("data-bs-toggle") || a.hasAttribute("hx-get") || a.hasAttribute("hx-post")) return false;
        const url = new URL(a.href, location.href);
        if (!/^https?:$/.test(url.protocol)) return false;
        if (url.origin !== location.origin) return false;
        if (url.pathname === location.pathname && url.search === location.search && url.hash) return false;
        return true;
    }

    document.addEventListener("click", function (event) {
        const a = event.target.closest("a");
        // Check after other handlers ran so preventDefault() is respected
        setTimeout(function () {
            if (!event.defaultPrevented && isNavigatingLink(a, event)) start();
        }, 0);
    });

    document.addEventListener("submit", function (event) {
        const form = event.target;
        setTimeout(function () {
            if (event.defaultPrevented) return;
            if (form.hasAttribute("hx-post") || form.hasAttribute("hx-get") || form.hasAttribute("hx-put")) return;
            if (form.target && form.target !== "_self") return;
            start();
        }, 0);
    });

    // Refreshes and address-bar navigations don't fire click/submit
    window.addEventListener("beforeunload", function (event) {
        // Deferred so a "leave page?" prompt from another handler is respected (no bar if the user stays)
        setTimeout(function () {
            if (!event.defaultPrevented && !event.returnValue) start();
        }, 0);
    });

    window.addEventListener("pagehide", function () {
        if (!visible) return;
        try {
            sessionStorage.setItem(STORAGE_KEY, JSON.stringify({ p: currentProgress(), t: Date.now() }));
        } catch (e) { /* storage unavailable */ }
    });

    // Back/forward cache restore: the page is already loaded
    window.addEventListener("pageshow", function (event) {
        if (event.persisted) done();
    });

    // --- htmx requests ---
    document.addEventListener("htmx:beforeRequest", function () {
        pendingHtmx++;
        start();
    });

    document.addEventListener("htmx:afterRequest", function () {
        pendingHtmx = Math.max(0, pendingHtmx - 1);
        if (pendingHtmx === 0) done();
    });

    window.PageLoader = { start: start, done: done };
})();
