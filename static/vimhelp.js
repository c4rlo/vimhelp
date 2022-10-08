"use strict";

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
