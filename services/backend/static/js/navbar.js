// Navbar: burger toggle (small screens) and the dropdown menus.
// Mice open nav dropdowns on hover (navbar.css); clicks, taps and Enter toggle the .open class.
(function () {
    const nav = document.getElementById("navbar");
    if (!nav) return;

    const burger = document.getElementById("burger");
    const container = document.getElementById("navbar-container");

    burger.addEventListener("click", () => {
        const open = container.classList.toggle("nav-active");
        burger.classList.toggle("toggle", open);
        burger.setAttribute("aria-expanded", open);
    });

    function setOpen(menu, open) {
        menu.classList.toggle("open", open);
        const toggle = menu.querySelector(":scope > button");
        if (toggle) toggle.setAttribute("aria-expanded", open);
    }

    function closeAll(except) {
        nav.querySelectorAll(".nav-dropdown.open, .profile-menu.open").forEach(menu => {
            if (menu !== except) setOpen(menu, false);
        });
    }

    // clicks toggle a menu: the profile menu has no hover state, and touch screens have no hover at all
    nav.querySelectorAll(".nav-dropdown, .profile-menu").forEach(menu => {
        menu.querySelector(":scope > button").addEventListener("click", () => {
            const open = !menu.classList.contains("open");
            closeAll(menu);
            setOpen(menu, open);
        });
        // tabbing past the last entry closes the menu
        menu.addEventListener("focusout", (e) => {
            if (e.relatedTarget && !menu.contains(e.relatedTarget)) setOpen(menu, false);
        });
    });

    // a click on a hovered dropdown must not pin it open once the mouse moves on
    nav.querySelectorAll(".nav-dropdown").forEach(menu => {
        menu.addEventListener("pointerleave", (e) => {
            if (e.pointerType !== "touch") setOpen(menu, false);
        });
    });

    document.addEventListener("mousedown", (e) => {
        if (!e.target.closest(".nav-dropdown, .profile-menu")) closeAll();
    });

    document.addEventListener("keydown", (e) => {
        if (e.key !== "Escape") return;
        const menu = document.activeElement && document.activeElement.closest("#navbar .nav-dropdown, #navbar .profile-menu");
        closeAll();
        if (menu) menu.querySelector(":scope > button").focus();
    });
})();
