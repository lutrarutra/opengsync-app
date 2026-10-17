/**
 * Dialog for the texts the spreadsheet context menu asks for (the `prompt` option of the jspreadsheet fork): the name
 * of a new or renamed column and cell comments. Resolves to the text, or null when cancelled.
 */
window.jssPrompt = (() => {
    const DIALOGS = {
        insertColumn: { title: "New column", confirm: "Insert" },
        renameColumn: { title: "Rename column", confirm: "Rename" },
        comments: { title: "Comment", confirm: "Save", input: "textarea" },
    };

    const normalize = (name) => name.trim().toLowerCase();

    // Column names must be unique, the backend maps the columns by name
    const validateColumnName = (worksheet, request, value) => {
        const name = normalize(value);
        if (!name) {
            return "Enter a column name.";
        }
        const others = worksheet.getHeaders(true).filter((_, x) => request.action === "insertColumn" || x !== request.x);
        if (others.some((header) => normalize(header) === name)) {
            return "A column with this name already exists.";
        }
        return null;
    };

    return (worksheet, request) => {
        const dialog = DIALOGS[request.action] || { title: request.message, confirm: "OK" };
        const isColumn = request.action === "insertColumn" || request.action === "renameColumn";
        return Swal.fire({
            // In a Bootstrap modal, which would take the focus back from a dialog outside of it
            target: worksheet.element.closest(".modal") || "body",
            titleText: dialog.title,
            input: dialog.input || "text",
            inputPlaceholder: request.message,
            inputValue: request.value || "",
            inputAttributes: { autocomplete: "off", spellcheck: "false" },
            showCancelButton: true,
            confirmButtonText: dialog.confirm,
            // Typing replaces the current text
            didOpen: () => Swal.getInput().select(),
            inputValidator: isColumn ? (value) => validateColumnName(worksheet, request, value) : undefined,
        }).then((result) => (result.isConfirmed ? result.value.trim() : null));
    };
})();
