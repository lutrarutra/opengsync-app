/**
 * Orderings for the "name [id]" cells of a DBObjectColumn (components/tables/spreadsheet.py), offered in the
 * column's context menu: `{ type: "dropdown", sortings: jssObjectSortings }`. Empty cells stay last.
 */
window.jssObjectSortings = (() => {
    const parse = (value) => {
        const match = /^(.*) \[(\d+)\]$/.exec(String(value));
        return match ? { name: match[1], id: Number(match[2]) } : { name: String(value), id: null };
    };

    const sorting = (compare) => (direction) => (a, b) => {
        if (a[1] === "" || b[1] === "") {
            return (a[1] === "") - (b[1] === "");
        }
        const order = compare(parse(a[1]), parse(b[1]));
        return direction ? -order : order;
    };

    return [
        { title: "name", sorting: sorting((a, b) => a.name.localeCompare(b.name, undefined, { numeric: true })) },
        { title: "ID", sorting: sorting((a, b) => (a.id ?? Infinity) - (b.id ?? Infinity)) },
    ];
})();
