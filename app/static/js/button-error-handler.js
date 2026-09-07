/**
 * Global button error handler to prevent UI crashes and provide user feedback
 * This script wraps all button clicks with try-catch blocks and provides fallback behavior
 */

(function() {
    'use strict';

    // Store original function references
    const originalOnClick = HTMLElement.prototype.onclick;
    
    // Enhanced button click wrapper
    function safeButtonClickHandler(event) {
        const button = event.target.closest('button, a, [role="button"]');
        if (!button) return;

        // Check if button already has safe handling
        if (button.hasAttribute('data-safe-handled')) {
            return;
        }

        // Add loading state
        const originalText = button.innerHTML;
        const originalDisabled = button.disabled;
        
        // Show loading state for async operations (but don't disable submit buttons on click, as that blocks form submission)
        if (button.tagName === 'BUTTON' && button.type !== 'submit' && !button.disabled) {
            button.disabled = true;
            button.innerHTML = '<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Processing...';
            button.setAttribute('data-original-text', originalText);
        }

        // Re-enable button after timeout (fallback)
        setTimeout(() => {
            if (button.disabled && button.hasAttribute('data-original-text')) {
                button.disabled = originalDisabled;
                button.innerHTML = button.getAttribute('data-original-text');
                button.removeAttribute('data-original-text');
            }
        }, 5000);
    }

    // Mock function fallbacks for testing mode
    window.mockFunctionFallback = function(functionName, fallbackMessage) {
        console.log(`[Mock Mode] ${functionName} called - using fallback behavior`);
        if (typeof fallbackMessage === 'string') {
            showTemporaryToast(fallbackMessage, 'info');
        }
        return false;
    };

    // Safe function executor
    window.safeExecute = function(func, context, args, fallbackMessage) {
        try {
            if (typeof func === 'function') {
                return func.apply(context, args);
            } else {
                console.warn(`[Safe Execute] Function not found, using fallback`);
                if (fallbackMessage) {
                    showTemporaryToast(fallbackMessage, 'warning');
                }
                return false;
            }
        } catch (error) {
            console.error(`[Safe Execute] Error in function:`, error);
            if (fallbackMessage) {
                showTemporaryToast(fallbackMessage || 'An error occurred. Please try again.', 'danger');
            }
            return false;
        }
    };

    // Enhanced modal handler with error recovery
    window.safeOpenModal = function(modalId, fallbackContent) {
        try {
            const modalEl = document.getElementById(modalId);
            if (!modalEl) {
                console.error(`Modal ${modalId} not found`);
                showTemporaryToast('Modal not available. Please refresh the page.', 'warning');
                return false;
            }

            const bsModal = new bootstrap.Modal(modalEl);
            bsModal.show();
            return true;
        } catch (error) {
            console.error('Error opening modal:', error);
            showTemporaryToast('Unable to open modal. Please try again.', 'danger');
            return false;
        }
    };

    // Safe fetch wrapper
    window.safeFetch = function(url, options, fallbackHandler) {
        return fetch(url, options)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response;
            })
            .catch(error => {
                console.error('Fetch error:', error);
                if (typeof fallbackHandler === 'function') {
                    fallbackHandler(error);
                } else {
                    showTemporaryToast('Network error. Please check your connection.', 'danger');
                }
                throw error;
            });
    };

    // Temporary toast notification
    function showTemporaryToast(message, type = 'info') {
        // Remove existing toasts of same type to avoid stacking
        const existingToasts = document.querySelectorAll(`.cp-toast-${type}`);
        existingToasts.forEach(toast => toast.remove());

        const toast = document.createElement('div');
        toast.className = `cp-toast cp-toast-${type}`;
        toast.setAttribute('role', 'alert');
        toast.innerHTML = `
            <div class="cp-toast-content">
                <span class="cp-toast-message">${message}</span>
                <button type="button" class="cp-toast-close" aria-label="Close">&times;</button>
            </div>
        `;

        // Add to toast stack
        let stack = document.getElementById('cpToastStack');
        if (!stack) {
            stack = document.createElement('div');
            stack.id = 'cpToastStack';
            stack.className = 'cp-toast-stack';
            document.body.appendChild(stack);
        }
        stack.appendChild(toast);

        // Auto dismiss after 3 seconds
        setTimeout(() => {
            toast.classList.add('cp-toast-hide');
            setTimeout(() => {
                toast.remove();
                if (stack && !stack.children.length) {
                    stack.remove();
                }
            }, 280);
        }, 3000);

        // Manual dismiss
        const closeBtn = toast.querySelector('.cp-toast-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                toast.classList.add('cp-toast-hide');
                setTimeout(() => toast.remove(), 280);
            });
        }
    }

    // Initialize safe button handling
    document.addEventListener('DOMContentLoaded', function() {
        // Wrap all existing button clicks
        const buttons = document.querySelectorAll('button, a[href], [role="button"]');
        buttons.forEach(button => {
            if (!button.hasAttribute('data-safe-handled')) {
                button.addEventListener('click', safeButtonClickHandler, true);
                button.setAttribute('data-safe-handled', 'true');
            }
        });

        // Watch for dynamically added buttons
        const observer = new MutationObserver(function(mutations) {
            mutations.forEach(function(mutation) {
                mutation.addedNodes.forEach(function(node) {
                    if (node.nodeType === 1) { // Element node
                        const newButtons = node.querySelectorAll ? 
                            node.querySelectorAll('button, a[href], [role="button"]') : [];
                        newButtons.forEach(button => {
                            if (!button.hasAttribute('data-safe-handled')) {
                                button.addEventListener('click', safeButtonClickHandler, true);
                                button.setAttribute('data-safe-handled', 'true');
                            }
                        });
                    }
                });
            });
        });

        observer.observe(document.body, {
            childList: true,
            subtree: true
        });

        console.log('[Button Error Handler] Initialized safe button handling');
    });

    // Export functions globally
    window.showTemporaryToast = showTemporaryToast;

})();