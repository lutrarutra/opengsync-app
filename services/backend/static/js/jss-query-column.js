/**
 * Spreadsheet column whose options are searched on the backend (QueryColumn in components/tables/spreadsheet.py).
 * It is a jspreadsheet custom editor: `{ type: jssQueryColumn, url, labels }`.
 *
 * Cells hold the option id and show its name; `labels` maps the ids in the table to their names and collects the
 * names of every option the backend returns. The editor requests `url` with `word` and `page` and expects
 * `{options: [{id, name}], has_more}`, further pages load when the list is scrolled to its end. Text that is typed
 * or pasted instead of picked is resolved to the option with exactly that name, otherwise it stays text and the
 * backend rejects it.
 */
window.jssQueryColumn = (() => {
    const SEARCH_DELAY = 250;
    const MAX_HEIGHT = 300;
    const MIN_WIDTH = 400;
    const MAX_WIDTH = 750;

    const labels = (options) => options.labels || (options.labels = {});
    const normalize = (text) => String(text).trim().toLowerCase();

    const fetchPage = async (options, word, page, signal) => {
        const url = new URL(options.url, window.location.href);
        url.searchParams.set("word", word);
        url.searchParams.set("page", page);
        const response = await fetch(url, { signal, headers: { Accept: "application/json" } });
        if (!response.ok) {
            throw new Error(`${response.status} ${response.statusText}`);
        }
        const result = await response.json();
        for (const option of result.options) {
            labels(options)[option.id] = option.name;
        }
        return result;
    };

    // Id of the only known option with this name
    const findByName = (name, options) => {
        const matches = Object.keys(labels(options)).filter((id) => normalize(labels(options)[id]) === normalize(name));
        return matches.length === 1 ? Number(matches[0]) : null;
    };

    // Ids are numbers, anything else in a cell is text that is not (yet) an option
    const render = (cell, value, options) => {
        if (typeof value === "number") {
            cell.textContent = labels(options)[value] ?? `[${value}]`;
        } else {
            cell.textContent = value ?? "";
        }
        cell.classList.toggle("jss_query_unresolved", typeof value === "string" && value !== "");
    };

    // Searches the backend for the name, once for all cells pasted with it
    const resolve = async (worksheet, x, y, text, options) => {
        const pending = options.pending || (options.pending = {});
        const key = normalize(text);
        try {
            pending[key] = pending[key] || fetchPage(options, text, 0).finally(() => delete pending[key]);
            await pending[key];
        } catch (error) {
            console.error(`Could not look up '${text}':`, error);
            return;
        }
        const id = findByName(text, options);
        // The cell may have changed meanwhile
        if (id === null || worksheet.options.data[y]?.[x] !== text) {
            return;
        }
        worksheet.options.data[y][x] = id;
        render(worksheet.records[y][x].element, id, options);
    };

    const renderList = (state) => {
        const items = state.items.map((item, i) => {
            const element = document.createElement("div");
            element.className = "jss_query_item";
            element.textContent = item.name;
            element.dataset.index = i;
            element.classList.toggle("jss_query_cursor", i === state.cursor);
            element.classList.toggle("jss_query_selected", item.id === state.value);
            return element;
        });
        const message = state.error ? "Could not load options" : state.loading ? "Loading…" : !items.length ? "No matches" : null;
        if (message) {
            const status = document.createElement("div");
            status.className = "jss_query_status";
            status.textContent = message;
            items.push(status);
        }
        state.list.replaceChildren(...items);
        place(state);
    };

    // Open below the cell, or above it when there is more room there, and stay within the content
    const place = (state) => {
        const { cell, list, worksheet } = state;
        const content = worksheet.content;
        const contentRect = content.getBoundingClientRect();
        const cellRect = cell.getBoundingClientRect();
        const left = contentRect.left + content.clientLeft;
        const right = left + content.clientWidth;
        const top = contentRect.top + content.clientTop + worksheet.thead.getBoundingClientRect().height;
        const bottom = contentRect.top + content.clientTop + content.clientHeight;

        const width = Math.min(Math.max(cellRect.width, MIN_WIDTH), MAX_WIDTH, content.clientWidth);
        list.style.width = width + "px";
        list.style.left = Math.min(0, right - cellRect.left - width) + "px";

        const below = bottom - cellRect.bottom - 8;
        const above = cellRect.top - top - 8;
        const up = below < Math.min(MAX_HEIGHT, list.scrollHeight) && above > below;
        list.classList.toggle("jss_query_up", up);
        list.style.maxHeight = Math.max(Math.min(MAX_HEIGHT, up ? above : below), 80) + "px";
    };

    const search = (state, word) => {
        clearTimeout(state.timer);
        if (state.controller) {
            state.controller.abort();
        }
        Object.assign(state, { word, page: 0, items: [], cursor: -1, hasMore: true, loading: false, error: false });
        state.list.scrollTop = 0;
        loadMore(state);
    };

    const loadMore = async (state) => {
        if (state.loading || !state.hasMore) {
            return;
        }
        const controller = (state.controller = new AbortController());
        state.loading = true;
        renderList(state);
        try {
            const result = await fetchPage(state.options, state.word, state.page, controller.signal);
            if (controller !== state.controller) {
                return;
            }
            state.items.push(...result.options);
            state.page += 1;
            state.hasMore = result.has_more;
            if (state.cursor === -1) {
                // Typing highlights the best match, otherwise the current value
                state.cursor = state.typed && state.word ? 0 : state.items.findIndex((item) => item.id === state.value);
            }
        } catch (error) {
            if (error.name === "AbortError") {
                return;
            }
            console.error("Could not load options:", error);
            state.error = true;
            state.hasMore = false;
        } finally {
            if (controller === state.controller) {
                state.loading = false;
            }
        }
        renderList(state);
        // Keep loading until the list can scroll, otherwise its end can never be reached
        if (state.hasMore && state.list.scrollHeight <= state.list.clientHeight) {
            loadMore(state);
        }
    };

    const moveCursor = (state, step) => {
        if (!state.items.length) {
            return;
        }
        state.moved = true;
        state.cursor = Math.min(Math.max(state.cursor + step, 0), state.items.length - 1);
        renderList(state);
        // Scroll the list only, scrollIntoView would also scroll the spreadsheet and close the editor
        const item = state.list.children[state.cursor];
        if (item.offsetTop < state.list.scrollTop) {
            state.list.scrollTop = item.offsetTop;
        } else if (item.offsetTop + item.offsetHeight > state.list.scrollTop + state.list.clientHeight) {
            state.list.scrollTop = item.offsetTop + item.offsetHeight - state.list.clientHeight;
        }
        if (state.cursor >= state.items.length - 3) {
            loadMore(state);
        }
    };

    return {
        createCell(cell, value, x, y, worksheet, options) {
            cell.classList.add("jss_query");
            render(cell, value, options);
        },

        // Values set by pasting, typing, undo or setValue: names become ids when the option is known
        updateCell(cell, value, x, y, worksheet, options) {
            if (typeof value === "string") {
                const text = value.trim();
                const id = text ? findByName(text, options) : null;
                value = id ?? text;
                if (text && id === null) {
                    resolve(worksheet, x, y, text, options);
                }
            }
            render(cell, value, options);
            return value;
        },

        openEditor(cell, value, x, y, worksheet, options, e) {
            // Typing in a selected cell replaces its value, double click, Enter and F2 edit it
            const typed = e && e.type === "keydown" && (e.key.length === 1 || e.key === "Process");

            const input = document.createElement("input");
            input.className = "jss_query_input";
            input.autocomplete = "off";
            input.value = typed ? "" : typeof value === "number" ? labels(options)[value] ?? "" : value ?? "";

            const list = document.createElement("div");
            list.className = "jss_query_list";

            cell.classList.add("editor", "jss_query_editor");
            cell.innerHTML = "";
            // jspreadsheet closes the editor by blurring the first child on Enter and Tab
            cell.append(input, list);

            const state = { cell, input, list, worksheet, options, value, typed: false, moved: false, selected: undefined };
            cell.jssQuery = state;

            input.addEventListener("input", () => {
                state.typed = true;
                state.moved = false;
                clearTimeout(state.timer);
                state.timer = setTimeout(() => search(state, input.value.trim()), SEARCH_DELAY);
            });
            input.addEventListener("keydown", (event) => {
                if (event.key === "ArrowDown" || event.key === "ArrowUp") {
                    event.preventDefault();
                    moveCursor(state, event.key === "ArrowDown" ? 1 : -1);
                }
            });
            input.onblur = () => {
                if (worksheet.edition && worksheet.edition[0] === cell) {
                    worksheet.closeEditor(cell, true);
                }
            };

            // Keep the focus in the input, so picking an option does not close the editor first
            list.addEventListener("mousedown", (event) => event.preventDefault());
            list.addEventListener("click", (event) => {
                const item = event.target.closest(".jss_query_item");
                if (item) {
                    state.selected = state.items[item.dataset.index].id;
                    worksheet.closeEditor(cell, true);
                }
            });
            list.addEventListener("scroll", () => {
                if (list.scrollTop + list.clientHeight >= list.scrollHeight - 40) {
                    loadMore(state);
                }
            });

            input.focus();
            if (!typed) {
                input.select();
            }
            search(state, "");
        },

        closeEditor(cell, save, x, y, worksheet, options) {
            const state = cell.jssQuery;
            delete cell.jssQuery;
            clearTimeout(state.timer);
            if (state.controller) {
                state.controller.abort();
            }
            state.input.onblur = null;
            cell.classList.remove("jss_query_editor");

            if (!save) {
                return;
            }
            if (state.selected !== undefined) {
                return state.selected;
            }
            const text = state.input.value.trim();
            // Emptied input
            if (state.typed && !text && !state.moved) {
                return "";
            }
            const current = state.items[state.cursor];
            // The highlighted option, if the list shows the results for the text in the input
            if ((state.typed || state.moved) && current && !state.loading && state.word === (state.typed ? text : "")) {
                return current.id;
            }
            if (!state.typed) {
                return state.value;
            }
            // Resolved by name in updateCell
            return text;
        },
    };
})();
