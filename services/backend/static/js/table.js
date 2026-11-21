// htmx tables (templates/components/tables/_table.html, server/components/tables, docs/tables.md).
//
// The server renders the whole table (toolbar form, header, rows, footer); this script only
//  - submits the toolbar form when the search, sort, page or filters change,
//  - mirrors each table's state into the address bar under its prefix (`lib.q=…&lib.page=2`) and reads it back
//    on the first load, so a refresh or a shared link shows the same view,
//  - computes the page size from the free height, keeps per-browser view settings (hidden columns, barcode
//    display, rows per page) and loads the options of entity filters.

const OTABLE_ROW_HEIGHT = 38; // fixed in table.css
const OTABLE_CHROME_HEIGHT = 190; // toolbar, header row, pager and a margin below
const OTABLE_PAGE_LIMIT_MIN = 10;
const OTABLE_PAGE_LIMIT_MAX = 50;
const OTABLE_SEARCH_DELAY = 300;

// ---------------------------------------------------------------------------------------------------------------
// Address bar state (pure functions, tested in services/backend/tests/table-url-state.test.js)
// ---------------------------------------------------------------------------------------------------------------

/** The `key.*` parameters of `search` without the prefix: ("?lib.q=a&x=1", "lib") -> {q: "a"} */
function tableStateFromSearch(search, key) {
    const params = new URLSearchParams(search);
    const prefix = key + ".";
    const state = {};
    for (const [name, value] of params) {
        if (name.startsWith(prefix) && name.length > prefix.length) {
            state[name.slice(prefix.length)] = value;
        }
    }
    return state;
}

/** `search` with the `key.*` parameters replaced by `state` (other parameters and their order kept). */
function tableSearchWithState(search, key, state) {
    const params = new URLSearchParams(search);
    const prefix = key + ".";
    for (const name of Array.from(params.keys())) {
        if (name.startsWith(prefix)) params.delete(name);
    }
    for (const [name, value] of Object.entries(state || {})) {
        if (value !== null && value !== undefined && value !== "") params.set(prefix + name, value);
    }
    const query = params.toString();
    return query ? "?" + query : "";
}

// ---------------------------------------------------------------------------------------------------------------
// Per-browser view settings
// ---------------------------------------------------------------------------------------------------------------

function tableSetting(key, name, fallback) {
    try {
        const value = window.localStorage.getItem(`otable:${key}:${name}`);
        return value === null ? fallback : JSON.parse(value);
    } catch (e) {
        return fallback;
    }
}

function setTableSetting(key, name, value) {
    try {
        window.localStorage.setItem(`otable:${key}:${name}`, JSON.stringify(value));
    } catch (e) { /* private mode or blocked storage: the setting just isn't remembered */ }
}

/**
 * Rows that fit on the first screen below the table: viewport height minus the table's position on the page
 * (not the current scroll position) and its toolbar, header and pager. The same for the first load and every
 * later page, sort or search, so the page size doesn't change while you use the table.
 */
function otableCalcPageLimit(el) {
    if (!el || typeof el.getBoundingClientRect !== "function") {
        return OTABLE_PAGE_LIMIT_MIN;
    }
    const top = el.getBoundingClientRect().top + window.scrollY;
    const available = window.innerHeight - top - OTABLE_CHROME_HEIGHT;
    const rows = Math.floor(available / OTABLE_ROW_HEIGHT);
    return Math.max(OTABLE_PAGE_LIMIT_MIN, Math.min(OTABLE_PAGE_LIMIT_MAX, rows || OTABLE_PAGE_LIMIT_MIN));
}

// The automatic page size of each table, decided on its first load and kept for every later page, sort and
// search (re-measuring could tip a row either way); a window resize decides again.
const otableAutoLimits = new Map();
window.addEventListener("resize", () => otableAutoLimits.clear());

function tablePageLimit(key, el) {
    const chosen = tableSetting(key, "limit", "auto");
    if (chosen !== "auto") return parseInt(chosen, 10) || OTABLE_PAGE_LIMIT_MIN;
    if (!otableAutoLimits.has(key)) otableAutoLimits.set(key, otableCalcPageLimit(el));
    return otableAutoLimits.get(key);
}

// ---------------------------------------------------------------------------------------------------------------
// Requests
// ---------------------------------------------------------------------------------------------------------------

