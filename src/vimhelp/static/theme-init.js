"use strict";

const themeMatch = document.cookie.match(/(?:^|;\s*)theme=(light|dark)(?:;|$)/);
if (themeMatch) {
    document.documentElement.classList.remove("light", "dark");
    document.documentElement.classList.add(themeMatch[1]);
    document.querySelector('meta[name="color-scheme"]').content = `only ${themeMatch[1]}`;
}
