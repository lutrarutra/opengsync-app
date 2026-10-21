// Floating assistant chat widget (see templates/components/chat/widget.html)
(function () {
    const widget = document.getElementById("chat-widget");
    if (!widget) return;

    const CONVERSATION_URL = widget.dataset.conversationUrl;
    const STORAGE_OPEN = "chat:open";
    const CONSENT_COOKIE = "chat_consent";
    const CONSENT_MAX_AGE = 60 * 60 * 24 * 365;  // 1 year

    const toggle = document.getElementById("chat-toggle");
    const panel = document.getElementById("chat-panel");
    const messages = document.getElementById("chat-messages");
    const form = document.getElementById("chat-form");
    const input = document.getElementById("chat-input");
    const send = document.getElementById("chat-send");
    const consent = document.getElementById("chat-consent");

    document.getElementById("chat-page-path").value = window.location.pathname;

    let loaded = false;
    let streaming = false;

    function storageGet(key) {
        try { return localStorage.getItem(key); } catch (e) { return null; }
    }

    function storageSet(key, value) {
        try {
            if (value === null) localStorage.removeItem(key);
            else localStorage.setItem(key, value);
        } catch (e) { /* storage unavailable */ }
    }

    function csrfHeaders() {
        return { "X-CSRF-Token": getCookie("csrf_token") || "" };
    }

    // Follow new output while the user is at the bottom; scrolling up pauses it until they scroll back down.
    // Tracked on scroll instead of checked after each swap: one SSE message re-renders the whole reply and can
    // grow it by more than any threshold, which would otherwise unstick the view mid-stream.
    let stickToBottom = true;

    function isAtBottom() {
        return messages.scrollHeight - messages.scrollTop - messages.clientHeight < 24;
    }

    function scrollToBottom(force = false) {
        if (!force && !stickToBottom) return;
        messages.scrollTop = messages.scrollHeight;
        stickToBottom = true;
    }

    messages.addEventListener("scroll", () => { stickToBottom = isAtBottom(); }, { passive: true });

    // Catches every content change (SSE swaps, new turns, async rendering) without wiring each event
    new MutationObserver(() => scrollToBottom()).observe(messages, {
        childList: true, subtree: true, characterData: true,
    });

    function setStreaming(value) {
        streaming = value;
        send.disabled = value;
        widget.classList.toggle("chat-is-streaming", value);
    }

    function showError(text) {
        const div = document.createElement("div");
        div.className = "chat-msg chat-msg-assistant";
        div.innerHTML = `<div class="chat-bubble chat-error"><i class="bi bi-exclamation-triangle"></i> </div>`;
        div.querySelector(".chat-bubble").append(text);
        messages.appendChild(div);
        scrollToBottom(true);
    }

    // ---------- conversation ----------

    function loadConversation() {
        return htmx.ajax("GET", CONVERSATION_URL, {
            target: messages, swap: "innerHTML", headers: csrfHeaders(),
        }).then(() => {
            loaded = true;
            if (messages.querySelector(".chat-streaming")) setStreaming(true);
            scrollToBottom(true);
        });
    }

    // ---------- open / close ----------

    // ---------- consent ----------

    function hasConsent() {
        return getCookie(CONSENT_COOKIE) === "1";
    }

    function showConsent(show) {
        consent.hidden = !show;
        messages.hidden = show;
        form.hidden = show;
    }

    document.getElementById("chat-consent-accept").addEventListener("click", () => {
        const secure = window.location.protocol === "https:" ? "; Secure" : "";
        document.cookie = `${CONSENT_COOKIE}=1; Max-Age=${CONSENT_MAX_AGE}; Path=/; SameSite=Lax${secure}`;
        showConsent(false);
        loadConversation();
        input.focus();
    });

    document.getElementById("chat-consent-decline").addEventListener("click", () => {
        close();
        toggle.focus();
    });

    // ---------- open / close ----------

    function open() {
        panel.hidden = false;
        widget.classList.add("chat-open");
        toggle.setAttribute("aria-expanded", "true");
        toggle.setAttribute("aria-label", "Close assistant chat");
        if (!hasConsent()) {
            showConsent(true);
            setTimeout(() => document.getElementById("chat-consent-accept").focus(), 50);
            return;  // not remembered as open, so the notice doesn't pop up on every page
        }
        showConsent(false);
        storageSet(STORAGE_OPEN, "1");
        if (!loaded) loadConversation();
        else scrollToBottom();  // output may have arrived while the panel was closed
        setTimeout(() => input.focus(), 50);
    }

    function close() {
        panel.hidden = true;
        widget.classList.remove("chat-open");
        toggle.setAttribute("aria-expanded", "false");
        toggle.setAttribute("aria-label", "Open assistant chat");
        storageSet(STORAGE_OPEN, null);
    }

    toggle.addEventListener("click", () => (panel.hidden ? open() : close()));
    document.getElementById("chat-close").addEventListener("click", close);

    panel.addEventListener("keydown", (e) => {
        if (e.key === "Escape") {
            close();
            toggle.focus();
        }
    });

    // ---------- htmx integration ----------

    // The form or workflow step open in a modal, as the URL path it submits to (the server maps it to a route pattern)
    function openFormPath() {
        const modals = document.querySelectorAll(".modal.show");
        const modal = modals[modals.length - 1];
        // data-submit-url marks forms that submit from JavaScript (e.g. spreadsheet steps) instead of hx-post
        const target = modal?.querySelector("[data-submit-url]") || modal?.querySelector("[hx-post], [hx-put], [hx-patch]");
        const url = target && (
            target.getAttribute("data-submit-url") || target.getAttribute("hx-post")
            || target.getAttribute("hx-put") || target.getAttribute("hx-patch")
        );
        if (!url) return "";
        try {
            return new URL(url, window.location.href).pathname;
        } catch (err) {
            return "";
        }
    }

    form.addEventListener("htmx:configRequest", (e) => {
        if (streaming) {
            e.preventDefault();
            return;
        }
        e.detail.parameters["form_path"] = openFormPath();
    });

    form.addEventListener("htmx:beforeRequest", () => {
        send.disabled = true;
        messages.querySelectorAll(".chat-empty").forEach((el) => el.remove());
    });

    form.addEventListener("htmx:afterRequest", (e) => {
        if (!e.detail.successful) {
            send.disabled = streaming;
            return;
        }
        input.value = "";
        autosize();
        setStreaming(true);
        scrollToBottom(true);
    });

    widget.addEventListener("htmx:responseError", (e) => {
        const status = e.detail.xhr.status;
        // the server already shows its error message as a flash toast
        if ((e.detail.xhr.getResponseHeader("HX-Trigger") || "").includes('"flash"')) return;
        if (status === 429) {
            showError("Too many messages. Please wait a moment and try again.");
        } else {
            showError("Something went wrong. Please try again.");
        }
    });

    widget.addEventListener("htmx:sendError", () => showError("Could not reach the server."));

    widget.addEventListener("htmx:sseClose", (e) => {
        e.detail.elt.classList.remove("chat-streaming");
        if (!messages.querySelector(".chat-streaming")) setStreaming(false);
    });

    widget.addEventListener("htmx:sseError", (e) => {
        // Replace the bubble so the sse extension drops the EventSource instead of retrying forever
        const bubble = e.detail.elt;
        const replacement = document.createElement("div");
        replacement.className = "chat-bubble";
        if (bubble.querySelector(".chat-typing")) {
            replacement.classList.add("chat-error");
            replacement.innerHTML = `<i class="bi bi-exclamation-triangle"></i> The response was interrupted.`;
        } else {
            replacement.innerHTML = bubble.innerHTML;
        }
        bubble.replaceWith(replacement);
        if (!messages.querySelector(".chat-streaming")) setStreaming(false);
    });

    // ---------- input ----------

    function autosize() {
        input.style.height = "auto";
        input.style.height = Math.min(input.scrollHeight, 160) + "px";
    }

    input.addEventListener("input", autosize);

    input.addEventListener("keydown", (e) => {
        if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
            e.preventDefault();
            if (input.value.trim() && !streaming) htmx.trigger(form, "submit");
        }
    });

    // ---------- restore state ----------

    if (storageGet(STORAGE_OPEN)) open();
})();
