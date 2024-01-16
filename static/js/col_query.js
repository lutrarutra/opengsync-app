var selected_column_target = null;
var selected_column_var = null;

function show_query_col() {
    const w = $(`#${selected_column_target}\\:${selected_column_var}`).width();
    const h = $(`#${selected_column_target}\\:${selected_column_var}`).height();
    $(".temp-query-input").hide();
    $(".query-col").show();
    $(`#${selected_column_target}\\:${selected_column_var}`).hide();
    $(`#${selected_column_target}\\:${selected_column_var}-temp`).show().css({
        "width": `${w}px`,
    }).children("input").css({
        "width": `${w}px`,
        "height": `${h}px`,
    }).focus();
}

$(document).off("contextmenu", ".query-col").on("contextmenu", ".query-col", function(e) {
    e.preventDefault();
    const x = e.pageX;
    const y = e.pageY;

    const target_id = $(e.target).closest("th").attr("id");

    selected_column_target = target_id.split(":")[0];
    selected_column_var = target_id.split(":")[1];
    
    $("#copy-edit-menu").css({
        display: "block",
        left: x + 8, top: y + 8
    }).append([
        `<li><a class='dropdown-item' onclick='show_query_col()'>Query</a></li>`,
    ]);

    $("#right-click-bg").css({
        display: "block"
    });
});

$(document).keyup(function(e) {
    if (e.key === "Escape") {
        $(".temp-query-input").hide();
        $(".query-col").show();
    }
});