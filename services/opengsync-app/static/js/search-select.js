class SearchSelect {
    constructor(element, url, field_name, options={}) {
        this.$element = $(element);
        this.$search_input = this.$element.find("input.searchbar-input").first();
        this.$selected_input = this.$element.find("input.searchbar-data").first();
        this.$options_container = this.$element.find(".options-container").first();
        this.$selected_bar = this.$element.find(".selected-bar").first();
        this.url = url;
        this.field_name = field_name;

        this.options = {
            placeholder: this.$element.data("placeholder") || "Select...",
            searchDelay: 300,
            onChange: null, // Callback function
            ...options
        };

        this.searchTimer = null;
        this.$element.data("searchSelectInstance", this);
        
        this._bindEvents();
        this._init();
    }

    _init() {
        if (this.$selected_input.val() && this.$search_input.val()) {
            let $span = $("<span class='search-select-name'>").text(this.$search_input.val());
            this.$selected_bar.empty().append($span).css("display", "flex");
            this.$search_input.val("").hide();
            window.domm[this.field_name] = $span;
        }
        else if (this.$selected_input.val() && window.domm[this.field_name]) {
            this.$selected_bar.empty().append(window.domm[this.field_name]).css("display", "flex");
            this.$search_input.hide();
        }
        this._ajax("");
    }

    open() {
        this.$element.addClass("active");
    }

    close() {
        this.$element.removeClass("active");
        if (this.$selected_input.val()) {
            this.$selected_bar.css("display", "flex");
            this.$search_input.hide();
        } else {
            this.$selected_bar.hide();
            this.$search_input.show();
        }
    }

    _ajax(word) {
        htmx.ajax("GET", this.url, {
            target: this.$options_container[0],
            swap: "innerHTML",
            values: { 
                [this.$search_input.attr("name")]: word,
                field_name: this.field_name,
                selected: this.$selected_input.val()
            }
        });
    }

    _bindEvents() {
        // Handle query input
        this.$search_input.on("input", () => {
            this._handleSearch();
        });

        // Show options on focus
        this.$search_input.on("focus", () => {
            this.open();
        });

        // Close dropdown when clicking outside
        $(document).on("click", (e) => {
            if (!$(e.target).closest(this.$element).length) {
                this.close();
            }
        });

        // Handle option selection
        this.$options_container.on("click", "li.option", (e) => {
            e.stopPropagation();
            window.domm[this.field_name] = $(e.currentTarget).clone().removeClass("option").addClass("selected-option");
            this.$selected_bar.empty().append(window.domm[this.field_name]).css("display", "flex");
            this.$search_input.hide();
            this.$selected_input.val($(e.currentTarget).data("value"));
            $(e.currentTarget).addClass("selected").siblings().removeClass("selected");
            if (typeof this.options.onChange === "function") {
                this.options.onChange();
            }
            this.$selected_input.trigger("change");
            this.close();
        });

        // When clicking the selected bar, show the search input again
        this.$selected_bar.on("click", () => {
            this.$selected_bar.hide();
            this.$search_input.show().focus();
        });

        // Clear button
        this.$element.on("click", ".clear-btn", (e) => {
            e.stopPropagation();
            this.$selected_input.val("");
            this.$search_input.val("");
            this.$options_container.find("li.option").removeClass("selected");
            this.$selected_bar.empty();
            this.$selected_input.trigger("change");
            this.close();
        });

        // After htmx content is swapped, update the selected state
        this.$options_container.on("htmx:afterSwap", () => {
            if (this.$selected_input.val()) {
                this.$options_container.find(`li.option[data-value="${this.$selected_input.val()}"]`).addClass("selected");
            }
        });
    }

    _handleSearch() {
        const word = this.$search_input.val().toLowerCase();
        clearTimeout(this.searchTimer);
        
        this.searchTimer = setTimeout(() => {
            this._ajax(word);
        }, this.options.searchDelay);
    }
}