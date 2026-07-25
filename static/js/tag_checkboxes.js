/*
 * TagCheckboxes - hierarchy behaviour for the grouped tag checkbox layout
 * (templates/partial/tags_checkboxes.html).
 *
 * Within the given scope (usually a <form>):
 *   - ticking a technique auto-ticks its parent category
 *   - un-ticking a technique un-ticks the category when no sibling technique
 *     remains ticked
 *   - un-ticking a category clears all its techniques
 * so a technique is never selected without its category, and a category is
 * never left selected on its own once its last technique is removed.
 *
 * Usage:  TagCheckboxes.init(document.getElementById('my-form'));
 */
window.TagCheckboxes = (function () {
    function cssEscape(v) {
        return v.replace(/"/g, '\\"');
    }

    function init(scope) {
        if (!scope) return;

        function parentInput(value) {
            return scope.querySelector('input[data-tag-class][value="' + cssEscape(value) + '"]');
        }

        function siblings(parentValue) {
            return scope.querySelectorAll('input[data-tag-parent="' + cssEscape(parentValue) + '"]');
        }

        scope.querySelectorAll('input[data-tag-parent]').forEach(function (sub) {
            sub.addEventListener('change', function () {
                var parentValue = sub.getAttribute('data-tag-parent');
                var parent = parentInput(parentValue);
                if (!parent) return;
                if (sub.checked) {
                    parent.checked = true;   // selecting a technique selects its category
                } else {
                    // deselecting the last remaining technique deselects the category
                    var anyChecked = Array.prototype.some.call(
                        siblings(parentValue), function (s) { return s.checked; });
                    if (!anyChecked) parent.checked = false;
                }
            });
        });

        scope.querySelectorAll('input[data-tag-class]').forEach(function (cls) {
            cls.addEventListener('change', function () {
                if (!cls.checked) {
                    siblings(cls.value).forEach(function (s) { s.checked = false; });
                }
            });
        });
    }

    return { init: init };
})();
