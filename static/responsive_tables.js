/* Keep wide tables inside the page instead of letting them widen the mobile document. */
(function () {
    'use strict';

    var wrappedAncestor = '.table-wrapper, .table-wrap, .table-responsive, .table-container, .table-scroll, .dq-scroll, .ar-table-scroll, .ms-table-scroll, .vdash__table-wrap, .profile-table-scroll';

    function wrapTables() {
        document.querySelectorAll('.page-container table').forEach(function (table) {
            if (table.closest(wrappedAncestor)) return;

            var wrapper = document.createElement('div');
            wrapper.className = 'table-scroll table-scroll--auto';
            table.parentNode.insertBefore(wrapper, table);
            wrapper.appendChild(table);
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', wrapTables, { once: true });
    } else {
        wrapTables();
    }
})();
