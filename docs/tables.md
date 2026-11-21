# Tables

How the paged tables in opengsync work (libraries, samples, requests, pools, users, kits, …): what the search box understands, how filters and entity filters work and which objects they offer, how a table keeps its state in the address bar, where row actions live, and how to add or change a table.

- [Using a table](#using-a-table)
- [Search syntax](#search-syntax)
- [Filters](#filters)
- [Address bar and shared links](#address-bar-and-shared-links)
- [Row actions](#row-actions)
- [How it works](#how-it-works)
- [Adding or changing a table](#adding-or-changing-a-table)
- [Tests](#tests)
- [Code](#code)

## Using a table

Every table has the same parts:

- **Search box**: one box for the whole table. The *All fields* dropdown in front of it restricts the search to one field.
- **Filter**: a panel with one tab per filterable field. Ticked values apply when the panel closes (or with *Apply*). The funnel in a column header opens the panel on that column's tab. Entity filters (owner, request, …) have a search box and load more options as you scroll.
- **Chips**: a row under the toolbar (only while something is active) shows each filter as a chip (`Status is 🧪 Pooled, ✅ Sequenced`). The × removes it, *Clear all* removes the search and every filter.
- **Buttons** for the table (e.g. *Add Assignee*, *Properties*) sit at the end of its toolbar; tables in tabs have no separate heading, the tab names them.
- **Headers**: click to sort ascending, again for descending, a third time to go back to the default order.
- **Column widths** come from the table's definition, not from the rows, so they stay the same on every page; long values end in "…" and show in full on hover. On narrow screens the table scrolls sideways.
- **Resizing columns**: drag the right edge of a column header (or focus it and use the arrow keys). Widths are remembered per table in this browser; double-click the edge or use *Reset column widths* in the Columns menu to go back to automatic widths.
- **Columns**: hide columns you don't need. This and the barcode display (*Name* | *Seq* in the Index header) are remembered per browser.
- **Footer**: the shown range, rows per page (*Auto* fits the screen) and the pages.
- **⋯** at the end of a row: everything you can do with the row (remove, re-sequence, email, …).
- **Right-click** on a name or barcode: copy it, or *Copy column* (every value of that column on the page, one per line).

## Search syntax

| You type | Matches |
|---|---|
| `pbmc` | any searchable field: names, and for most tables also owner, group, project, request, … |
| `pbmc d04` | rows matching **both** terms (each in any field) |
| `"liver organoid"` | the phrase, spaces included |
| `owner:chen` | only that field (the field names are the ones in the *All fields* dropdown, e.g. `owner`, `group`, `project`, `request`, `pool`, `index`) |
| `group:"Immuno Lab"` | a field with a quoted value |
| `#1291` or `1291` | the row with exactly that id first, then rows whose names etc. contain the digits; `id:1291` for the id only. Pools also take `P1291`, requests `BSR_1291` |
| `status:pooled` | a filterable field by the start of its label (`status:seq` finds *Sequenced*) |
| `index:SI-TT-B4` or `index:GTCAGG` | libraries by barcode name or sequence |

Matching is case-insensitive, and the search terms are highlighted in the visible cells. Matches are **literal** first (exact, starts with, contains). Only when nothing matches literally, the table's own names are searched with typo tolerance and a note says *No exact matches, showing similar …*. Joined fields (owner, group, project, …) only ever match literally.

Without a column sort, results come by relevance: exact matches first, then names that start with the term, then names that contain it. Clicking a column header sorts by that column instead.

## Filters

**Value filters** list every value of a field (statuses, types, roles, …). Several ticked values of one field are OR-ed, different fields are AND-ed, and filters combine with the search.

**Entity filters** filter by related objects: libraries by their owner, request, pool, project or group, samples by project or owner, requests and projects by their assignees, requests by requestor or group, and so on. Type a name in the filter tab and tick one or more of the listed objects.

What an entity filter offers is restricted twice:

1. Only objects that **occur in the rows you can see** in that table (the owners of the libraries listed on this page context, not every user).
2. Only objects **you may see yourself** (`server/components/tables/visibility.py`):

| Viewer | Users | Groups | Requests, projects, pools, samples, libraries, files | Experiments, lab preps, sequencers, … |
|---|---|---|---|---|
| Staff (insiders) | all | all | all | all |
| Customers | themselves and members of their groups | their groups | what they have read access to (own and their groups') | not offered |

Exception: assignees (staff) are offered when they are assigned to a row you can see, since their badges show on those rows anyway (`Entity(..., from_rows=True)`); ids from the address bar are then checked against those rows.

An id in the address bar that you may not see (e.g. a pasted link with someone else's owner) is dropped silently: no chip, no name on the page, and the table is not filtered by it.

## Address bar and shared links

Each table writes its state into the address bar under its own prefix, so a reload or a copied link shows the same view, and two tables on one page (e.g. a request's samples and libraries) don't collide:

```
/seq_requests/388?lib.q=owner:chen&lib.status_in=5,6&lib.order_by=name:asc&lib.page=2&smp.q=d01#request-libraries-tab
```

| Parameter | Meaning |
|---|---|
| `<key>.q` | search box |
| `<key>.scope` | the *All fields* dropdown |
| `<key>.order_by` | `<field>:asc` or `<field>:desc` |
| `<key>.<field>_in` | filter values (enum ids or object ids), comma separated |
| `<key>.page` | page, starting at 1 |

- Only non-default values are written; the open tab stays in the `#hash`.
- The address bar is updated in place (`history.replaceState`): searching, sorting and paging don't add *Back* steps.
- Rows per page are not part of the link (they depend on the screen), nor are hidden columns.
- Unknown fields, bad values and pages past the end are ignored or clamped, so old or hand-edited links always open.
- Tables inside forms (the *browse* tables of workflows) don't write the address bar.

Table keys: `lib` libraries, `smp` samples, `pool` pools, `req` requests, `prj` projects, `exp` experiments, `prep` lab preps, `user` users, `asg` assignees, `grp` groups, `aff` affiliations, `tok` API tokens, `share` share tokens, `kit` kits, `ikit` index kits, `fkit` feature kits, `feat` features, `adapt` adapters, `prot` protocols, `seqr` sequencers, `run` sequencing runs, `lane` lanes, `dil` dilutions, `file` files, and on the admin pages `ashare` share links and `aaff_<kind>` affiliation values.

## Row actions

Everything that changes data lives in the row's **⋯ menu**: *Remove Library*, *Re-Sequence Library*, *Remove Sample*, *Remove Assignee*, *Send Email*, *Delete File*, *Deactivate*, *Expire*, … Actions that need confirmation ask first. After an action the table re-renders with the same search, filters, sort and page.

**Right-click** menus in tables only copy (cell value, *Copy column*, a barcode's adapter name or i7/i5 sequence). Shift+right-click opens the browser's own menu; Shift+F10 or the context-menu key opens the menu of the focused ⋯ button or cell.

## How it works

1. A page contains a loader (`<div data-table-loader="lib" hx-get="…/render-table-page?seq_request_id=…">`). On its first request, `static/js/table.js` adds the table's `lib.*` parameters from the address bar (without the prefix) and the page size that fits the screen.
2. The route checks permissions, builds the base statement for its context (e.g. the libraries of one request, or for customers only what they may see) and calls `Table.render`.
3. `Table.render` (`server/components/tables/table.py`) validates the filters (`state.py`, `visibility.py`), applies the search (`query.py`), sorts, pages and renders `templates/components/tables/_table.html`. That shared template draws toolbar, chips, header, footer and empty states and includes the variant's **row template** (`templates/components/tables/rows/*.html`) for the `<tr>`s.
4. The toolbar is a `<form>`: searching (300 ms after the last keystroke), sorting, paging and filtering submit it, and htmx swaps the whole table. The search box keeps its focus (`hx-preserve`); during a request the rows are dimmed under a thin progress bar.
5. After every swap, `table.js` writes the table's state (the server renders it into `data-url-state`) into the address bar and re-applies hidden columns, resized column widths and the barcode display.
6. A successful request started from inside a table that isn't its own form (a ⋯ action, a button in a row) re-renders the table with its current state.
7. With `?options=<field>&word=…` the same route answers with the options of an entity filter (JSON, like the searchable input fields) instead of HTML. It goes through the same permission checks and base statement, so options can't reach beyond what the table shows.

Search ranking reuses the tiers of the navbar search (`opengsync_db/queries/search.py`). Conditions on related objects (owner, group, project, …) are correlated `EXISTS` (`rel.has()` / `rel.any()`), so a library with two samples in the same project is still one row and counted once.

## Adding or changing a table

A table is a `Table` subclass next to its route. Libraries (`server/routes/htmx/libraries.py`) are the reference:

```python
class LibraryTable(Table):
    key = "lib"                         # address bar prefix, unique
    model = models.Library
    noun = "libraries"                  # counts and empty states
    load = (orm.selectinload(L.pool), ...)
    columns = [
        Col("id", "ID", sort=True, search=Exact(L.id), hideable=False),
        Col("name", "Name", sort=True, search=Text(L.name, L.sample_name, compact=True)),
        Col("status", "Status", sort=True, filter=Enum(C.LibraryStatus)),
        Col("owner", "Owner", sort=related(L.owner, full_name(User)),
            search=Text(full_name(User), User.email, via=L.owner),
            filter=Entity(models.User, via=L.owner, option=query_options.user_option, search=(full_name(User),))),
        Field("group", "Group", search=Text(Group.name, via=(L.seq_request, SeqRequest.group)), ...),
    ]
    variants = {
        "default": Variant(["id", "name", "status"], "components/tables/rows/library.html", dom_id="library-table"),
        "seq_request": Variant([...], "components/tables/rows/seq_request-library.html", actions=True, ...),
        "browse": Variant([...], ..., url_state=False),
    }


@router.get("/render-table-page")
def render_library_table(seq_request_id: int | None = None, state: TableState = Depends(LibraryTable.params), ...):
    stmt = Q.library.select(seq_request_id=seq_request_id)
    table = LibraryTable(state, route="render_library_table", user=current_user)
    if seq_request_id is not None:
        ...  # permission check
        table.use("seq_request", seq_request_id=seq_request_id, seq_request=seq_request)
    elif not current_user.is_insider:
        stmt = Q.library.select(viewer_id=current_user.id, statement=stmt)
    return table.render(session, stmt)
```

| Building block | Use |
|---|---|
| `Col(key, title, sort=…, search=…, filter=…, size=1)` | a column. `sort=True` sorts by `model.<key>`, or pass an expression (`related(rel, column)` for a column of a many-to-one relation). `size` is its width weight among the shown columns (raised automatically so the header fits) |
| `Field(key, title, search=…, filter=…)` | searchable/filterable but never shown (e.g. `group`) |
| `Text(*columns, via=path, compact=False, weight=1.0)` | text search; `via` is a relationship path from the table's model |
| `Exact(column, prefixes=("P",))` | id search |
| `Enum(enum, column=None, via=(), choices=None, nullable=False)` | value filter |
| `Entity(model, via, option, search=(), from_rows=False)` | entity filter; `option` is a `query_options.*_option` function. `from_rows=True`: offer and accept exactly the objects that occur in the visible rows instead of `visibility.py`'s rule (assignees) |
| `Variant(columns, row_template, dom_id=None, actions=False, url_state=True, fields=None, toolbar=None, prelude=None)` | one way to show the table, usually per page context. `toolbar`: a template with buttons at the end of the toolbar; `prelude`: a template shown above the card (e.g. the flow cell capacity of an experiment's pools) |
| `table.use(variant, **params)` | picks a variant: plain values become context query parameters kept on every request, objects become template context |

Checklist:

1. Spec and route as above. The route keeps its context parameters and permission checks, and scopes the base statement for customers.
2. A row template in `templates/components/tables/rows/` that renders `{% for x in rows %}<tr>…</tr>{% endfor %}` with one cell per variant column, in order. Copy actions go in `context_menu([...])` on the cell; every other action in `row_menu([...])` as the last cell (and `actions=True` on the variant).
3. Status cells show `{{ status.icon }} {{ status.label }}`.
4. The page loader gets `data-table-loader="<key>"`.
5. A new entity filter on a new kind of object needs a rule in `visibility.py`.
6. Run the tests below.

## Tests

| Test | Guards |
|---|---|
| `tests/server/test_table_wiring.py` | every table route found; keys unique; every sort, search and filter works in SQL; variants consistent |
| `tests/server/test_table_query_parser.py` | search box syntax, lenient state parsing |
| `tests/server/test_table_joined_search.py` | owner/group/project search, one row per library, relevance, empty states |
| `tests/server/test_table_entity_filters.py` | entity filter options and ids respect access rights |
| `tests/server/test_table_row_menu.py` | right-click menus in tables only copy; ⋯ menus have an actions column |
| `tests/server/test_table_search_filters.py`, `test_table_sort.py` | search, filters and sorts of every table |
| `services/backend/tests/table-url-state.test.js` | address bar prefixes (`node --test services/backend/tests/*.test.js`) |

For a manual check in a browser, `scripts/dev_seed_tables.py` seeds the dev database with QA users (password `devpassword`) and a group whose members must see each other's requests while an outsider's stay hidden.

## Code

| What | Where |
|---|---|
| Spec building blocks | `services/backend/server/components/tables/spec.py` |
| `Table`: filters, search, sort, paging, options, template helpers | `services/backend/server/components/tables/table.py` |
| State parsing | `services/backend/server/components/tables/state.py` |
| Search box | `services/backend/server/components/tables/query.py` |
| Entity filter access rules | `services/backend/server/components/tables/visibility.py` |
| Shared layout | `services/backend/templates/components/tables/_table.html` |
| Row templates | `services/backend/templates/components/tables/rows/` |
| ⋯ menu macro | `row_menu` in `services/backend/templates/components/contextmenu.jinja2` |
| Browser side | `services/backend/static/js/table.js`, menus in `static/js/contextmenu.js`, styles in `static/style/table.css` |
| Ranking tiers | `packages/opengsync-db/opengsync_db/queries/search.py` |
