/**
 * Profile Image Click-to-Enlarge Lightbox
 */
document.addEventListener('DOMContentLoaded', function () {
    // Create global lightbox modal container if not existing
    let modal = document.getElementById('cpProfileLightboxModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'cpProfileLightboxModal';
        modal.className = 'cp-lightbox-overlay';
        modal.innerHTML = `
            <div class="cp-lightbox-content">
                <button type="button" class="cp-lightbox-close" aria-label="Close">&times;</button>
                <img src="" alt="Enlarged Profile Image" class="cp-lightbox-img" id="cpLightboxImg">
            </div>
        `;
        document.body.appendChild(modal);

        const closeBtn = modal.querySelector('.cp-lightbox-close');
        const hideModal = () => modal.classList.remove('active');

        closeBtn.addEventListener('click', hideModal);
        modal.addEventListener('click', function (e) {
            if (e.target === modal) hideModal();
        });
        document.addEventListener('keydown', function (e) {
            if (e.key === 'Escape' && modal.classList.contains('active')) {
                hideModal();
            }
        });
    }

    const lightboxImg = document.getElementById('cpLightboxImg');

    // Attach click handlers to any profile image elements
    document.addEventListener('click', function (e) {
        const img = e.target.closest('.profile-avatar, .cp-wizard-avatar img, .profile-avatar-preview img, [data-profile-lightbox], .talent-avatar-img');
        if (img && img.tagName === 'IMG' && img.src && !img.src.endsWith('#')) {
            lightboxImg.src = img.src;
            modal.classList.add('active');
        }
    });
});
