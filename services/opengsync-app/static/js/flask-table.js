class HTMXTable {
    constructor(selector, url=null, options = {}) {
        this.selector = selector;
        this.$container = $(selector);
        this.$table = this.$container.find("table").first();
        this.url = url;
        this.sort_by = null;
        this.sort_order = null;
        this.filters = {};
        this.options = {
            searchDelay: 1500, // Default delay in ms
            state: {}, // Initial state for filters and sorting
            ...options
        };
        
        this.multiselects = [];
        this._init(this.options.state);
        this._bindEvents();
    }

    _show_filter_menu(th, focus=true) {
        $(th).find(".table-col-header.active").removeClass("active");
        this.$table.find(".multiple-select.active").removeClass("active");
        $(th).find(".table-col-header.col-header-multiselect").addClass("active");
        if (focus) {
            $(th).find(".table-col-header.col-header-multiselect")
            .find(".multiple-select").first().addClass("active")
            .find("input.option-search").focus();
        }
    }

    _hide_filter_menu(th) {
        $(th).find(".table-col-header.active").removeClass("active");
        $(th).find(".table-col-header.col-header-default").addClass("active");
    }

    _show_search_menu(th) {
        $(th).find(".table-col-header.active").removeClass("active");
        $(th).find(".table-col-header.col-header-search").addClass("active");
        
        const $input = $(th).find(".table-col-header.col-header-search input").first();
        $input.focus();
        
        // Set cursor at end of input
        const value = $input.val();
        $input[0].setSelectionRange(value.length, value.length);
    }

    _hide_search_menu(th) {
        $(th).find(".table-col-header.active").removeClass("active");
        $(th).find(".table-col-header.col-header-default").addClass("active");
    }

    _ajax(state) {
        const $tbody = this.$table.find("tbody");
        const height = $tbody.outerHeight(); // Capture height before emptying
        
        htmx.ajax("GET", this.url, {
            target: this.selector,
            swap: "outerHTML",
            values: state
        });
        
        $tbody.empty();
        $tbody.append(`
            <tr class="loading-row">
                <td colspan="100%" style="height: ${height}px; text-align: center; vertical-align: middle;">
                    <div class="spinner-border cemm-blue" role="status">
                        <span class="visually-hidden">Loading...</span>
                    </div>
                </td>
            </tr>
        `);
    }

    _init(state) {
        this.$table.find(".multiple-select").each((index, element) => {
            let field_name = $(element).data("field_name");
            let select = new MultipleSelect(
                $(element), {
                    onApply: (state) => {
                        let table_state = this._getState();
                        table_state[$(element).data("field_name") + "_in"] = JSON.stringify(state);
                        if (this.url) {
                            this._ajax(table_state);
                        } else {
                            console.log("Warning: No URL provided for HTMXTable. Changes in multiple select will not trigger an update.");
                        }
                    },
                    selected: JSON.parse(state[field_name + "_in"] || "[]")
                }
            );
            if (state[field_name + "_in"]) {
                this._show_filter_menu($(element).closest("th"), focus=false);
            }
            this.multiselects.push(select);
        });

        this.$table.find(".table-query-input").each((index, element) => {
            let th = $(element).closest("th");
            let field_name = th.data("field_name");
            if (state[field_name]) {
                this._show_search_menu(th);
            }
        });
    }

    _handleSearch(field_name, search_value) {
        let state = this._getState(false);
        state[field_name] = search_value;
        this._ajax(state);
    }

    _getState(include_sort=true) {
        let state = {};
        this.multiselects.forEach(select => {
            let field_name = select.$container.data("field_name");
            if (select.options.selected.length > 0) {
                state[field_name + "_in"] = JSON.stringify(select.options.selected);
            }
        });
        if (include_sort) {
            this.$table.find("th.sortable-col").each((index, th) => {
                let $th = $(th);
                if ($th.data("current_sort")) {
                    state.sort_by = $th.data("sort_by");
                    state.sort_order = $th.data("current_sort");
                }
            });
        }
        return state;
    }

    _bindEvents() {
        // Show multiselect filter
        this.$table.on("click", ".table-multiselect-filter-btn", (e) => {
            e.stopPropagation();
            this._show_filter_menu($(e.currentTarget).closest("th"));

        });
        
        // Show search query field
        this.$table.on("click", ".table-column-search-btn", (e) => {
            e.stopPropagation();
            this._show_search_menu($(e.currentTarget).closest("th"));
        });
        
        // Search query input
        this.$table.on("input", ".table-col-header.col-header-search input", (e) => {
            const $input = $(e.currentTarget);
            const searchValue = $input.val();
            
            clearTimeout(this.searchTimer);
            
            this.searchTimer = setTimeout(() => {
                this._handleSearch($input.closest("th").data("field_name"), searchValue);
            }, this.options.searchDelay);
        });
        
        // enter key in search query input
        this.$table.on("keydown", ".table-col-header.col-header-search input", (e) => {
            if (e.key === "Enter") {
                clearTimeout(this.searchTimer);
                e.preventDefault();
                const $input = $(e.currentTarget);
                const searchValue = $input.val();
                this._handleSearch($input.closest("th").data("field_name"), searchValue);
            }
        });
        
        // Sort btn
        this.$table.on("click", ".sort-btn", (e) => {
            e.stopPropagation();
            let state = this._getState();
            state.sort_by = $(e.currentTarget).closest("th").data("sort_by");
            let current_sort = $(e.currentTarget).closest("th").data("current_sort");
            state.sort_order = current_sort === "asc" ? "desc" : "asc";
            this._ajax(state);
        });

        // Pagination
        this.$container.on("click", ".pagination .page-item", (e) => {
            e.preventDefault();
            let page = $(e.currentTarget).data("page");
            let state = this._getState();
            state.page = page;
            this._ajax(state);
        });
    }
}

function toggle_index_display() {
    $(".index-badge").each(function() {
        $(this).toggle();
    });
}