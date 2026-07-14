/*
 * TagCheckboxes - hierarchy behaviour for the grouped tag checkbox layout
 * (templates/partial/tags_checkboxes.html).
 *
 * Within the given scope (usually a <form>):
 *   - ticking a specific technique auto-ticks its parent category
 *   - un-ticking a category clears its techniques
 * so a sub-label is never submitted without its parent.
 *
 * Usage:  TagCheckboxes.init(document.getElementById('my-form'));
 */
window.TagCheckboxes = (function () {
    function init(scope) {
        if (!scope) return;

        function parentInput(value) {
            return scope.querySelector('input[data-tag-class][value="' + value.replace(/"/g, '\\"') + '"]');
        }

        scope.querySelectorAll('input[data-tag-parent]').forEach(function (sub) {
            sub.addEventListener('change', function () {
                if (sub.checked) {
                    var parent = parentInput(sub.getAttribute('data-tag-parent'));
                    if (parent) parent.checked = true;
                }
            });
        });

        scope.querySelectorAll('input[data-tag-class]').forEach(function (cls) {
            cls.addEventListener('change', function () {
                if (!cls.checked) {
                    scope.querySelectorAll('input[data-tag-parent="' + cls.value.replace(/"/g, '\\"') + '"]')
                        .forEach(function (s) { s.checked = false; });
                }
            });
        });
    }

    return { init: init };
})();
