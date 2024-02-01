"use strict";


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


{% if mode != "offline" %}

// "Go to keyword" entry

const tagTS = new TomSelect("#vh-select-tag", {
    maxItems: 1,
    loadThrottle: 250,
    valueField: "href",
    placeholder: "Go to keyword (type for autocomplete)",
    onFocus: () => {
        const ts = document.getElementById("vh-select-tag").tomselect;
        ts.clear();
        ts.clearOptions();
    },
    shouldLoad: (query) => query.length >= 1,
    load: async (query, callback) => {
        let url = "/api/tagsearch?q=" + encodeURIComponent(query);
        if (document.location.protocol === "file:") {
            url = "http://127.0.0.1:5000" + url;
        }
        const resp = await fetch(url);
        const respJson = await resp.json();
        callback(respJson.results);
    },
    onChange: (value) => {
        if (value) {
            window.location = value;
        }
    }
});

document.querySelector(".tag.srch .placeholder").addEventListener("click", (e) => {
    tagTS.focus();
});


// "Site search" entry

const srchInput = document.getElementById("vh-srch-input");
srchInput.placeholder = "Site search (opens new DuckDuckGo tab)";
srchInput.addEventListener("blur", (e) => {
    srchInput.value = "";
});
document.querySelector(".site.srch .placeholder").addEventListener("click", (e) => {
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
        document.documentElement.className = className;
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

document.body.addEventListener("click", (e) => {
    // hide theme dropdown (vimhelp.css has it as "display: none")
    document.getElementById("theme-dropdown").style.display = null;
});

// tweak native theme button tooltip
document.getElementById("theme-native").title = "Switch to native theme" +
    (matchMedia("(prefers-color-scheme: dark)").matches ? " (which is dark)" : " (which is light)");


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

{% endif %}