document.body.addEventListener("htmx:configRequest", (evt) => {
    const elt = evt.detail.elt;
    if (!(elt instanceof Element)) return;
    const params = evt.detail.parameters;
    if (params.browse !== undefined || /[?&]browse=/.test(evt.detail.path || "")) return;

    // first load of a table: <div data-table-loader="lib" hx-get=…> (macro table_loader)
    const loaderKey = elt.dataset.tableLoader;
    if (loaderKey !== undefined) {
        if (elt.dataset.syncUrl !== "false") {
            Object.assign(params, tableStateFromSearch(window.location.search, loaderKey));
        }
        params.limit = tablePageLimit(loaderKey, elt);
        return;
    }

    // requests of a table's own form
    if (elt.classList.contains("otable-form")) {
        const container = elt.closest(".otable");
        params.limit = tablePageLimit(container.dataset.tableKey, container);
    }
});

function submitTable(container, changes = {}) {
    const form = container.querySelector(".otable-form");
    if (!form) return;
    for (const [name, value] of Object.entries(changes)) {
        const input = form.querySelector(`input[type=hidden][name="${name}"]`);
        if (input) input.value = value;
    }
    htmx.trigger(form, "submit");
}

// re-render a table with its current state, e.g. after a row action
function refreshTable(container) {
    if (container) submitTable(container);
}

// After a successful request started from a table row (a ⋯ menu action, a button in a cell), re-render the
// table so rows, counts and pages stay right.
document.body.addEventListener("htmx:afterRequest", (evt) => {
    const elt = evt.detail.elt;
    if (!evt.detail.successful || !(elt instanceof Element)) return;
    if (elt.classList.contains("otable-form") || elt.dataset.tableLoader !== undefined) return;
    // only actions on rows (⋯ menu, buttons in cells) change the rows; toolbar buttons open modals
    if (!elt.closest("tbody")) return;
    const container = elt.closest(".otable");
    if (container && document.body.contains(container)) refreshTable(container);
});

// ---------------------------------------------------------------------------------------------------------------
// After every render
// ---------------------------------------------------------------------------------------------------------------

function applyTableView(container) {
    const key = container.dataset.tableKey;
    const variant = container.dataset.variant || "default";

    // hidden columns (per table and variant)
    const hidden = tableSetting(key, `hidden:${variant}`, []);
    const headerCells = Array.from(container.querySelectorAll("thead th"));
    const indexes = [];
    headerCells.forEach((th, i) => {
        if (hidden.includes(th.dataset.col)) indexes.push(i + 1);
    });
    let style = container.querySelector("style.otable-hidden-cols");
    if (!style) {
        style = document.createElement("style");
        style.className = "otable-hidden-cols";
        container.prepend(style);
    }
    const id = CSS.escape(container.id);
    style.textContent = indexes.map(n =>
        `#${id} > form table > * > tr > :nth-child(${n}), #${id} > form table > colgroup > col:nth-child(${n}) { display: none; }`
    ).join("\n");
    container.querySelectorAll(".otable-col-toggle").forEach(box => {
        box.checked = !hidden.includes(box.dataset.col);
    });

    applyColumnWidths(container);
    highlightSearch(container);

    // barcode display
    const mode = tableSetting(key, "index-mode", "name");
    container.dataset.indexMode = mode;
    container.querySelectorAll(".otable-index-switch button").forEach(button => {
        button.setAttribute("aria-pressed", button.dataset.indexMode === mode ? "true" : "false");
    });

    // rows per page
    const limit = container.querySelector(".otable-limit");
    if (limit) limit.value = String(tableSetting(key, "limit", "auto"));

    // address bar
    if (container.dataset.syncUrl === "true") {
        let state = {};
        try { state = JSON.parse(container.dataset.urlState || "{}"); } catch (e) { state = {}; }
        const search = tableSearchWithState(window.location.search, key, state);
        if (search !== window.location.search) {
            history.replaceState(history.state, "", window.location.pathname + search + window.location.hash);
        }
    }
}

function applyTableViews(target) {
    if (!(target instanceof Element) || !document.body.contains(target)) return;
    const containers = target.matches(".otable") ? [target] : Array.from(target.querySelectorAll(".otable"));
    containers.forEach(applyTableView);
}

// new content (an outerHTML swap of a table or of its loader) and settled swaps
document.body.addEventListener("htmx:load", (evt) => applyTableViews(evt.detail.elt));
document.body.addEventListener("htmx:afterSettle", (evt) => applyTableViews(evt.detail.elt));

