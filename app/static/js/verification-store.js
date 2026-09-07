(function () {
    'use strict';

    /* ── Storage helper ───────────────────────────────────────────────── */
    var STORAGE_KEY = 'cp_pending_verification';
    function readStore() {
        try { var r = localStorage.getItem(STORAGE_KEY); return r ? JSON.parse(r) : null; }
        catch (e) { return null; }
    }
    window.cpVerificationStore = {
        save:  function (p) { try { localStorage.setItem(STORAGE_KEY, JSON.stringify(p)); } catch (e) {} },
        clear: function ()  { localStorage.removeItem(STORAGE_KEY); },
        read:  readStore
    };

    /* ── Email display helper ─────────────────────────────────────────── */
    document.addEventListener('DOMContentLoaded', function () {
        var emailEl = document.getElementById('verifyEmailDisplay');
        var stored  = readStore();
        if (emailEl && stored && stored.email && !emailEl.textContent.trim()) {
            emailEl.textContent = stored.email;
        }
    });

    /* ── Countdown Timer ─────────────────────────────────────────────── */
    document.addEventListener('DOMContentLoaded', function () {
        var countEl   = document.getElementById('verifyCountdown');
        if (!countEl) return;

        var badgeWrap = countEl.parentElement;
        var resendBtn = document.getElementById('resendBtn');
        var submitBtn = document.querySelector('#verifyForm [type="submit"]');

        /* Total seconds from server via Jinja: <span id="verifyCountdown">{{ expiry_seconds }}</span> */
        var totalSeconds = parseInt(countEl.textContent.trim(), 10) || 120;

        /* Anchor timer to localStorage so it survives page reloads */
        var anchorKey = 'cp_timer_' + window.location.pathname.replace(/\W/g, '_');
        var now = Date.now();
        var existingAnchor = localStorage.getItem(anchorKey);
        if (existingAnchor) {
            var elapsed = Math.floor((now - parseInt(existingAnchor, 10)) / 1000);
            totalSeconds = Math.max(0, totalSeconds - elapsed);
        } else {
            localStorage.setItem(anchorKey, now.toString());
        }

        /* Disable resend initially */
        if (resendBtn && totalSeconds > 0) {
            resendBtn.disabled     = true;
            resendBtn.style.opacity = '0.4';
            resendBtn.style.cursor  = 'not-allowed';
            resendBtn.title         = 'Wait for code to expire before resending';
        }

        function setExpired() {
            countEl.textContent = 'Expired';
            if (badgeWrap) {
                badgeWrap.style.background   = 'rgba(239,68,68,0.15)';
                badgeWrap.style.color        = '#f87171';
                badgeWrap.style.borderColor  = 'rgba(239,68,68,0.3)';
            }
            if (resendBtn) {
                resendBtn.disabled     = false;
                resendBtn.style.opacity = '1';
                resendBtn.style.cursor  = 'pointer';
                resendBtn.style.color   = '#4facfe';
                resendBtn.title         = 'Request a new verification code';
            }
            if (submitBtn) {
                submitBtn.disabled     = true;
                submitBtn.style.opacity = '0.45';
                submitBtn.title         = 'Code expired — please request a new code';
            }
            localStorage.removeItem(anchorKey);
        }

        function tick() {
            if (totalSeconds <= 0) { setExpired(); return; }
            /* Format: show "1m 30s" if >=60s else "45s" */
            if (totalSeconds >= 60) {
                var m = Math.floor(totalSeconds / 60), s = totalSeconds % 60;
                countEl.textContent = m + 'm ' + (s < 10 ? '0' : '') + s + 's';
            } else {
                countEl.textContent = totalSeconds + 's';
            }
            /* Warn orange under 30s */
            if (totalSeconds <= 30 && badgeWrap) {
                badgeWrap.style.background  = 'rgba(245,158,11,0.15)';
                badgeWrap.style.color       = '#fbbf24';
                badgeWrap.style.borderColor = 'rgba(245,158,11,0.3)';
            }
            totalSeconds--;
            setTimeout(tick, 1000);
        }

        /* Clear anchor on submit or resend */
        var verifyForm = document.getElementById('verifyForm');
        if (verifyForm) verifyForm.addEventListener('submit', function () { localStorage.removeItem(anchorKey); });
        if (resendBtn) {
            var resendForm = resendBtn.closest('form');
            if (resendForm) resendForm.addEventListener('submit', function () { localStorage.removeItem(anchorKey); });
        }

        tick();
    });
})();
