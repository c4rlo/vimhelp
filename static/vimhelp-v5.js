"use strict";

// "Go to keyword" entry

new TomSelect("#vh-select-tag", {
    maxItems: 1,
    loadThrottle: 250,
    placeholder: "Go to keyword",
    valueField: "href",
    onFocus: () => {
        const self = document.getElementById("vh-select-tag").tomselect;
        self.clear();
        self.clearOptions();
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

// Theme switcher

for (let theme of ["theme-native", "theme-light", "theme-dark"]) {
    document.getElementById(theme).addEventListener("click", (e) => {
        console.log("selected theme:", theme);
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
            : "Tue, 19 Jan 2038 04:14:07 GMT";  // set "permanent" cookie
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

// hide sidebar when it wraps
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
