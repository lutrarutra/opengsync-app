var selected_column_target = null;
var selected_column_var = null;

function show_query_col(column_id) {
    column_id = column_id.replace(":", "\\:");
    const w = $(`#${column_id}`).width();
    const h = $(`#${column_id}`).height();
    $(".temp-query-input").hide();
    $(".query-col").show();
    $(`#${column_id}`).hide();
    $(`#${column_id}-temp`).show().on("focusout", function() {
        $(this).hide();
        $(`#${column_id}`).show();
    }).children("input").focus();
}


$(document).keyup(function(e) {
    if (e.key === "Escape") {
        $(".temp-query-input").hide();
        $(".query-col").show();
    }
});