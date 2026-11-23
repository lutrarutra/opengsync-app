// Guided onboarding tour for customers (Driver.js). Progress is kept server-side (server/core/onboarding.py),
// so the tour can be paused and resumed later, also on another device.
//
// Three groups of steps:
//   dash.*     dashboard highlights, "Next" through them; the last one waits for a click on the create tile
//   form.*     while the request form (xl modal) is open: a hint card follows the form's own steps
//   request.*  on the page of the request just created: the submission checklist
// Elements are looked up through data-tour attributes or stable ids, and waited for: most of them are
// loaded by htmx after the page.
(function () {
    const configEl = document.getElementById("onboarding-config");
    if (!configEl || !window.driver || !window.driver.js) return;
    const config = JSON.parse(configEl.textContent);

    const CREATED_FLAG = "onboarding-created";
    const dashboardPath = new URL(config.dashboard_url, location.origin).pathname;
    const requestPath = new URL(config.seq_request_url, location.origin).pathname;
    const requestPattern = new RegExp("^" + requestPath.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace("/0", "/(\\d+)") + "/?$");

    function currentPage() {
        if (location.pathname === dashboardPath) return { name: "dash" };
        const match = location.pathname.match(requestPattern);
        if (match) return { name: "request", id: Number(match[1]) };
        return { name: null };
    }

    // ---- steps -------------------------------------------------------------------------------------

    function accordionItem(id) {
        return () => document.getElementById(id)?.closest(".accordion-item");
    }

    function expand(id) {
        return new Promise(resolve => {
            const el = document.getElementById(id);
            if (!el || el.classList.contains("show")) return resolve();
            el.addEventListener("shown.bs.collapse", () => resolve(), { once: true });
            bootstrap.Collapse.getOrCreateInstance(el).show();
            setTimeout(resolve, 800);
        });
    }

    const STEPS = [
        {
            id: "dash.welcome",
            title: "Welcome to OpeNGSync 👋",
            text: "This short tour shows you around and helps you create your first sequencing request. "
                + "You can pause it at any time and continue later with the <b>Tour</b> button on the dashboard.",
            nextText: "Start tour",
        },
        {
            id: "dash.nav_requests", element: '[data-tour="nav-requests"]', skipIfMissing: true,
            title: "Requests",
            text: "All your sequencing requests: drafts, submitted and completed ones.",
        },
        {
            id: "dash.nav_projects", element: '[data-tour="nav-projects"]', skipIfMissing: true,
            title: "Projects",
            text: "Projects group your samples. A project is created when you add samples to a request.",
        },
        {
            id: "dash.nav_groups", element: '[data-tour="nav-groups"]', skipIfMissing: true,
            title: "Groups",
            text: "Groups (e.g. your lab) let you share requests and projects with colleagues.",
        },
        {
            id: "dash.nav_help", element: '[data-tour="nav-help"]', skipIfMissing: true,
            title: "Help",
            text: "Guides and documentation, if you get stuck.",
        },
        {
            id: "dash.requests", element: '[data-tour="dash-seq-requests"]', side: "right",
            title: "Your recent requests",
            text: "Here you can see your most recent sequencing requests and their status at a glance.",
        },
        {
            id: "dash.projects", element: '[data-tour="dash-projects"]', side: "left",
            title: "Your recent projects",
            text: "Here you can see your projects, with the samples you sent us.",
        },
        {
            // only rendered when the chat feature is enabled (templates/components/chat/widget.html)
            id: "dash.chat", element: "#chat-toggle", side: "left", skipIfMissing: true,
            title: "Ask the assistant",
            text: "Have a question about how something works? Click ✨ to chat with our AI assistant. "
                + "It can't see your data, so don't enter personal or confidential information.",
        },
        {
            id: "dash.create", element: '[data-tour="create-seq-request"]', side: "left", action: "create",
            title: "Create your first request",
            text: "Let's create a request together. <b>Click the tile</b> to open the request form. "
                + "It is saved as a draft: nothing is sent to us until you submit it.",
        },
        {
            id: "form.request", form: true,
        },
        {
            id: "request.status", element: ".status_bar", side: "bottom",
            title: "Your new request",
            text: "Your request is created as a <b>draft</b>. The status bar shows where it is in the process.",
        },
        {
            id: "request.checklist", element: 'button[data-bs-target="#request-checklist-tab"]', side: "bottom",
            before: () => open_tab("request-checklist-tab"),
            title: "Submission checklist",
            text: "The checklist lists what is still needed before you can submit the request.",
        },
        {
            id: "request.samples", element: accordionItem("request-submit-accordion-1"), side: "top",
            before: () => { open_tab("request-checklist-tab"); return expand("request-submit-accordion-1"); },
            title: "1. Add samples",
            text: "Click <b>Begin</b> to add your samples or libraries. A workflow guides you through it, "
                + "and you can download and fill in a spreadsheet template.",
        },
        {
            id: "request.auth_form", element: accordionItem("request-submit-accordion-2"), side: "top",
            before: () => expand("request-submit-accordion-2"),
            title: "2. Authorization form",
            text: "Download the sequencing authorization form, have it signed, and upload it here.",
        },
        {
            id: "request.layout", element: accordionItem("request-submit-accordion-layout"), side: "top",
            before: () => expand("request-submit-accordion-layout"),
            title: "3. Submission layout",
            text: "Tell us how your tubes or plates are arranged, once your samples are added.",
        },
        {
            id: "request.share_emails", element: accordionItem("request-submit-accordion-share_emails"), side: "top",
            before: () => expand("request-submit-accordion-share_emails"),
            title: "4. Data share emails",
            text: "The data is shared with these email addresses when sequencing is done.",
        },
        {
            id: "request.submit", element: accordionItem("request-submit-accordion-3"), side: "top",
            before: () => expand("request-submit-accordion-3"),
            title: "5. Submit",
            text: "When everything above is complete, submit the request for review. We'll check it and get back to you.",
        },
        {
            id: "request.tabs", element: ".page-tabs", side: "bottom",
            title: "More about your request",
            text: "The other tabs show the request's samples, libraries, files, and more.",
        },
        {
            id: "request.comments", element: "#request-comments-tab-btn", side: "bottom",
            title: "Questions?",
            text: "Leave us a comment here, or attach files under <b>Files</b>.",
        },
        {
            id: "request.done",
            title: "You're all set 🎉",
            text: "Continue with the checklist whenever you're ready. If this was just practice, you can delete "
                + "the draft from the <b>Manage</b> menu. You can restart the tour from the dashboard at any time.",
            nextText: "Finish",
        },
    ];

    // Hints for the request form's own steps, by `data-step` of its visible pane.
    const FORM_HINTS = {
        disclaimer: "Read the disclaimer and accept it, then click <b>Next</b>.",
        submission: "What are you sending us? <b>Raw samples</b> for library prep, ready <b>pooled libraries</b>, "
            + "or samples for <b>QC only</b>.",
        basic_info: "Give the request a name you'll recognize, and optionally a description.",
        contact: "Who should we contact about this request? Your details are filled in where we have them; "
            + "complete the rest, including your principal investigator (PI).",
        technical_info: "Read type, read length and number of lanes. Not sure? Pick your best guess "
            + "and mention it under special requirements, we'll check it with you.",
        bioinformatician: "Optional: a bioinformatician we can contact about the data.",
        organization: "Your organization, filled in from your profile.",
        billing: "Billing details. When everything is filled in, click <b>Create</b>: the request is saved as a draft.",
    };

    const stepIndex = id => STEPS.findIndex(step => step.id === id);
    const groupOf = id => (id || "").split(".")[0];
    const CREATE_INDEX = stepIndex("dash.create");
    const FORM_INDEX = stepIndex("form.request");

    // ---- state -------------------------------------------------------------------------------------

    let state = { status: null, step: null, seq_request_id: null };

    function save(patch) {
        state = Object.assign({}, state, patch);
        return fetch(config.state_url, {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json", "X-CSRF-Token": getCookie("csrf_token") || "" },
            body: JSON.stringify({ status: state.status, step: state.step, seq_request_id: state.seq_request_id }),
        }).catch(() => {});
    }

    function toast(text) {
        Swal.fire({ toast: true, position: "top", icon: "info", text: text, timer: 4000, showConfirmButton: false, showCloseButton: true });
    }

    // ---- highlighting --------------------------------------------------------------------------------

    let drv = null;
    let current = -1;

    // Laid out and horizontally on screen: the mobile navbar is an off-canvas drawer
    function visible(el) {
        if (!el || el.getClientRects().length === 0) return false;
        if (el.checkVisibility && !el.checkVisibility({ visibilityProperty: true })) return false;
        const rect = el.getBoundingClientRect();
        return rect.width > 0 && rect.right > 0 && rect.left < window.innerWidth;
    }

    function resolve(element) {
        return typeof element === "function" ? element() : document.querySelector(element);
    }

    // Elements loaded by htmx may not be there yet: poll for a short while.
    function waitFor(element, timeout = 5000) {
        return new Promise(done => {
            const started = Date.now();
            (function poll() {
                const el = resolve(element);
                if (visible(el)) return done(el);
                if (Date.now() - started > timeout) return done(null);
                setTimeout(poll, 100);
            })();
        });
    }

    function makeButton(text, cls, onClick) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = cls;
        button.textContent = text;
        button.addEventListener("click", onClick);
        return button;
    }

    function getDriver() {
        if (drv) return drv;
        drv = window.driver.js.driver({
            allowClose: false,              // Esc is handled below (pause); a click on the overlay does nothing
            overlayOpacity: 0.55,
            stagePadding: 6,
            popoverClass: "onboarding-popover",
            showButtons: ["next", "previous"],
            onNextClick: () => next(),
            onPrevClick: () => go(current - 1, -1),
            onPopoverRender: (popover) => {
                const step = STEPS[current];
                // highlight() (single-step mode) hides the footer: we drive the steps ourselves
                popover.footer.style.display = "flex";
                popover.progress.textContent = `${current + 1} / ${STEPS.length}`;
                popover.progress.style.display = "block";
                popover.previousButton.textContent = "Back";
                popover.nextButton.textContent = step.nextText || "Next";
                if (step.action) popover.nextButton.style.display = "none";
                // No way back into the form (or before the first step)
                if (current === 0 || STEPS[current - 1].form) popover.previousButton.style.display = "none";

                const extra = document.createElement("span");
                extra.className = "onboarding-popover-extra";
                if (step.id === "dash.welcome") {
                    extra.append(
                        makeButton("Skip", "onboarding-link", skip),
                        makeButton("Later", "onboarding-link", pause),
                    );
                } else if (step.id !== "request.done") {
                    extra.append(
                        makeButton("Skip tour", "onboarding-link", skip),
                        makeButton("Pause", "onboarding-link", pause),
                    );
                }
                popover.footer.prepend(extra);
            },
        });
        return drv;
    }

    function stopDriver() {
        if (drv && drv.isActive()) drv.destroy();
        drv = null;
    }

    // Show step `i`; steps whose element is hidden (e.g. the collapsed navbar on mobile) are skipped
    // in the direction we're moving.
    async function go(i, direction = 1) {
        if (i < 0 || i >= STEPS.length) return;
        const step = STEPS[i];
        if (step.form) return startForm();
        current = i;
        setFabVisible(false);
        save({ status: "IN_PROGRESS", step: step.id });

        if (step.before) await step.before();
        let el = null;
        if (step.element) {
            el = await waitFor(step.element, step.skipIfMissing ? 300 : 5000);
            if (current !== i) return;      // moved on while waiting
            if (!el && step.skipIfMissing) return go(i + direction, direction);
        }

        getDriver().highlight({
            element: el || undefined,
            popover: { title: step.title, description: step.text, side: step.side, align: "start" },
        });
        if (step.action === "create" && el) {
            el.addEventListener("click", () => startForm(), { once: true });
        }
    }

    function next() {
        if (STEPS[current].id === "request.done") return complete();
        go(current + 1, 1);
    }

    function pause() {
        stopDriver();
        unmountCoach();
        // An abandoned form can't be restored, resume at the create tile
        const step = groupOf(state.step) === "form" ? STEPS[CREATE_INDEX].id : state.step;
        save({ status: "PAUSED", step: step });
        toast("Tour paused. Continue anytime with the Tour button on the dashboard.");
        setFabVisible(true);
    }

    function skip() {
        stopDriver();
        unmountCoach();
        save({ status: "SKIPPED", step: null, seq_request_id: null });
        toast("Tour skipped. You can start it again from the dashboard.");
        setFabVisible(true);
    }

    function complete() {
        stopDriver();
        save({ status: "COMPLETED", step: null, seq_request_id: null });
        Swal.fire({ toast: true, position: "top", icon: "success", text: "Tour completed!", timer: 3000, showConfirmButton: false });
    }

    document.addEventListener("keydown", event => {
        if (event.key === "Escape" && (drv?.isActive() || coach)) pause();
    });

    // ---- request form ----------------------------------------------------------------------------------
    // The form swaps its whole container on every Next, so instead of highlighting inside it, a hint banner
    // is (re-)inserted under the modal header and follows whichever form step is visible.

    let coach = null;
    let observer = null;

    function startForm() {
        stopDriver();
        current = FORM_INDEX;
        sessionStorage.removeItem(CREATED_FLAG);
        save({ status: "IN_PROGRESS", step: STEPS[FORM_INDEX].id });
        waitFor("#xl-modal-content #seq_request-form", 10000).then(form => {
            if (form && current === FORM_INDEX) mountCoach();
        });
    }

    function mountCoach() {
        coach = document.createElement("aside");
        coach.className = "onboarding-coach";
        coach.setAttribute("role", "status");
        coach.innerHTML = `
            <div class="onboarding-coach-header">
                <i class="bi bi-signpost-2"></i>
                <b class="onboarding-coach-title"></b>
                <span class="onboarding-coach-progress"></span>
                <span class="onboarding-coach-actions"></span>
            </div>
            <p class="onboarding-coach-text"></p>
            <p class="onboarding-coach-error" hidden>Some fields of this step need attention, see the messages in red.</p>`;
        coach.querySelector(".onboarding-coach-actions").append(
            makeButton("Skip tour", "onboarding-link", skip),
            makeButton("Pause", "onboarding-link", pause),
        );

        const content = document.getElementById("xl-modal-content");
        observer = new MutationObserver(updateCoach);
        observer.observe(content, { subtree: true, childList: true, attributes: true, attributeFilter: ["class"] });
        updateCoach();
    }

    function setText(el, text) {
        if (el.textContent !== text) el.textContent = text;
    }

    function updateCoach() {
        if (!coach) return;
        const container = document.getElementById("seq_request-form-container");
        if (!container) return;
        if (coach.parentElement !== container) {
            container.insertBefore(coach, container.querySelector(".modal-body"));
        }
        const pane = document.querySelector("#seq_request-form .step-pane:not(.d-none)");
        if (!pane) return;
        const panes = document.querySelectorAll("#seq_request-form .step-pane");
        const hint = FORM_HINTS[pane.dataset.step] || "Fill in this step, then click <b>Next</b>.";
        // The banner is inside the observed subtree: only write what changed, or the observer loops
        setText(coach.querySelector(".onboarding-coach-title"), pane.dataset.title);
        setText(coach.querySelector(".onboarding-coach-progress"), `${Array.from(panes).indexOf(pane) + 1} / ${panes.length}`);
        const text = coach.querySelector(".onboarding-coach-text");
        if (text.dataset.step !== pane.dataset.step) {
            text.innerHTML = hint;
            text.dataset.step = pane.dataset.step;
        }
        const error = coach.querySelector(".onboarding-coach-error");
        const hasErrors = !!document.querySelector("#seq_request-timeline .step-timeline-item.current.step-error");
        if (error.hidden === hasErrors) error.hidden = !hasErrors;

        const button = ["seq_request-step-next", "seq_request-submit"]
            .map(id => document.getElementById(id))
            .find(el => el && !el.classList.contains("d-none"));
        document.querySelectorAll(".onboarding-pulse").forEach(el => {
            if (el !== button) el.classList.remove("onboarding-pulse");
        });
        if (button && !button.classList.contains("onboarding-pulse")) button.classList.add("onboarding-pulse");
    }

    function unmountCoach() {
        if (observer) observer.disconnect();
        observer = null;
        if (coach) coach.remove();
        coach = null;
        document.querySelectorAll(".onboarding-pulse").forEach(el => el.classList.remove("onboarding-pulse"));
    }

    // Create answers with HX-Redirect to the new request's page; remember that in this tab so the
    // request steps continue there (and not on any other request page the user opens later).
    document.body.addEventListener("htmx:afterRequest", event => {
        if (!coach || event.detail.elt?.id !== "seq_request-submit") return;
        if (event.detail.xhr?.getResponseHeader("HX-Redirect")) {
            sessionStorage.setItem(CREATED_FLAG, "1");
        }
    });

    document.getElementById("xl-modal")?.addEventListener("hidden.bs.modal", () => {
        if (coach && !sessionStorage.getItem(CREATED_FLAG)) pause();
    });

    // ---- floating button (customer dashboard) ------------------------------------------------------------

    const fab = document.getElementById("onboarding-fab");

    function setFabVisible(show) {
        if (!fab) return;
        fab.hidden = !show;
        const resumable = ["IN_PROGRESS", "PAUSED"].includes(state.status) && state.step;
        const label = fab.querySelector(".onboarding-fab-label");
        if (resumable) {
            const i = Math.max(stepIndex(state.step), 0);
            label.textContent = `Resume tour (${i + 1}/${STEPS.length})`;
        } else {
            label.textContent = "Start tour";
        }
        fab.setAttribute("aria-label", label.textContent);
    }

    function resume() {
        const group = groupOf(state.step);
        if (group === "request" && state.seq_request_id) {
            save({ status: "IN_PROGRESS" }).then(() => {
                location.href = requestPath.replace("/0", "/" + state.seq_request_id);
            });
            return;
        }
        if (group === "form") return go(CREATE_INDEX);
        const i = stepIndex(state.step);
        go(i >= 0 && group === "dash" ? i : 0);
    }

    fab?.addEventListener("click", () => {
        const resumable = ["IN_PROGRESS", "PAUSED"].includes(state.status) && state.step;
        if (resumable) resume();
        else go(0);
    });

    // ---- boot ----------------------------------------------------------------------------------------------

    function boot() {
        const page = currentPage();
        const group = groupOf(state.step);

        if (page.name === "dash") {
            if (state.status === "NEW") return go(0);
            if (state.status === "IN_PROGRESS" && group === "dash") return go(Math.max(stepIndex(state.step), 0));
            if (state.status === "IN_PROGRESS" && group === "form") return go(CREATE_INDEX);
            return setFabVisible(true);
        }

        if (page.name === "request" && state.status === "IN_PROGRESS") {
            if (group === "form" && sessionStorage.getItem(CREATED_FLAG)) {
                sessionStorage.removeItem(CREATED_FLAG);
                state.seq_request_id = page.id;
                return go(FORM_INDEX + 1);
            }
            if (group === "request" && state.seq_request_id === page.id) {
                return go(Math.max(stepIndex(state.step), FORM_INDEX + 1));
            }
        }
    }

    fetch(config.state_url, { credentials: "same-origin" })
        .then(response => response.ok ? response.json() : null)
        .then(data => {
            if (data) state = Object.assign(state, data);
            boot();
        })
        .catch(() => setFabVisible(true));
})();
