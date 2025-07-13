function show_query_col(column_id) {
    column_id = column_id.replace(":", "\\:");

    $(`#${column_id}`).hide();
    $(`#${column_id}-query`).show().on("focusout", function(){
        $(this).hide();
        $(`#${column_id}`).show();
    }).children("input").focus();
}

function show_filter_col(column_id) {
    column_id = column_id.replace(":", "\\:");
    $(`#${column_id}`).hide();
    $(`#${column_id}-filter`).show();
}

function get_table_filters(table_container_id) {
    var filters = [];
    $(`#${table_container_id} .multi-select`).each(function() {
        var selected = [];
        $(this).find("input.multi-select-check:checked").each(function() {
            selected.push($(this).val());
        });
        if (selected.length > 0) {
            filters[$(this).attr("field") + "_in"] = JSON.stringify(selected);
        }
    });
    return filters;
}

function get_table_sort(table_container_id) {
    var sort = {};
    $(`#${table_container_id} .sortable-col`).each(function() {
        var field_name = $(this).attr("field");
        if ($(this).attr("is-current-sort") === "true") {
            sort["sort_by"] = field_name;
            sort["sort_order"] = $(this).attr("sort-order");
        }
    });
    return sort;
}


function get_table_state(table_container_id) {
    var state = Object.assign({}, get_table_sort(table_container_id), get_table_filters(table_container_id));
    return state;
}

function table_page(url, table_container_id) {
    var state = get_table_state(table_container_id);

    $(`#${table_container_id} tbody`).children().remove();
    $(`#${table_container_id} ul.pagination`).children().remove();
    $(`#${table_container_id} .sort-btn`).prop("onclick", null).off("click");

    htmx.ajax("GET", url, {
        target: `#${table_container_id}`,
        swap: "outerHTML",
        values: state
    })
}

function table_sort(url, table_container_id, field) {
    var state = get_table_state(table_container_id);

    if (state["sort_by"] === field) {
        if (state["sort_order"] === "asc") {
            state["sort_order"] = "desc";
        } else {
            state["sort_order"] = "asc";
        }
    } else {
        state["sort_by"] = field;
        state["sort_order"] = "asc";
    }

    $(`#${table_container_id} tbody`).children().remove();
    $(`#${table_container_id} ul.pagination`).children().remove();
    $(`#${table_container_id} .sort-btn`).prop("onclick", null).off("click");

    htmx.ajax("GET", url, {
        target: `#${table_container_id}`,
        swap: "outerHTML",
        indicator: `#${table_container_id}-spinner`,
        values: state
    })
}

function table_filter(url, table_container_id) {
    var state = get_table_state(table_container_id);

    $(`#${table_container_id} tbody`).children().remove();
    $(`#${table_container_id} ul.pagination`).children().remove();
    $(`#${table_container_id} .sort-btn`).prop("onclick", null).off("click");

    htmx.ajax("GET", url, {
        target: `#${table_container_id}`,
        swap: "outerHTML",
        indicator: `#${table_container_id}-spinner`,
        values: state
    })
}

function table_query(url, table_container_id, field_name, word) {
    var state = get_table_filters(table_container_id);

    state[field_name] = word;

    $(`#${table_container_id} tbody`).children().remove();
    $(`#${table_container_id} ul.pagination`).children().remove();
    $(`#${table_container_id} .sort-btn`).prop("onclick", null).off("click");

    htmx.ajax("GET", url, {
        target: `#${table_container_id}`,
        swap: "outerHTML",
        indicator: `#${table_container_id}-spinner`,
        values: state
    })
}

function toggle_index_display(subset) {
    $(".index-badges-" + subset).each(function() {
        if ($(this).is(":hidden")) {
            $(this).show();
        } else {
            $(this).hide();
        }
    });
}