"use strict";

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

const sidebar = document.getElementById("vh-sidebar");
if (sidebar) {
    const content = document.getElementById("vh-content");
    const pre = document.getElementsByTagName("pre")[0];

    const resizeObserver = new ResizeObserver((entries) => {
        const contentWidth = content.getBoundingClientRect().width;
        const preWidth = pre.getBoundingClientRect().width;
        const preMargin = contentWidth - preWidth;
        const sidebarWidth = sidebar.getBoundingClientRect().width;
        const sidebarVis = getComputedStyle(sidebar).getPropertyValue("visibility");
        if (sidebarVis == "visible" && preMargin <= 5) {
            sidebar.style.visibility = "hidden";
            sidebar.style.position = "absolute";
            sidebar.style.left = "10px";
        }
        else if (sidebarVis == "hidden" && preMargin >= sidebarWidth + 10) {
            sidebar.style.visibility = "visible";
            sidebar.style.position = "sticky";
        }
        if (sidebar.style.visibility == "visible") {
            const preLeft = pre.getBoundingClientRect().left;
            const left = (preLeft - sidebarWidth) / 2;
            sidebar.style.left = `${left}px`;
        }
    });

    resizeObserver.observe(content);
}
