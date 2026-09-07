/**
 * International Phone Input Component with Country Flags & Code Selector
 */
document.addEventListener('DOMContentLoaded', function () {
    const phoneInputs = document.querySelectorAll('input[name="phone"]');

    phoneInputs.forEach(input => {
        // Enforce numeric only input
        input.addEventListener('input', function (e) {
            this.value = this.value.replace(/\D/g, '');
        });

        const group = input.closest('.input-group');
        if (!group) return;

        const select = group.querySelector('select[name="country_code"]');
        if (!select) return;

        // Ensure styled container wrapping custom dropdown if not already created
        if (group.querySelector('.cp-country-dropdown-wrap')) return;

        // Transform select into interactive custom flag dropdown while syncing underlying select value
        select.style.display = 'none';

        const wrap = document.createElement('div');
        wrap.className = 'cp-country-dropdown-wrap dropdown position-relative d-inline-block';
        wrap.style.maxWidth = '160px';

        const selectedOption = select.options[select.selectedIndex] || select.options[0];
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'btn btn-cp-outline dropdown-toggle d-flex align-items-center justify-content-between w-100 text-truncate px-2 py-2';
        btn.style.fontSize = '0.85rem';
        btn.setAttribute('data-bs-toggle', 'dropdown');
        btn.setAttribute('aria-expanded', 'false');
        btn.innerHTML = `<span class="selected-flag-label me-1">${selectedOption ? selectedOption.text : '🇵🇰 +92'}</span>`;

        const menu = document.createElement('div');
        menu.className = 'dropdown-menu shadow-lg p-2 cp-country-menu';
        menu.style.maxHeight = '280px';
        menu.style.overflowY = 'auto';
        menu.style.minWidth = '240px';

        const searchBox = document.createElement('input');
        searchBox.type = 'text';
        searchBox.className = 'form-control form-control-sm mb-2';
        searchBox.placeholder = 'Search country or code...';
        searchBox.addEventListener('keyup', function () {
            const term = this.value.toLowerCase();
            items.querySelectorAll('.dropdown-item').forEach(item => {
                const text = item.textContent.toLowerCase();
                item.style.display = text.includes(term) ? 'block' : 'none';
            });
        });
        menu.appendChild(searchBox);

        const items = document.createElement('div');
        items.className = 'cp-country-items';

        Array.from(select.options).forEach(opt => {
            const item = document.createElement('a');
            item.className = 'dropdown-item d-flex align-items-center py-2 px-2 rounded cursor-pointer small';
            item.href = '#';
            item.textContent = opt.text;
            if (opt.selected) item.classList.add('active');

            item.addEventListener('click', function (e) {
                e.preventDefault();
                select.value = opt.value;
                select.dispatchEvent(new Event('change', { bubbles: true }));
                btn.querySelector('.selected-flag-label').textContent = opt.text;
                items.querySelectorAll('.dropdown-item').forEach(i => i.classList.remove('active'));
                item.classList.add('active');
                const bsDropdown = bootstrap.Dropdown.getInstance(btn);
                if (bsDropdown) bsDropdown.hide();
            });
            items.appendChild(item);
        });

        menu.appendChild(items);
        wrap.appendChild(btn);
        wrap.appendChild(menu);

        group.insertBefore(wrap, select);
    });
});
