let searchTimer;

function update_search_bar(option) {
    let $container = option.closest(".multiple-select");
    let $search_bar = $container.find(".option-search").first();

    let $selected_container = $container.find(".selected-container").first();
    $selected_container.empty();
    // loop through all options and concatenate the text of the checked ones
    $container.find(".options-container .option").each(function() {
        let $checkbox = $(this).find('input[type="checkbox"]');
        if ($checkbox.prop("checked")) {
            $selected_container.append(`<span class="badge" data-id="${$checkbox.attr("id")}">${$(this).find("label .label-name").text()}</span>`);
        }
    });

    // if it's empty, add a placeholder
    if ($selected_container.children().length === 0) {
        $selected_container.append(`Select..`);
    }
}

$(document).on("click", ".multiple-select .dropdown-toggle", function(e) {
    e.stopPropagation();

    let container = $(this).closest('.multiple-select');    
    container.toggleClass("active");
    
    if (container.hasClass("active")) {
        container.find('.option-search').first().focus();
    }
});

$(document).on("click", ".options-container .option", function() {
    let $option = $(this);
    $checkbox = $option.find('input[type="checkbox"]').prop("checked", function(i, value) {
        return !value;
    });

    // uncheck select all when not all are selected
    let $container = $option.closest('.multiple-select');
    let totalOptions = $container.find('.options-container .option').length;
    let checkedOptions = $container.find('.options-container .option input[type="checkbox"]:checked').length;
    $container.find('.select-all').prop("checked", totalOptions === checkedOptions);
    update_search_bar($option);
});

$(document).on("click", function(e) {
    if (!$(e.target).closest(".multiple-select").length) {
        $(".multiple-select").removeClass("active");
    }
});

$(document).on("click", ".options-container", function(e) {
    e.stopPropagation();
});

$(document).on("click", ".select-all", function() {
    let $container = $(this).closest('.multiple-select');
    let isChecked = $(this).prop("checked");
    $container.find('.options-container .option input[type="checkbox"]').prop("checked", isChecked);
    update_search_bar($(this));
});

$(document).on("input", ".option-search", function() {
    let $input = $(this);
    let searchTerm = $input.val().toLowerCase();
    let $container = $input.closest('.multiple-select');
    let $options = $container.find('.options-container .option');

    $container.toggleClass("active", true);

    // Clear the previous timer if the user is still typing
    clearTimeout(searchTimer);

    // Set a new timer (e.g., 300ms delay)
    searchTimer = setTimeout(function() {
        $options.each(function() {
            // Get the text from the label (includes label text and span.desc)
            let text = $(this).find('label').text().toLowerCase();
            
            if (text.indexOf(searchTerm) > -1) {
                $(this).show(); // Match found
            } else {
                $(this).hide(); // No match
            }
        });
    }, 300); // 300ms is usually the "sweet spot" for UX
});
