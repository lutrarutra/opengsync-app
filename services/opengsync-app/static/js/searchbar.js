function select_option(option) {
    let field = option.data("field").replace("-search", "");

    set_selected_bar(field, option.prop('outerHTML'));
    let value = option.data("value");
    let search_bar = $(`#${field}-search`);
    let data_field = $(`#${field}`);
    
    data_field.val(value);
    
    $(`#${field}-invalid-container`).empty();
    if (search_bar.hasClass("is-invalid")){
        search_bar.removeClass("is-invalid");
    }
    htmx.trigger(`#${field}`, "change");
    
    // Store as HTML string instead of jQuery object
    window.domm[field] = option.prop('outerHTML');
}

function set_selected_bar(field_name, html_string) {
    let selected_bar = $(`#${field_name}-selected_bar`);
    selected_bar.css("display", "flex");
    selected_bar.empty();
    selected_bar.append(html_string);
    $(`#${field_name}-search`).css("display", "none");
}

$(document).on("mousedown", ".search-select-option", function() {
    select_option($(this));
});

$(document).on("focus", ".searchbar-input:not(.disabled)", function() {
    $(`#${$(this).data("field")}-results`).css("display", "block");
    this.select();
    $(this).parent().addClass("active");
});

$(document).on("blur", ".searchbar-input:not(.disabled)", function() {
    $(this).parent().removeClass("active");
    $(".search-select-results").hide();
    
    let field_name = $(this).data("field");
    if (!$(`#${field_name}`).val()) {
        $(this).val("");
    } else {
        $(`#${field_name}-selected_bar`).show();
        $(this).hide();
    }
});

$(document).on("change", ".searchbar-input:not(.disabled)", function() {
    if ($(this).val() === "") {
        $(`#${$(this).data("field")}`).val("");
    }
});

$(document).on("click", ".clear-search-btn", function() {
    $(`#${$(this).data("field")}-search`).val("");
    $(`#${$(this).data("field")}`).val("");
    $(`#${$(this).data("field")}-selected_bar`).hide();
    $(`#${$(this).data("field")}-search`).show();
    $(this).parent().parent().find(".selected").removeClass("selected");
})

$(document).on("click", ".selected-bar", function() {
    $(this).hide();
    $(`#${$(this).data("field")}-search`).show().focus();
});
