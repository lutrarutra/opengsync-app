var selected_column_var = null;

function show_query_col() {
    const w = $(`#table-col-${selected_column_var}`).width();
    const h = $(`#table-col-${selected_column_var}`).height();
    $(".temp-query-input").hide();
    $(".query-col").show();
    $(`#table-col-${selected_column_var}`).hide();
    $(`#table-col-${selected_column_var}-temp`).show().css({
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
    selected_column_var = e.target.id.split("-")[2];
    console.log(selected_column_var);
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