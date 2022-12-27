"use strict";

// "Go to keyword" entry

if (typeof $ !== "undefined") {
    $(() => {
        $("link.select2-css").removeAttr("disabled");
        $("select#vh-select-tag")
            .select2({
                placeholder: "Go to keyword",
                width: "100%",
                ajax: {
                    url: "api/tagsearch"
                },
                minimumInputLength: 1
            })
            .on("select2:select", (e) => {
                window.location = e.params.data.href;
            })
            // .on("select2:open", () => {
            //     // Workaround for https://github.com/select2/select2/issues/5993
            //     // (would be needed with jQuery 3.6.0)
            //     $(".select2-container--open .select2-search__field")[0].focus();
            // })
            .show();
    });
}

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

// show theme switcher (defaults to invisible for non-JS browsers)
document.getElementById("theme-switcher").style.display = "revert";

// tweak native theme button tooltip
document.getElementById("theme-native").title = "Switch to native theme" +
    (matchMedia("(prefers-color-scheme: dark)").matches ? " (which is dark)" : " (which is light)");
