class MultipleSelect {
    constructor(selector, options={}) {
        this.$container = $(selector);
        this.options = {
            placeholder: this.$container.data("placeholder") || "Select...",
            searchDelay: 300,
            selected: [],
            onChange: null, // Callback function
            onApply: null, // Callback function for Apply button
            ...options
        };
        this.searchTimer = null;
        this.$container.data("multipleSelectInstance", this);
        
        this._init(this.options.selected);
        this._bindEvents();
    }
    
    _init(selected) {
        const $selectedContainer = this.$container.find(".selected-container").first();
        if ($selectedContainer.children().length === 0) {
            $selectedContainer.text(this.options.placeholder);
        }
        if (selected.length > 0) {
            this._setSelected(selected);
            this._updateSelectAllState();
        }
    }
    
    _setSelected(selected) {
        const $options = this.$container.find('.options-container .option');
        $options.each((i, el) => {
            const $option = $(el);
            const value = $option.data("value");
            if (selected.includes(value)) {
                $option.find('input[type="checkbox"]').prop("checked", true);
            }
        });
        this._updateSearchBar();
    }

    _bindEvents() {
        this.$container.on("click", ".dropdown-toggle", (e) => {
            e.stopPropagation();
            this.toggle();
        });

        this.$container.on("change", ".options-container .option input[type='checkbox']", (e) => {
            e.stopPropagation();
            this._updateSelectAllState();
            this._updateSearchBar();
            this._triggerChange();
        });
        
        this.$container.on("click", ".options-container", (e) => {
            e.stopPropagation();
        });
        
        this.$container.on("click", ".select-all", (e) => {
            this._handleSelectAll($(e.currentTarget));
        });
        
        this.$container.on("input", ".option-search", (e) => {
            this._handleSearch($(e.currentTarget));
        });
        
        this.$container.on("click", ".apply-btn", (e) => {
            e.stopPropagation();
            if (typeof this.options.onApply === "function") {
                this.options.onApply(this.getSelected());
            }
        });
        
        $(document).on("click", (e) => {
            if (!$(e.target).closest(this.$container).length) {
                this.close();
            }
        });
    }
    
    _handleSelectAll($selectAll) {
        const isChecked = $selectAll.prop("checked");
        this.$container
            .find('.options-container .option input[type="checkbox"]').prop("checked", isChecked);
        
        this._updateSearchBar();
        this._triggerChange();
    }
    
    _triggerChange() {
        if (typeof this.options.onChange === "function") {
            this.options.onChange(this.getSelected());
        }
    }
    
    _handleSearch($input) {
        const searchTerm = $input.val().toLowerCase();
        const $options = this.$container.find('.options-container .option');
        
        this.open();
        
        clearTimeout(this.searchTimer);
        
        this.searchTimer = setTimeout(() => {
            $options.each(function() {
                const $option = $(this);
                const text = $option.find('label').text().toLowerCase();
                $option.toggle(text.indexOf(searchTerm) > -1);
            });
        }, this.options.searchDelay);
    }
    
    _updateSelectAllState() {
        const totalOptions = this.$container.find('.options-container .option').length;
        const checkedOptions = this.$container.find('.options-container .option input[type="checkbox"]:checked').length;
        
        this.$container.find('.select-all').prop("checked", totalOptions === checkedOptions);
    }
    
    _updateSearchBar() {
        const $selectedContainer = this.$container.find(".selected-container").first();
        $selectedContainer.empty();
        
        this.$container.find(".options-container .option").each((i, el) => {
            const $option = $(el);
            const $checkbox = $option.find('input[type="checkbox"]');
            
            if ($checkbox.prop("checked")) {
                const labelText = $option.find("label .label-name").text();
                $selectedContainer.append(
                    `<span class="badge" data-id="${$checkbox.attr("id")}">${labelText}</span>`
                );
            }
        });
        
        if ($selectedContainer.children().length === 0) {
            $selectedContainer.text(this.options.placeholder);
        }
    }
    
    toggle() {
        this.$container.toggleClass("active");
        if (this.$container.hasClass("active")) {
            this.$container.find('.option-search').first().focus();
        }
    }
    
    open() {
        this.$container.addClass("active");
    }
    
    close() {
        this.$container.removeClass("active");
    }
    
    getSelected() {
        const selected = [];
        this.$container.find('.options-container .option input[type="checkbox"]:checked').each(function() {
            selected.push($(this).parent().data("value"));
        });
        return selected;
    }
    
    selectAll() {
        this.$container.find('.select-all').prop("checked", true).trigger("click");
    }
    
    clearAll() {
        this.$container.find('.select-all').prop("checked", false);
        this.$container.find('.options-container .option input[type="checkbox"]').prop("checked", false);
        this._updateSearchBar();
        this._triggerChange();
    }
    
    static Get(selector) {
        return $(selector).data("multipleSelectInstance");
    }
}