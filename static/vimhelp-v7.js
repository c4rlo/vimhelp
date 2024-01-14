"use strict";


// "Go to keyword" & "Site search" keyboard hints

const tagKbdHint = document.getElementById("tag-kbd-hint");
const ssKbdHint = document.getElementById("ss-kbd-hint");


// "Go to keyword" entry

const tagTS = new TomSelect("#vh-select-tag", {
    maxItems: 1,
    loadThrottle: 250,
    placeholder: "Go to keyword",
    valueField: "href",
    onFocus: () => {
        const ts = document.getElementById("vh-select-tag").tomselect;
        ts.clear();
        ts.clearOptions();
        ts.settings.placeholder = "Go to keyword (type for autocomplete)";
        ts.inputState();
        tagKbdHint.style.opacity = 0.2;
    },
    onBlur: () => {
        const ts = document.getElementById("vh-select-tag").tomselect;
        ts.settings.placeholder = "Go to keyword";
        ts.inputState();
        tagKbdHint.style.opacity = 0.7;
    },
    shouldLoad: (query) => query.length >= 1,
    load: async (query, callback) => {
        const url = "/api/tagsearch?q=" + encodeURIComponent(query);
        const resp = await fetch(url);
        callback((await resp.json()).results);
    },
    onChange: (value) => {
        if (value) {
            window.location = value;
        }
    }
});

tagKbdHint.addEventListener("click", (e) => {
    tagTS.focus();
});


// "Site search" entry

const srchInput = document.getElementById("vh-srch-input");
srchInput.addEventListener("focus", (e) => {
    srchInput.placeholder = "Site search (opens new DuckDuckGo tab)";
    ssKbdHint.style.opacity = 0.2;
});
srchInput.addEventListener("blur", (e) => {
    srchInput.placeholder = "Site search";
    ssKbdHint.style.opacity = 0.7;
});

ssKbdHint.addEventListener("click", (e) => {
    srchInput.focus();
});


// Theme switcher

for (let theme of ["theme-native", "theme-light", "theme-dark"]) {
    document.getElementById(theme).addEventListener("click", (e) => {
        const [className, meta] = {
            "theme-native": [ "",      "light dark" ],
            "theme-light":  [ "light", "only light" ],
            "theme-dark":   [ "dark",  "only dark" ]
        }[theme];
        document.getElementsByTagName("html")[0].className = className;
        document.querySelector('meta[name="color-scheme"]').content = meta;

        const cookieDomain = location.hostname.replace(/^neo\./, "");
        const cookieExpiry = theme === "theme-native"
            ? "Tue, 01 Jan 1970 00:00:00 GMT"   // delete cookie
            : "Fri, 31 Dec 9999 23:59:59 GMT";  // set "permanent" cookie
        document.cookie =
            `theme=${className}; Secure; Domain=${cookieDomain}; SameSite=Lax; Path=/; Expires=${cookieExpiry}`;
    });
}

document.getElementById("theme-current").addEventListener("click", (e) => {
    const themeDropdown = document.getElementById("theme-dropdown");
    if (!themeDropdown.style.display) {
        // if currently hidden, show it...
        themeDropdown.style.display = "revert";
        // ...and prevent the handler on <body> from running, which would hide it again.
        e.stopPropagation();
    }
});

document.getElementsByTagName("body")[0].addEventListener("click", (e) => {
    // hide theme dropdown (vimhelp.css has it as "display: none")
    document.getElementById("theme-dropdown").style.display = null;
});

// tweak native theme button tooltip
document.getElementById("theme-native").title = "Switch to native theme" +
    (matchMedia("(prefers-color-scheme: dark)").matches ? " (which is dark)" : " (which is light)");


// Hide sidebar when it wraps

const onResize = (e) => {
    const sidebar = document.getElementById("vh-sidebar");
    const sidebarTop = sidebar.getBoundingClientRect().top;
    const contentBottom = document.getElementById("vh-content").getBoundingClientRect().bottom;
    if (sidebarTop >= contentBottom - 4) {
        sidebar.style.visibility = "hidden";
        sidebar.style.height = "0px";
    }
    else {
        sidebar.style.visibility = null;
        sidebar.style.height = null;
    }
};
addEventListener("resize", onResize);
onResize();


// Keyboard shortcuts
// https://github.com/c4rlo/vimhelp/issues/28

const onKeyDown = (e) => {
    if (e.isComposing || e.keyCode === 229) {
        // https://developer.mozilla.org/en-US/docs/Web/API/Element/keydown_event
        return;
    }
    const a = document.activeElement;
    if (a && (a.isContentEditable || a.tagName === "INPUT" || a.tagName === "SELECT")) {
        return;
    }
    if (e.key === "k") {
        e.preventDefault();
        document.getElementById("vh-select-tag-ts-control").focus();
    }
    else if (e.key === "s") {
        e.preventDefault();
        document.getElementById("vh-srch-input").focus();
    }
};
addEventListener("keydown", onKeyDown);
