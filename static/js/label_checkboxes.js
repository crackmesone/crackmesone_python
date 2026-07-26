/*
 * LabelCheckboxes - hierarchy behaviour for the grouped label checkbox layout
 * (templates/partial/labels_checkboxes.html).
 *
 * Within the given scope (usually a <form>):
 *   - ticking a technique auto-ticks its parent category
 *   - un-ticking a technique un-ticks the category when no sibling technique
 *     remains ticked
 *   - un-ticking a category clears all its techniques
 * so a technique is never selected without its category, and a category is
 * never left selected on its own once its last technique is removed.
 *
 * Usage:  LabelCheckboxes.init(document.getElementById('my-form'));
 */
window.LabelCheckboxes = (function () {
    function cssEscape(v) {
        return v.replace(/"/g, '\\"');
    }

    function init(scope) {
        if (!scope) return;

        function parentInput(value) {
            return scope.querySelector('input[data-label-class][value="' + cssEscape(value) + '"]');
        }

        function siblings(parentValue) {
            return scope.querySelectorAll('input[data-label-parent="' + cssEscape(parentValue) + '"]');
        }

        scope.querySelectorAll('input[data-label-parent]').forEach(function (sub) {
            sub.addEventListener('change', function () {
                var parentValue = sub.getAttribute('data-label-parent');
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

        scope.querySelectorAll('input[data-label-class]').forEach(function (cls) {
            cls.addEventListener('change', function () {
                if (!cls.checked) {
                    siblings(cls.value).forEach(function (s) { s.checked = false; });
                }
            });
        });
    }

    return { init: init };
})();
