document.addEventListener('DOMContentLoaded', () => {
    const sidebar = document.getElementById('adminSidebar');
    const toggle = document.getElementById('sidebarToggle');
    const overlay = document.getElementById('adminOverlay');
    const main = document.querySelector('.admin-main');

    if (toggle && sidebar) {
        toggle.addEventListener('click', () => {
            // On mobile, toggle open class
            // On desktop, toggle collapsed class
            if (window.innerWidth >= 992) {
                sidebar.classList.toggle('collapsed');
                main.classList.toggle('collapsed');
            } else {
                sidebar.classList.toggle('open');
                overlay.classList.toggle('show');
            }
        });
        
        overlay.addEventListener('click', () => {
            sidebar.classList.remove('open');
            overlay.classList.remove('show');
        });
    }
});
