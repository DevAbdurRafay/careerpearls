(function () {
    var DEFAULT_MS = 4000;

    function dismissToast(toast) {
        if (!toast || toast.classList.contains('cp-toast-hide')) return;
        toast.classList.add('cp-toast-hide');
        window.setTimeout(function () {
            toast.remove();
            var stack = document.getElementById('cpToastStack');
            if (stack && !stack.children.length) {
                stack.remove();
            }
        }, 280);
    }

    function initFlashToasts() {
        document.querySelectorAll('.cp-toast[data-auto-dismiss]').forEach(function (toast) {
            var ms = parseInt(toast.getAttribute('data-auto-dismiss'), 10);
            if (Number.isNaN(ms) || ms <= 0) {
                ms = DEFAULT_MS;
            }
            window.setTimeout(function () {
                dismissToast(toast);
            }, ms);
        });
    }

    function initNetworkBanner() {
        var banner = null;
        function updateOnlineStatus() {
            if (!navigator.onLine) {
                if (!banner) {
                    banner = document.createElement('div');
                    banner.id = 'cpOfflineBanner';
                    banner.style.position = 'fixed';
                    banner.style.top = '44px';
                    banner.style.left = '0';
                    banner.style.width = '100%';
                    banner.style.backgroundColor = '#ef4444';
                    banner.style.color = '#ffffff';
                    banner.style.textAlign = 'center';
                    banner.style.padding = '6px 12px';
                    banner.style.fontSize = '0.8rem';
                    banner.style.fontWeight = '600';
                    banner.style.zIndex = '9999';
                    banner.innerHTML = '<i class="bi bi-wifi-off me-2"></i>Network Disconnected. You are currently offline.';
                    document.body.appendChild(banner);
                }
            } else {
                if (banner) {
                    banner.style.backgroundColor = '#10b981';
                    banner.innerHTML = '<i class="bi bi-wifi me-2"></i>Network Connection Restored.';
                    setTimeout(function() {
                        if (banner) {
                            banner.remove();
                            banner = null;
                        }
                    }, 2500);
                }
            }
        }
        window.addEventListener('online', updateOnlineStatus);
        window.addEventListener('offline', updateOnlineStatus);
        if (!navigator.onLine) {
            updateOnlineStatus();
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', function() {
            initFlashToasts();
            initNetworkBanner();
        });
    } else {
        initFlashToasts();
        initNetworkBanner();
    }
})();