document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".otable").forEach(applyTableView);
});

// ---------------------------------------------------------------------------------------------------------------
// Toolbar, header and footer
// ---------------------------------------------------------------------------------------------------------------

const tableSearchTimers = new WeakMap();

document.addEventListener("input", (e) => {
    const input = e.target;
    if (!input.classList || !input.classList.contains("otable-q")) return;
    const container = input.closest(".otable");
    clearTimeout(tableSearchTimers.get(container));
    tableSearchTimers.set(container, setTimeout(() => submitTable(container, { page: 1 }), OTABLE_SEARCH_DELAY));
});

document.addEventListener("keydown", (e) => {
    const input = e.target;
    if (input.classList && input.classList.contains("otable-q") && e.key === "Enter") {
        e.preventDefault();
        const container = input.closest(".otable");
        clearTimeout(tableSearchTimers.get(container));
        submitTable(container, { page: 1 });
        return;
    }
    if (input.classList && input.classList.contains("otable-q") && e.key === "Escape" && input.value) {
        input.value = "";
        submitTable(input.closest(".otable"), { page: 1 });
        return;
    }
});

document.addEventListener("change", (e) => {
    const el = e.target;
    if (!el.closest) return;
    const container = el.closest(".otable");
    if (!container) return;

    if (el.classList.contains("otable-scope")) {
        const q = container.querySelector(".otable-q");
        if (q && q.value.trim()) submitTable(container, { page: 1 });
    } else if (el.classList.contains("otable-limit")) {
        setTableSetting(container.dataset.tableKey, "limit", el.value);
        submitTable(container, { page: 1 });
    } else if (el.classList.contains("otable-col-toggle")) {
        const key = container.dataset.tableKey;
        const name = `hidden:${container.dataset.variant || "default"}`;
        const hidden = tableSetting(key, name, []).filter(col => col !== el.dataset.col);
        if (!el.checked) hidden.push(el.dataset.col);
        setTableSetting(key, name, hidden);
        applyTableView(container);
    } else if (el.closest(".otable-filter-panel") && el.type === "checkbox") {
        container.dataset.filtersChanged = "true";
    }
});

// ---------------------------------------------------------------------------------------------------------------
// Highlight the search terms in the visible cells (like the navbar search)
// ---------------------------------------------------------------------------------------------------------------

/** Words of the search box as typed: ``owner:chen "liver org" #12`` -> ["chen", "liver org", "12"]. */
function searchTerms(q) {
    const terms = [];
    const pattern = /(?:[A-Za-z_]\w*:)?(?:"([^"]*)"?|(\S+))/g;
    let match;
    while ((match = pattern.exec(q || "")) !== null) {
        let term = (match[1] !== undefined ? match[1] : match[2] || "").trim();
        if (term.startsWith("#")) term = term.slice(1);
        if (term.length >= 2 || /^\d+$/.test(term)) terms.push(term);
    }
    return terms;
}

