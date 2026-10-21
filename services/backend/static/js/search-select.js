/**
 * Select input whose options are searched on the backend (SearchableInputField in components/inputs/searchable.py,
 * templates/components/inputs/search-select.html).
 *
 * Elements with `data-search-select` are set up on page load and whenever htmx loads new content. The element has
 * `data-url`, the search route, which is requested with `word` and `page` and returns
 * `{options: [{id, name, header?, description?, data?}], has_more}`; further pages load when the list is scrolled to
 * its end. Ids without a name are looked up once with `selected_id`. The element's `searchSelect` is this instance,
 * `selectedOption()` resolves to the selected option (with its `data`, e.g. a user's email) or null.
 *
 * The selection is kept in two hidden inputs: `.search-select-value` (the id, submitted as the field's name) and
 * `.search-select-text` (its name, submitted as `<name>-text`). With `data-allow-new` the list also offers to create
 * the typed text (`data-new-label`), which sets the value to `new` and the text to the new name.
 *
 * Changes dispatch `change` on the value input and `search-select:change` with `{id, isNew, text, option}` on the
 * element.
 * Elements with `data-search-select-new-only="<value input id>"` are shown only while the field holds a new name, and
 * their inputs are disabled (not submitted) otherwise.
 *
 * With `data-key-values` (ColumnValueInputField, components/inputs/column_value.py) option ids are string keys
 * instead of numbers and are not shown. `data-query-fields` (JSON `{param: field id}`) adds the shown value of other
 * fields to the search, e.g. the institute of a department.
 */
