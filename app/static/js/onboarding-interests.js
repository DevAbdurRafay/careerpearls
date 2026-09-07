(function () {
    function initInterestChips(root) {
        var scope = root || document;
        var counter = scope.getElementById ? scope.getElementById('interestCounter') : document.getElementById('interestCounter');
        var submitBtn = scope.getElementById ? scope.getElementById('submitBtn') : document.getElementById('submitBtn');
        var minRequired = 3;

        function updateInterests() {
            var checked = document.querySelectorAll('.interest-chip input:checked').length;
            if (counter) {
                counter.textContent = 'Select at least ' + minRequired + ' fields (' + checked + ' selected)';
                counter.classList.toggle('valid', checked >= minRequired);
            }
            if (submitBtn) {
                submitBtn.disabled = checked < minRequired;
            }
        }

        document.querySelectorAll('.interest-chip').forEach(function (chip) {
            if (chip.dataset.bound === '1') return;
            chip.dataset.bound = '1';

            var input = chip.querySelector('input[type="checkbox"]');
            if (!input) return;

            chip.setAttribute('role', 'checkbox');
            chip.setAttribute('tabindex', '0');
            chip.setAttribute('aria-checked', input.checked ? 'true' : 'false');

            function toggleChip() {
                input.checked = !input.checked;
                chip.classList.toggle('selected', input.checked);
                chip.setAttribute('aria-checked', input.checked ? 'true' : 'false');
                updateInterests();
            }

            chip.addEventListener('click', function (e) {
                e.preventDefault();
                toggleChip();
            });

            chip.addEventListener('keydown', function (e) {
                if (e.key === ' ' || e.key === 'Enter') {
                    e.preventDefault();
                    toggleChip();
                }
            });
        });

        updateInterests();
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function () { initInterestChips(); });
    } else {
        initInterestChips();
    }

    window.cpInitInterestChips = initInterestChips;
})();