function highlightSearch(container) {
    let state = {};
    try { state = JSON.parse(container.dataset.urlState || "{}"); } catch (e) { return; }
    const terms = searchTerms(state.q);
    const tbody = container.querySelector("tbody");
    if (!terms.length || !tbody || tbody.querySelector("mark.otable-mark")) return;
    const escaped = terms
        .sort((a, b) => b.length - a.length)
        .map(t => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    const regex = new RegExp(`(${escaped.join("|")})`, "gi");
    const walker = document.createTreeWalker(tbody, NodeFilter.SHOW_TEXT, {
        acceptNode: (node) => (
            node.nodeValue.trim() && !node.parentElement.closest("button, script, style, .otable-empty, mark")
                ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT
        ),
    });
    const nodes = [];
    while (walker.nextNode()) nodes.push(walker.currentNode);
    for (const node of nodes) {
        const text = node.nodeValue;
        regex.lastIndex = 0;
        if (!regex.test(text)) continue;
        const fragment = document.createDocumentFragment();
        let last = 0;
        text.replace(regex, (found, _group, offset) => {
            if (offset > last) fragment.append(text.slice(last, offset));
            const mark = document.createElement("mark");
            mark.className = "otable-mark";
            mark.textContent = found;
            fragment.append(mark);
            last = offset + found.length;
            return found;
        });
        if (last < text.length) fragment.append(text.slice(last));
        node.replaceWith(fragment);
    }
}

if (typeof module !== "undefined") {
    module.exports = Object.assign(module.exports || {}, { searchTerms });
}

// ---------------------------------------------------------------------------------------------------------------
// Resizable columns: drag the right edge of a header cell (or focus it and use the arrow keys). Widths are kept
// per table and variant in this browser; double-click a handle or "Reset column widths" to go back to automatic.
// ---------------------------------------------------------------------------------------------------------------

const OTABLE_MIN_COL_WIDTH = 48;

function columnWidthsName(container) {
    return `widths:${container.dataset.variant || "default"}`;
}

function applyColumnWidths(container) {
    const table = container.querySelector("table.otable-table");
    if (!table) return;
    const cols = Array.from(table.querySelectorAll("colgroup col[data-col]"));
    const saved = tableSetting(container.dataset.tableKey, columnWidthsName(container), null);
    if (table.dataset.minWidth === undefined) table.dataset.minWidth = table.style.minWidth;
    if (!saved) {
        cols.forEach(col => { col.style.width = col.dataset.width; });
        table.style.width = "";
        table.style.minWidth = table.dataset.minWidth;
        return;
    }
    table.style.minWidth = "100%";
    let total = 0;
    for (const col of cols) {
        const width = Math.max(OTABLE_MIN_COL_WIDTH, saved[col.dataset.col] || 120);
        col.style.width = `${width}px`;
        if (getComputedStyle(col).display !== "none") total += width;
    }
    const actions = table.querySelector("colgroup col.otable-actions-col");
    if (actions) total += actions.getBoundingClientRect().width || 48;
    // at least the card's width: wider tables scroll sideways, narrower ones grow proportionally
    table.style.width = `${total}px`;
}

function startColumnResize(handle, clientX) {
    const th = handle.closest("th");
    const container = th.closest(".otable");
    const table = container.querySelector("table.otable-table");
    const cols = Array.from(table.querySelectorAll("colgroup col[data-col]"));
    const headers = Array.from(table.querySelectorAll("thead th[data-col]"));
    // freeze every column at its current width, then move only the dragged one
    const widths = {};
    headers.forEach(h => { widths[h.dataset.col] = Math.round(h.getBoundingClientRect().width); });
    const key = th.dataset.col;
    return { container, table, cols, widths, key, startX: clientX, startWidth: widths[key] };
}

function resizeColumn(state, width) {
    state.widths[state.key] = Math.max(OTABLE_MIN_COL_WIDTH, Math.round(width));
    setTableSetting(state.container.dataset.tableKey, columnWidthsName(state.container), state.widths);
    applyColumnWidths(state.container);
}

document.addEventListener("pointerdown", (e) => {
    const handle = e.target.closest && e.target.closest(".otable-resize");
    if (!handle || e.button !== 0) return;
    e.preventDefault();
    e.stopPropagation();
    const state = startColumnResize(handle, e.clientX);
    handle.classList.add("dragging");
    handle.setPointerCapture(e.pointerId);
    document.body.style.cursor = "col-resize";
    const move = (ev) => resizeColumn(state, state.startWidth + ev.clientX - state.startX);
    const up = () => {
        handle.classList.remove("dragging");
        document.body.style.cursor = "";
        handle.removeEventListener("pointermove", move);
        handle.removeEventListener("pointerup", up);
        handle.removeEventListener("pointercancel", up);
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", up);
    handle.addEventListener("pointercancel", up);
});

// a click on the handle must not sort the column
document.addEventListener("click", (e) => {
    if (e.target.closest && e.target.closest(".otable-resize")) e.stopPropagation();
}, true);

document.addEventListener("dblclick", (e) => {
    const handle = e.target.closest && e.target.closest(".otable-resize");
    if (!handle) return;
    resetColumnWidths(handle.closest(".otable"));
});

document.addEventListener("keydown", (e) => {
    const handle = e.target.closest && e.target.closest(".otable-resize");
    if (!handle || (e.key !== "ArrowLeft" && e.key !== "ArrowRight")) return;
    e.preventDefault();
    const state = startColumnResize(handle, 0);
    resizeColumn(state, state.startWidth + (e.key === "ArrowRight" ? 16 : -16));
});

function resetColumnWidths(container) {
    try {
        window.localStorage.removeItem(`otable:${container.dataset.tableKey}:${columnWidthsName(container)}`);
    } catch (err) { /* storage blocked: nothing was saved */ }
    applyColumnWidths(container);
}

// truncated cells show their full text on hover
document.addEventListener("mouseover", (e) => {
    const cell = e.target.closest && e.target.closest(".otable tbody td, .otable tbody td > a");
    if (!cell || cell.title) return;
    if (cell.scrollWidth > cell.clientWidth + 1) cell.title = cell.innerText.trim();
});

function clearFilterInputs(container, field) {
    const selector = field ? `.otable-filter-panel input[name="${field}_in"]` : ".otable-filter-panel input[type=checkbox]";
    container.querySelectorAll(selector).forEach(box => { box.checked = false; });
}

document.addEventListener("click", (e) => {
    const el = e.target.closest && e.target.closest("button");
    if (!el) return;
    const container = el.closest(".otable");
    if (!container) return;

    if (el.classList.contains("otable-sort")) {
        submitTable(container, { order_by: el.dataset.orderBy, page: 1 });
    } else if (el.classList.contains("otable-page")) {
        if (!el.disabled) submitTable(container, { page: el.dataset.page });
    } else if (el.classList.contains("otable-chip-x")) {
        clearFilterInputs(container, el.dataset.clearFilter);
        submitTable(container, { page: 1 });
    } else if (el.classList.contains("otable-clear-all")) {
        const q = container.querySelector(".otable-q");
        if (q) q.value = "";
        const scope = container.querySelector(".otable-scope");
        if (scope) scope.value = "";
        clearFilterInputs(container);
        submitTable(container, { page: 1 });
    } else if (el.classList.contains("otable-filter-field")) {
        showFilterPane(container, el.dataset.field);
    } else if (el.classList.contains("otable-funnel")) {
        e.stopPropagation();
        const toggle = container.querySelector(".otable-filter-toggle");
        showFilterPane(container, el.dataset.filterField);
        if (toggle) bootstrap.Dropdown.getOrCreateInstance(toggle).show();
    } else if (el.classList.contains("otable-clear-field")) {
        clearFilterInputs(container, el.dataset.field);
        container.dataset.filtersChanged = "true";
    } else if (el.classList.contains("otable-apply")) {
        const toggle = container.querySelector(".otable-filter-toggle");
        container.dataset.filtersChanged = "true";
        if (toggle) bootstrap.Dropdown.getOrCreateInstance(toggle).hide();
        else submitTable(container, { page: 1 });
    } else if (el.classList.contains("otable-reset-widths")) {
        resetColumnWidths(container);
    } else if (el.matches(".otable-index-switch button")) {
        setTableSetting(container.dataset.tableKey, "index-mode", el.dataset.indexMode);
        applyTableView(container);
    }
});

// filters apply when the filter panel closes
document.addEventListener("hide.bs.dropdown", (e) => {
    const toggle = e.target;
    if (!toggle.classList || !toggle.classList.contains("otable-filter-toggle")) return;
    const container = toggle.closest(".otable");
    if (container && container.dataset.filtersChanged === "true") {
        container.dataset.filtersChanged = "false";
        submitTable(container, { page: 1 });
    }
});

document.addEventListener("shown.bs.dropdown", (e) => {
    const toggle = e.target;
    if (!toggle.classList || !toggle.classList.contains("otable-filter-toggle")) return;
    const pane = toggle.closest(".otable").querySelector(".otable-filter-pane.active");
    if (pane) activateFilterPane(pane);
});

function showFilterPane(container, field) {
    container.querySelectorAll(".otable-filter-field").forEach(b => b.classList.toggle("active", b.dataset.field === field));
    let active = null;
    container.querySelectorAll(".otable-filter-pane").forEach(p => {
        const on = p.dataset.pane === field;
        p.classList.toggle("active", on);
        if (on) active = p;
    });
    if (active) activateFilterPane(active);
}

function activateFilterPane(pane) {
    const search = pane.querySelector(".otable-entity-search");
    if (search) {
        if (!pane.dataset.loaded) loadEntityOptions(pane, true);
        setTimeout(() => search.focus(), 0);
    }
}

// ---------------------------------------------------------------------------------------------------------------
// Entity filters: type-ahead list of the related objects that occur in the visible rows
// ---------------------------------------------------------------------------------------------------------------

const entitySearchTimers = new WeakMap();

document.addEventListener("input", (e) => {
    const input = e.target;
    if (!input.classList || !input.classList.contains("otable-entity-search")) return;
    const pane = input.closest(".otable-filter-pane");
    clearTimeout(entitySearchTimers.get(pane));
    entitySearchTimers.set(pane, setTimeout(() => loadEntityOptions(pane, true), OTABLE_SEARCH_DELAY));
});

// Enter in the option search must not submit the table form
document.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && e.target.classList && e.target.classList.contains("otable-entity-search")) {
        e.preventDefault();
    }
});

