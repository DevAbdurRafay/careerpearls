/**
 * CareerPearls Client-Side Time Synchronization
 * Automatically converts all UTC timestamps in tables, cards, and audit logs
 * into the user's exact local device time and preferred format.
 */
(function () {
    'use strict';

    function formatElement(el) {
        if (el.getAttribute('data-synced') === 'true') return;

        var raw = el.getAttribute('data-utc') || el.getAttribute('data-utc-time') || el.getAttribute('datetime');
        if (!raw) return;

        var iso = raw.trim();
        if (!iso.includes('T')) {
            iso = iso.replace(' ', 'T');
        }
        if (!iso.endsWith('Z') && !iso.includes('+') && !iso.includes('-')) {
            iso += 'Z';
        }

        var d = new Date(iso);
        if (isNaN(d.getTime())) return;

        var mode = el.getAttribute('data-mode') || 'datetime';

        try {
            var formatted = '';
            if (mode === 'time') {
                formatted = d.toLocaleTimeString(undefined, {
                    hour: '2-digit',
                    minute: '2-digit',
                    hour12: true
                });
            } else if (mode === 'date') {
                formatted = d.toLocaleDateString(undefined, {
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric'
                });
            } else if (mode === 'short-datetime') {
                var datePart = d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
                var timePart = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: true });
                formatted = datePart + ', ' + timePart;
            } else {
                var datePartFull = d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
                var timePartFull = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: true });
                formatted = datePartFull + ' ' + timePartFull;
            }

            el.textContent = formatted;
            el.setAttribute('data-synced', 'true');
            el.setAttribute('title', 'Device Time: ' + formatted);
        } catch (err) {
            console.warn('Time format error:', err);
        }
    }

    function syncAllTimes() {
        var elements = document.querySelectorAll('.cp-local-time:not([data-synced="true"]), [data-utc]:not([data-synced="true"]), [data-utc-time]:not([data-synced="true"]), time[datetime]:not([data-synced="true"])');
        for (var i = 0; i < elements.length; i++) {
            formatElement(elements[i]);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', syncAllTimes);
    } else {
        syncAllTimes();
    }

    window.cpSyncTimes = syncAllTimes;
})();