window.SearchSelect = (() => {
    const NEW = "new";
    const SEARCH_DELAY = 200;
    const LIST_MAX_HEIGHT = 280;

    const normalize = (text) => String(text ?? "").trim().toLowerCase();

    // The text with the first occurrence of the word marked
    const highlighted = (text, word) => {
        const fragment = document.createDocumentFragment();
        const i = word ? text.toLowerCase().indexOf(word.toLowerCase()) : -1;
        if (i < 0) {
            fragment.append(text);
            return fragment;
        }
        const mark = document.createElement("mark");
        mark.textContent = text.slice(i, i + word.length);
        fragment.append(text.slice(0, i), mark, text.slice(i + word.length));
        return fragment;
    };

    const span = (className, content) => {
        const element = document.createElement("span");
        element.className = className;
        element.append(content);
        return element;
    };

    class SearchSelect {
        constructor(root) {
            this.root = root;
            this.url = root.dataset.url;
            this.allowNew = root.hasAttribute("data-allow-new");
            this.newLabel = root.dataset.newLabel || "Create New";
            this.keyValues = root.hasAttribute("data-key-values");
            this.queryFields = root.dataset.queryFields ? JSON.parse(root.dataset.queryFields) : {};
            this.queryFieldsKey = null;
            this.readOnly = root.classList.contains("read-only");
            this.control = root.querySelector(".search-select-control");
            this.input = root.querySelector(".search-select-input");
            this.badge = root.querySelector(".search-select-badge");
            this.clearButton = root.querySelector(".search-select-clear");
            this.list = root.querySelector(".search-select-list");
            this.valueInput = root.querySelector(".search-select-value");
            this.textInput = root.querySelector(".search-select-text");

            // Pages already loaded per search word, so typing back and reopening is instant
            this.cache = new Map();
            this.state = null;
            this.option = null;
            this.lookup = null;
            this.typed = false;
            this.moved = false;
            this.pickWhenLoaded = false;

            root.searchSelect = this;
            if (!this.readOnly) {
                this._bind();
            }
            if (this.value && !this.isNew && !this.textInput.value) {
                this._lookUpName();
            }
            this._toggleDependents();
        }

        get value() {
            return this.valueInput.value;
        }

        get isNew() {
            return this.value === NEW;
        }

        get isOpen() {
            return !this.list.hidden;
        }

        /** Sets the value (an id, "new" or empty) and the name shown; `option` is the selected option if known. */
        setValue(value, text, { silent = false, option = null } = {}) {
            this.valueInput.value = value ?? "";
            this.textInput.value = value ? text ?? "" : "";
            this.option = option;
            this._showSelection();
            this._toggleDependents();
            if (silent) {
                return;
            }
            this.valueInput.dispatchEvent(new Event("change", { bubbles: true }));
            this.root.dispatchEvent(new CustomEvent("search-select:change", {
                bubbles: true,
                detail: {
                    id: this.value && !this.isNew ? (this.keyValues ? this.value : Number(this.value)) : null,
                    isNew: this.isNew,
                    text: this.textInput.value,
                    option: this.option,
                },
            }));
        }

        clear() {
            this.setValue("", "");
        }

        /** The selected option, looked up once if the page was rendered with the selection; null for new names. */
        async selectedOption() {
            const id = this.value;
            if (!id || this.isNew) {
                return null;
            }
            if (this.option && String(this.option.id) === id) {
                return this.option;
            }
            if (this.lookup?.id !== id) {
                const promise = this._fetch({ selected_id: id, word: "", page: 0 })
                    .then((result) => result.options.find((option) => String(option.id) === id) ?? null);
                this.lookup = { id, promise };
                promise.catch(() => {
                    if (this.lookup?.promise === promise) {
                        this.lookup = null;
                    }
                });
            }
            const option = await this.lookup.promise;
            if (this.value !== id) {
                return null;
            }
            if (option) {
                this.option = option;
                if (!this.textInput.value) {
                    this.textInput.value = option.name;
                    this._showSelection();
                }
            }
            return option;
        }

        open() {
            if (this.isOpen) {
                return;
            }
            this.list.hidden = false;
            this.input.setAttribute("aria-expanded", "true");
            this.root.classList.add("open");
            this._search(this.typed ? this.input.value.trim() : "");
        }

        close() {
            clearTimeout(this.timer);
            this.state?.controller?.abort();
            this.list.hidden = true;
            this.input.setAttribute("aria-expanded", "false");
            this.input.removeAttribute("aria-activedescendant");
            this.root.classList.remove("open", "up");
            this.typed = false;
            this.moved = false;
            this.pickWhenLoaded = false;
            this._showSelection();
        }

        _bind() {
            this.input.addEventListener("focus", () => {
                this.open();
                this.input.select();
                this.focusedNow = true;
            });
            // Typing replaces the shown name: keep it selected when focusing by click (mouseup would unselect it)
            this.input.addEventListener("mouseup", (event) => {
                if (this.focusedNow) {
                    event.preventDefault();
                }
                this.focusedNow = false;
            });
            this.input.addEventListener("keydown", () => {
                this.focusedNow = false;
            });
            this.input.addEventListener("blur", () => this.close());
            this.input.addEventListener("input", () => {
                this.typed = true;
                this.moved = false;
                this.open();
                const word = this.input.value.trim();
                clearTimeout(this.timer);
                this._checkQueryFields();
                if (this.cache.has(word)) {
                    this._search(word);
                } else {
                    this.timer = setTimeout(() => this._search(word), SEARCH_DELAY);
                }
            });
            this.input.addEventListener("keydown", (event) => this._onKeydown(event));

            // Keep the focus in the input, so clicking an option or the control does not close the list first
            this.root.addEventListener("mousedown", (event) => {
                if (event.target !== this.input && event.target.closest(".search-select-control, .search-select-list")) {
                    event.preventDefault();
                    if (document.activeElement !== this.input) {
                        this.input.focus();
                    } else if (!this.isOpen) {
                        this.open();
                    }
                }
            });
            this.clearButton?.addEventListener("click", () => {
                this.clear();
                this.typed = false;
                this.input.value = "";
                if (this.isOpen) {
                    this._search("");
                }
            });
            this.list.addEventListener("click", (event) => {
                const item = event.target.closest("[data-index]");
                if (item) {
                    this._pick(this.state.entries[item.dataset.index]);
                }
            });
            this.list.addEventListener("mousemove", (event) => {
                const item = event.target.closest("[data-index]");
                if (item && Number(item.dataset.index) !== this.state.cursor) {
                    this.state.cursor = Number(item.dataset.index);
                    this._markCursor();
                }
            });
            this.list.addEventListener("scroll", () => {
                if (this.list.scrollTop + this.list.clientHeight >= this.list.scrollHeight - 40) {
                    this._loadMore();
                }
            });
        }

        _onKeydown(event) {
            switch (event.key) {
                case "ArrowDown":
                case "ArrowUp":
                    event.preventDefault();
                    if (!this.isOpen) {
                        this.open();
                    } else {
                        this._moveCursor(event.key === "ArrowDown" ? 1 : -1);
                    }
                    break;
                case "Enter":
                    if (!this.isOpen) {
                        return;
                    }
                    // Never submit the form from here
                    event.preventDefault();
                    if (this._isCurrent()) {
                        this._pick(this.state.entries[this.state.cursor]);
                    } else {
                        // The list does not show the results for the typed text yet
                        this.pickWhenLoaded = true;
                    }
                    break;
                case "Escape":
                    if (this.isOpen) {
                        // Do not close a surrounding modal
                        event.preventDefault();
                        event.stopPropagation();
                        this.close();
                        this.input.select();
                    }
                    break;
                case "Tab":
                    if (this.isOpen && this.moved && this._isCurrent()) {
                        this._pick(this.state.entries[this.state.cursor], { keepFocus: false });
                    }
                    break;
            }
        }

        // The list shows the complete first page for the text in the input
        _isCurrent() {
            const { state } = this;
            const word = this.typed ? this.input.value.trim() : "";
            return state && state.word === word && !(state.loading && state.page === 0) && !!state.entries[state.cursor];
        }

        _pick(entry, { keepFocus = true } = {}) {
            if (!entry) {
                return;
            }
            if (entry.isNew) {
                this.setValue(NEW, entry.name);
            } else {
                this.setValue(String(entry.id), entry.name, { option: entry });
            }
            this.close();
            if (keepFocus && document.activeElement === this.input) {
                this.input.select();
            }
        }

        // The input shows the name of the selection unless the user is typing
        _showSelection() {
            if (!this.typed) {
                this.input.value = this.textInput.value;
            }
            if (this.keyValues) {
                this.badge.textContent = this.isNew ? "New" : "";
                this.badge.title = "New";
            } else {
                this.badge.textContent = this.value || "—";
                this.badge.title = this.isNew ? "New" : "ID";
            }
            this.root.classList.toggle("is-new", this.isNew);
            this.root.classList.toggle("has-value", !!this.value);
        }

        // Hidden elements are not submitted: their inputs are disabled (and enabled again only if disabled here)
        _toggleDependents() {
            if (!this.valueInput.id) {
                return;
            }
            for (const element of document.querySelectorAll(`[data-search-select-new-only="${CSS.escape(this.valueInput.id)}"]`)) {
                element.classList.toggle("d-none", !this.isNew);
                for (const input of element.querySelectorAll("input, select, textarea")) {
                    if (!this.isNew && !input.disabled) {
                        input.disabled = true;
                        input.dataset.searchSelectDisabled = "";
                    } else if (this.isNew && "searchSelectDisabled" in input.dataset) {
                        input.disabled = false;
                        delete input.dataset.searchSelectDisabled;
                    }
                }
            }
        }

        // Shown values of the fields in `data-query-fields`, by query parameter
        _queryFieldValues() {
            const values = {};
            for (const [param, id] of Object.entries(this.queryFields)) {
                const other = document.getElementById(`${id}-container`)?.searchSelect;
                values[param] = other ? other.textInput.value : document.getElementById(id)?.value ?? "";
            }
            return values;
        }

        // Options loaded for other values of the query fields are stale
        _checkQueryFields() {
            const key = JSON.stringify(this._queryFieldValues());
            if (key !== this.queryFieldsKey) {
                this.queryFieldsKey = key;
                this.cache.clear();
            }
        }

        async _fetch(params, signal) {
            const url = new URL(this.url, window.location.href);
            for (const [key, value] of Object.entries({ ...this._queryFieldValues(), ...params })) {
                url.searchParams.set(key, value);
            }
            const response = await fetch(url, { signal, headers: { Accept: "application/json" } });
            if (!response.ok) {
                throw new Error(`${response.status} ${response.statusText}`);
            }
            return response.json();
        }

        async _lookUpName() {
            try {
                await this.selectedOption();
            } catch (error) {
                console.error("Could not look up the selected option:", error);
            }
        }

        _search(word) {
            clearTimeout(this.timer);
            this._checkQueryFields();
            this.state?.controller?.abort();
            const cached = this.cache.get(word);
            this.state = cached
                ? { ...cached, items: [...cached.items], cursor: -1, loading: false, error: false }
                : { word, items: [], page: 0, hasMore: true, cursor: -1, loading: false, error: false };
            this.state.entries = [];
            this.list.scrollTop = 0;
            if (cached) {
                this._initCursor();
                this._render();
                this._fillList();
            } else {
                this._loadMore();
            }
        }

        async _loadMore() {
            const state = this.state;
            if (!state || state.loading || !state.hasMore) {
                return;
            }
            const controller = (state.controller = new AbortController());
            state.loading = true;
            this._render();
            try {
                const result = await this._fetch({ word: state.word, page: state.page }, controller.signal);
                state.items.push(...result.options);
                state.page += 1;
                state.hasMore = result.has_more;
                this.cache.set(state.word, { word: state.word, items: [...state.items], page: state.page, hasMore: state.hasMore });
            } catch (error) {
                if (error.name === "AbortError") {
                    return;
                }
                console.error("Could not load options:", error);
                state.error = true;
                state.hasMore = false;
            } finally {
                state.loading = false;
            }
            if (state !== this.state) {
                return;
            }
            if (state.cursor === -1) {
                this._initCursor();
            }
            this._render();
            if (this.pickWhenLoaded && this._isCurrent()) {
                this.pickWhenLoaded = false;
                this._pick(state.entries[state.cursor]);
                return;
            }
            this._fillList();
        }

        // Keep loading until the list can scroll, otherwise its end can never be reached
        _fillList() {
            if (this.isOpen && this.state.hasMore && this.list.scrollHeight <= this.list.clientHeight) {
                this._loadMore();
            }
        }

        // Typing highlights the option with exactly that name, else creating it if allowed, else the best match;
        // otherwise the current selection is highlighted
        _initCursor() {
            const { state } = this;
            state.entries = this._entries();
            if (this.typed && state.word) {
                const exact = state.entries.findIndex((entry) => !entry.isNew && normalize(entry.name) === normalize(state.word));
                state.cursor = exact >= 0 ? exact : state.entries.length ? 0 : -1;
            } else {
                state.cursor = state.entries.findIndex((entry) => !entry.isNew && String(entry.id) === this.value);
            }
        }

        // The options, after an entry that creates the typed text when new names are allowed
        _entries() {
            const { state } = this;
            if (!this.allowNew || !this.typed || !state.word) {
                return state.items;
            }
            return [{ id: null, name: state.word, isNew: true }, ...state.items];
        }

        _render() {
            const { state } = this;
            state.entries = this._entries();
            const rows = state.entries.map((entry, i) => {
                const row = document.createElement("li");
                row.id = `${this.list.id}-${i}`;
                row.className = "search-select-option";
                row.setAttribute("role", "option");
                row.dataset.index = i;
                if (entry.isNew) {
                    row.classList.add("create");
                    const icon = document.createElement("i");
                    icon.className = "bi bi-plus-lg";
                    row.append(
                        span("search-select-option-header", icon),
                        span("search-select-option-name", entry.name),
                        span("search-select-option-description", this.newLabel),
                    );
                } else {
                    row.append(
                        span("search-select-option-header", entry.header ?? ""),
                        span("search-select-option-name", highlighted(entry.name, state.word)),
                        span("search-select-option-description", entry.description ?? ""),
                    );
                    if (String(entry.id) === this.value && !this.isNew) {
                        row.classList.add("selected");
                        row.setAttribute("aria-selected", "true");
                    }
                }
                return row;
            });
            const message = state.error
                ? "Could not load options"
                : state.loading
                    ? "Loading…"
                    : !state.items.length
                        ? (this.allowNew && state.word ? "No existing matches" : "No matches")
                        : null;
            if (message) {
                const status = document.createElement("li");
                status.className = "search-select-status";
                status.textContent = message;
                rows.push(status);
            }
            this.list.replaceChildren(...rows);
            this._markCursor();
            this._place();
        }

        _markCursor() {
            const { state } = this;
            for (const row of this.list.querySelectorAll(".search-select-option")) {
                row.classList.toggle("cursor", Number(row.dataset.index) === state.cursor);
            }
            const current = this.list.children[state.cursor];
            if (current && state.cursor >= 0) {
                this.input.setAttribute("aria-activedescendant", current.id);
            } else {
                this.input.removeAttribute("aria-activedescendant");
            }
        }

        _moveCursor(step) {
            const { state } = this;
            if (!state || !state.entries.length) {
                return;
            }
            this.moved = true;
            state.cursor = Math.min(Math.max(state.cursor + step, 0), state.entries.length - 1);
            this._markCursor();
            // Scroll the list only, scrollIntoView would also scroll the page or modal
            const row = this.list.children[state.cursor];
            if (row.offsetTop < this.list.scrollTop) {
                this.list.scrollTop = row.offsetTop;
            } else if (row.offsetTop + row.offsetHeight > this.list.scrollTop + this.list.clientHeight) {
                this.list.scrollTop = row.offsetTop + row.offsetHeight - this.list.clientHeight;
            }
            if (state.cursor >= state.entries.length - 3) {
                this._loadMore();
            }
        }

        // Open below the input, or above it when there is more room there
        _place() {
            const rect = this.control.getBoundingClientRect();
            const below = window.innerHeight - rect.bottom - 8;
            const above = rect.top - 8;
            const up = below < Math.min(LIST_MAX_HEIGHT, this.list.scrollHeight) && above > below;
            this.root.classList.toggle("up", up);
            this.list.style.maxHeight = Math.max(Math.min(LIST_MAX_HEIGHT, up ? above : below), 120) + "px";
        }

        static init(container = document) {
            const roots = container.matches?.("[data-search-select]") ? [container] : [];
            roots.push(...container.querySelectorAll("[data-search-select]"));
            for (const root of roots) {
                if (!root.searchSelect) {
                    new SearchSelect(root);
                }
            }
        }
    }

    document.addEventListener("DOMContentLoaded", () => SearchSelect.init());
    document.addEventListener("htmx:load", (event) => SearchSelect.init(event.detail.elt));

    return SearchSelect;
})();
