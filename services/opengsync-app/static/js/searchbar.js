function select_option(parent, value, field) {
    let data_field = $(`#${field}`);
    let selected_bar = $(`#${field}-selected_bar`);
    let search_bar = $(`#${field}-search`);

    $(selected_bar).css("display", "flex");
    $(search_bar).css("display", "none");

    $(parent).parent().find("li").removeClass("selected");
    $(parent).addClass("selected");

    // Set search field value
    var empty = $(selected_bar).empty();
    $(parent).find("a.search-select-option span").each(function() {
        empty.append($(this).clone());
    });

    $(data_field).val(value);

    // Hide invalid feedback
    $(`#${field}-invalid-container`).empty();
    if ($(search_bar).hasClass("is-invalid")){
        $(search_bar).removeClass("is-invalid");
    }

    htmx.trigger(`#${field}`, "change");
}

$(document).on("focus", ".searchbar-input:not(.disabled)", function() {
    $(`#${$(this).data("field")}-results`).css("display", "block");
    this.select();
    $(this).parent().addClass("active");
});

$(document).on("blur", ".searchbar-input:not(.disabled)", function() {
    $(this).parent().removeClass("active");
    $(".search-select-results").css("display", "none");
    
    let field_name = $(this).data("field");
    if (!$(`#${field_name}`).val()) {
        $(this).val("");
    } else {
        $(`#${field_name}-selected_bar`).css("display", "flex");
        $(this).css("display", "none");
    }
});

$(document).on("change", ".searchbar-input:not(.disabled)", function() {
    if ($(this).val() === "") {
        $(`#${$(this).data("field")}`).val("");
    }
});

$(document).on("mousedown", ".search-select-option", function() {
    let field = $(this).data("field");
    let value = $(this).data("value");

    select_option($(this).parent(), value, field.replace("-search", ""));
});

$(document).on("click", ".clear-search-btn", function() {
    $(`#${$(this).data("field")}-search`).val("");
    $(`#${$(this).data("field")}`).val("");
    $(`#${$(this).data("field")}-selected_bar`).css("display", "none");
    $(`#${$(this).data("field")}-search`).css("display", "block");
})

$(document).on("click", ".selected-bar", function() {
    $(this).css("display", "none");
    $(`#${$(this).data("field")}-search`).css("display", "block").focus();
});