// Infinite scrolling: when the sentinel after the options scrolls into view, the next page is loaded.
function observeEntityOptions(pane) {
    if (pane._optionsObserver || typeof IntersectionObserver === "undefined") return;
    const sentinel = pane.querySelector(".otable-entity-sentinel");
    pane._optionsObserver = new IntersectionObserver((entries) => {
        if (entries.some(entry => entry.isIntersecting) && pane.dataset.hasMore === "true" && pane.dataset.loading !== "true") {
            loadEntityOptions(pane, false);
        }
    }, { root: pane.querySelector(".otable-options"), rootMargin: "0px 0px 120px 0px" });
    pane._optionsObserver.observe(sentinel);
}

async function loadEntityOptions(pane, reset) {
    const input = pane.querySelector(".otable-entity-search");
    const results = pane.querySelector(".otable-entity-results");
    const status = pane.querySelector(".otable-option-status");
    const field = input.dataset.field;
    observeEntityOptions(pane);
    const page = reset ? 1 : (parseInt(pane.dataset.optionsPage || "1", 10) + 1);
    const url = new URL(input.dataset.optionsUrl, window.location.origin);
    if (input.value.trim()) url.searchParams.set("word", input.value.trim());
    url.searchParams.set("options_page", page);

    const requestId = (parseInt(pane.dataset.requestId || "0", 10) + 1).toString();
    pane.dataset.requestId = requestId;
    pane.dataset.loading = "true";
    status.textContent = "Loading…";
    status.hidden = false;
    let data;
    try {
        const response = await fetch(url, { headers: { "HX-Request": "true" }, credentials: "same-origin" });
        if (!response.ok) throw new Error(response.statusText);
        data = await response.json();
    } catch (err) {
        if (pane.dataset.requestId === requestId) {
            pane.dataset.loading = "false";
            status.textContent = "Could not load options.";
        }
        return;
    }
    if (pane.dataset.requestId !== requestId) return; // a newer search is on its way
    pane.dataset.loading = "false";
    status.hidden = true;

    pane.dataset.loaded = "true";
    pane.dataset.optionsPage = String(page);
    if (reset) results.replaceChildren();

    const selected = new Set(Array.from(pane.querySelectorAll(`input[name="${field}_in"]`)).map(box => box.value));
    for (const option of data.options) {
        if (selected.has(String(option.id))) continue;
        const label = document.createElement("label");
        label.className = "otable-option";
        const box = document.createElement("input");
        box.type = "checkbox";
        box.name = `${field}_in`;
        box.value = String(option.id);
        const text = document.createElement("span");
        text.textContent = option.name;
        label.append(box, text);
        if (option.description) {
            const detail = document.createElement("small");
            detail.className = "otable-option-detail";
            detail.textContent = option.description;
            label.append(detail);
        }
        results.append(label);
    }
    if (reset && !data.options.length) {
        const empty = document.createElement("div");
        empty.className = "otable-option-empty";
        empty.textContent = "No matches";
        results.append(empty);
    }
    pane.dataset.hasMore = data.has_more ? "true" : "false";
    // a short first page may not fill the list: keep loading until it scrolls or nothing is left
    const list = pane.querySelector(".otable-options");
    if (data.has_more && list.offsetParent !== null && list.scrollHeight <= list.clientHeight + 120) {
        loadEntityOptions(pane, false);
    }
}

// ---------------------------------------------------------------------------------------------------------------
// Barcodes outside of tables (checklists, workflow summaries): page-wide toggle
// ---------------------------------------------------------------------------------------------------------------

function toggle_index_display() {
    $(".index-badge").each(function() {
        $(this).toggle();
    });
}

if (typeof module !== "undefined") {
    module.exports = Object.assign(module.exports || {}, { tableStateFromSearch, tableSearchWithState });
}
