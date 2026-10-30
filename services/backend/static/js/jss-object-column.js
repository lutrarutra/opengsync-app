/**
 * Context menu orderings for DBObjectColumn and QueryColumn. Empty cells stay last.
 */
(() => {
    const parse = (value) => {
        const match = /^(.*) \[(\d+)\]$/.exec(String(value));
        return match ? { name: match[1], id: Number(match[2]) } : { name: String(value), id: null };
    };

    const sorting = (compare, isEmpty = (entry) => entry[1] === "") => (direction) => (a, b) => {
        if (isEmpty(a) || isEmpty(b)) {
            return isEmpty(a) - isEmpty(b);
        }
        const order = compare(a, b);
        return direction ? -order : order;
    };

    const byId = (getId) => sorting((a, b) => {
        const idA = getId(a[2]) ?? Infinity;
        const idB = getId(b[2]) ?? Infinity;
        return idA > idB ? 1 : idA < idB ? -1 : 0;
    }, (entry) => entry[2] === "" || entry[2] === null || entry[2] === undefined);
    const objectId = (value) => {
        const match = typeof value === "string" && /(?:^| )\[(\d+)\]$/.exec(value);
        return match ? Number(match[1]) : null;
    };
    const queryId = (value) => typeof value === "number" && Number.isFinite(value) ? value : null;

    window.jssObjectSortings = [
        { title: "name", sorting: sorting((a, b) => parse(a[1]).name.localeCompare(parse(b[1]).name, undefined, { numeric: true })) },
        { title: "ID", sorting: byId(objectId) },
    ];
    window.jssQuerySortings = [
        { title: "name", sorting: sorting((a, b) => a[1] > b[1] ? 1 : a[1] < b[1] ? -1 : 0) },
        { title: "ID", sorting: byId(queryId) },
    ];
})();
