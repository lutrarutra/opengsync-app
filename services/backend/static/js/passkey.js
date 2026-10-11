// Passkey (WebAuthn) support:
//  - login page: the password manager offers saved passkeys in the email field's autofill
//    (conditional mediation).
//  - after a password login: the password manager is asked to save a passkey (conditional create)
//    and shows its own save prompt.
//  - keeps the password manager in sync with passkeys removed on the server (Signal API).
// Endpoint URLs come from #passkey-config in base.html.
(function () {
    const UPGRADE_COOKIE = "passkey_upgrade";
    const config = JSON.parse(document.getElementById("passkey-config")?.textContent || "{}");
    const supported = !!(window.PublicKeyCredential && navigator.credentials);

    let conditionalAbort = null;

    // ---- encoding --------------------------------------------------------------------

    function b64urlToBuffer(value) {
        const b64 = value.replace(/-/g, "+").replace(/_/g, "/");
        const bin = atob(b64.padEnd(Math.ceil(b64.length / 4) * 4, "="));
        const bytes = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
        return bytes.buffer;
    }

    function bufferToB64url(buffer) {
        let bin = "";
        for (const b of new Uint8Array(buffer)) bin += String.fromCharCode(b);
        return btoa(bin).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    }

    function parseCreationOptions(json) {
        if (PublicKeyCredential.parseCreationOptionsFromJSON) {
            return PublicKeyCredential.parseCreationOptionsFromJSON(json);
        }
        return {
            ...json,
            challenge: b64urlToBuffer(json.challenge),
            user: { ...json.user, id: b64urlToBuffer(json.user.id) },
            excludeCredentials: (json.excludeCredentials || []).map(c => ({ ...c, id: b64urlToBuffer(c.id) })),
        };
    }

    function parseRequestOptions(json) {
        if (PublicKeyCredential.parseRequestOptionsFromJSON) {
            return PublicKeyCredential.parseRequestOptionsFromJSON(json);
        }
        return {
            ...json,
            challenge: b64urlToBuffer(json.challenge),
            allowCredentials: (json.allowCredentials || []).map(c => ({ ...c, id: b64urlToBuffer(c.id) })),
        };
    }

    function credentialToJSON(credential) {
        // Some password-manager extensions return credentials without a working toJSON().
        if (typeof credential.toJSON === "function") {
            try { return credential.toJSON(); } catch (e) {}
        }
        const r = credential.response;
        const response = { clientDataJSON: bufferToB64url(r.clientDataJSON) };
        if (r.attestationObject) {
            response.attestationObject = bufferToB64url(r.attestationObject);
            response.transports = typeof r.getTransports === "function" ? r.getTransports() : [];
        } else {
            response.authenticatorData = bufferToB64url(r.authenticatorData);
            response.signature = bufferToB64url(r.signature);
            if (r.userHandle) response.userHandle = bufferToB64url(r.userHandle);
        }
        return {
            id: credential.id,
            rawId: bufferToB64url(credential.rawId),
            type: credential.type,
            response,
            authenticatorAttachment: credential.authenticatorAttachment || undefined,
            clientExtensionResults: credential.getClientExtensionResults(),
        };
    }

    // ---- helpers ---------------------------------------------------------------------

    async function postJSON(url, body) {
        const resp = await fetch(url, {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json", "X-CSRF-Token": getCookie("csrf_token") || "" },
            body: JSON.stringify(body ?? {}),
        });
        let data = {};
        try { data = await resp.json(); } catch (e) {}
        if (!resp.ok) {
            const err = new Error(typeof data.detail === "string" ? data.detail : "Passkey request failed.");
            err.data = data;
            throw err;
        }
        return data;
    }

    async function capabilities() {
        if (!supported) return {};
        if (PublicKeyCredential.getClientCapabilities) {
            try { return await PublicKeyCredential.getClientCapabilities(); } catch (e) {}
        }
        const conditionalGet = PublicKeyCredential.isConditionalMediationAvailable
            ? await PublicKeyCredential.isConditionalMediationAvailable() : false;
        return { conditionalGet };
    }

    function signalAcceptedCredentials(rpId, userId, credentialIds) {
        // Lets the password manager drop passkeys that were removed here or by a password reset.
        if (!rpId || !userId || !window.PublicKeyCredential?.signalAllAcceptedCredentials) return;
        PublicKeyCredential.signalAllAcceptedCredentials({
            rpId, userId, allAcceptedCredentialIds: credentialIds,
        }).catch(() => {});
    }

    function findIn(el, selector) {
        if (!el || !el.querySelector) return null;
        return el.matches?.(selector) ? el : el.querySelector(selector);
    }

    // ---- sign in ---------------------------------------------------------------------

    async function startConditionalLogin() {
        const caps = await capabilities();
        if (!caps.conditionalGet) return;

        conditionalAbort?.abort();
        const controller = new AbortController();
        conditionalAbort = controller;

        let credential;
        try {
            const { options } = await postJSON(config.loginOptions);
            credential = await navigator.credentials.get({
                publicKey: parseRequestOptions(options),
                mediation: "conditional",
                signal: controller.signal,
            });
        } catch (e) {
            if (e.name !== "AbortError") console.debug("Passkey autofill unavailable:", e);
            return;
        }
        await finishLogin(credential);
    }

    async function finishLogin(credential) {
        try {
            const data = await postJSON(config.loginVerify, credentialToJSON(credential));
            window.location.href = data.redirect;
        } catch (e) {
            if (e.data?.unknown_credential && PublicKeyCredential.signalUnknownCredential) {
                PublicKeyCredential.signalUnknownCredential({
                    rpId: e.data.rp_id, credentialId: credential.id,
                }).catch(() => {});
            }
            showFlashToast({ category: "error", message: e.message });
            startConditionalLogin();
        }
    }

    // ---- register --------------------------------------------------------------------

    async function registerPasskey() {
        try {
            const reg = await postJSON(config.registerOptions, { conditional: false });
            const credential = await navigator.credentials.create({ publicKey: parseCreationOptions(reg.options) });
            const data = await postJSON(config.registerVerify, credentialToJSON(credential));
            showFlashToast({ category: "success", message: `Passkey saved (${data.name}).` });
            return true;
        } catch (e) {
            if (e.name === "InvalidStateError") {
                showFlashToast({ category: "info", message: "Your password manager already has a passkey for this account." });
            } else if (e.name !== "NotAllowedError") {
                showFlashToast({ category: "error", message: e.message });
            }
            return false;
        }
    }

    async function offerPasskeyAfterLogin() {
        if (!getCookie(UPGRADE_COOKIE)) return;
        deleteCookie(UPGRADE_COOKIE);
        if (!supported) return;

        const caps = await capabilities();
        let reg;
        try {
            reg = await postJSON(config.registerOptions, { conditional: !!caps.conditionalCreate });
        } catch (e) {
            return;
        }
        signalAcceptedCredentials(reg.rp_id, reg.user_handle, reg.credential_ids);

        if (!caps.conditionalCreate) return;
        try {
            // Succeeds only if the password manager just filled the password; it then saves
            // the passkey and shows its own confirmation.
            const credential = await navigator.credentials.create({
                publicKey: parseCreationOptions(reg.options),
                mediation: "conditional",
            });
            await postJSON(config.registerVerify, credentialToJSON(credential));
        } catch (e) {
            // InvalidStateError: the password manager already holds a passkey for this account.
            // NotAllowedError: the password wasn't autofilled or the user declined.
        }
    }

    // ---- wiring ----------------------------------------------------------------------

    htmx.onLoad(function (el) {
        if (!supported) return;

        const form = findIn(el, ".passkey-login-form");
        if (form) {
            startConditionalLogin();
        }

        const list = findIn(el, ".passkey-list[data-signal-rp-id]");
        if (list) {
            signalAcceptedCredentials(
                list.dataset.signalRpId,
                list.dataset.signalUserHandle,
                JSON.parse(list.dataset.signalCredentialIds || "[]"),
            );
        }
    });

    $(document).on("click", ".passkey-register-btn", async function () {
        if (!supported) {
            showFlashToast({ category: "warning", message: "This browser does not support passkeys." });
            return;
        }
        const btn = $(this);
        btn.prop("disabled", true);
        const saved = await registerPasskey();
        btn.prop("disabled", false);
        if (saved) {
            htmx.ajax("GET", btn.data("list-url"), { target: "#passkey-list", swap: "outerHTML" });
        }
    });

    $(document).ready(offerPasskeyAfterLogin);
})();
