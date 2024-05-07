var selected_column_target = null;
var selected_column_var = null;

function show_query_col(column_id) {
    column_id = column_id.replace(":", "\\:");

    $(".temp-query-input").hide();
    $(".query-col").show();
    $(`#${column_id}`).hide();
    $(`#${column_id}-query`).show().on("focusout", function() {
        $(this).hide();
        $(`#${column_id}`).show();
    }).children("input").focus();
}

function show_filter_col(column_id) {
    column_id = column_id.replace(":", "\\:");

    $(`#${column_id}`).hide();
    $(`#${column_id}-filter`).show().on("focusout", function(e) {
    });
}

$(document).keyup(function(e) {
    if (e.key === "Escape") {
        $(".temp-query-input").hide();
        $(".query-col").show();
    }
});