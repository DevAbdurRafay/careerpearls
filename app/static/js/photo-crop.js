(function () {
    var cropper = null;
    var activeFileInput = null;
    var activeHiddenField = null;
    var activePreview = null;
    var activeSaveBtn = null;
    var activeForm = null;

    function getModal() {
        return document.getElementById('photoCropModal');
    }

    function getCropImage() {
        return document.getElementById('photoCropImage');
    }

    function destroyCropper() {
        if (cropper) {
            cropper.destroy();
            cropper = null;
        }
    }

    function updatePreview(dataUrl) {
        if (activePreview) {
            activePreview.innerHTML = '<img src="' + dataUrl + '" alt="Profile preview" class="profile-avatar rounded-circle w-100 h-100" style="object-fit:cover;">';
        }
        var wizard = document.getElementById('wizardAvatarPreview');
        if (wizard) {
            wizard.innerHTML = '<img src="' + dataUrl + '" alt="Profile preview" style="width:100%;height:100%;object-fit:cover;border-radius:50%;">';
        }
    }

    function openCropper(file) {
        var modalEl = getModal();
        var cropImg = getCropImage();
        if (!modalEl || !cropImg || !file) return;

        var reader = new FileReader();
        reader.onload = function (event) {
            destroyCropper();
            cropImg.src = event.target.result;
            var modal = bootstrap.Modal.getOrCreateInstance(modalEl);
            modal.show();
            cropImg.onload = function () {
                try {
                    destroyCropper();
                    cropper = new Cropper(cropImg, {
                        aspectRatio: 1,
                        viewMode: 1,
                        dragMode: 'move',
                        autoCropArea: 1,
                        responsive: true,
                        background: false,
                    });
                } catch (e) {
                    console.error('Cropper initialization error:', e);
                    alert('Failed to initialize image cropper. Please try a different image.');
                    if (modal) {
                        modal.hide();
                    }
                }
            };
            cropImg.onerror = function() {
                console.error('Image load error');
                alert('Failed to load the image. Please try a different file.');
                if (modal) {
                    modal.hide();
                }
                // Fallback: try to submit the form directly with the file
                if (activeForm && activeFileInput && activeFileInput.files[0]) {
                    // Create a new file input to replace the original
                    var newInput = document.createElement('input');
                    newInput.type = 'file';
                    newInput.name = 'logo';
                    newInput.files = activeFileInput.files;
                    activeForm.appendChild(newInput);
                    // Remove the cropped_image field since we're using direct upload
                    if (activeHiddenField) {
                        activeHiddenField.value = '';
                    }
                    // Submit the form
                    activeForm.submit();
                }
            };
        };
        reader.onerror = function() {
            console.error('File reader error');
            alert('Failed to read the file. Please try again.');
        };
        reader.readAsDataURL(file);
    }

    function bindTriggers() {
        document.querySelectorAll('[data-photo-crop-trigger]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var inputId = btn.getAttribute('data-photo-crop-trigger');
                var input = document.getElementById(inputId);
                if (input) input.click();
            });
        });

        document.querySelectorAll('[data-photo-crop-input]').forEach(function (input) {
            input.addEventListener('change', function () {
                if (!input.files || !input.files[0]) return;
                activeFileInput = input;
                activeForm = input.closest('[data-photo-crop-form]') || input.closest('form');
                activeHiddenField = activeForm ? (activeForm.querySelector('[name="cropped_image"]') || activeForm.querySelector('input[type="hidden"]#companyLogoCropped')) : null;
                
                activePreview = document.getElementById('companyLogoPreview')
                    || document.getElementById('photoUploadPreview')
                    || document.getElementById('profilePhotoPreview')
                    || document.getElementById('wizardAvatarPreview')
                    || (activeForm ? activeForm.querySelector('[data-photo-preview]') : null);

                activeSaveBtn = document.getElementById('companyLogoSave')
                    || document.getElementById('profilePhotoSave')
                    || (activeForm ? activeForm.querySelector('[type="submit"]') : null);

                console.log('Photo crop initialized:', {
                    inputId: input.id,
                    formId: activeForm ? activeForm.id : 'no form',
                    hiddenField: activeHiddenField ? activeHiddenField.id : 'no hidden field',
                    preview: activePreview ? activePreview.id : 'no preview',
                    saveBtn: activeSaveBtn ? activeSaveBtn.id : 'no save button'
                });

                openCropper(input.files[0]);
                input.value = '';
            });
        });

        var confirmBtn = document.getElementById('photoCropConfirm');
        if (confirmBtn) {
            confirmBtn.addEventListener('click', function () {
                if (!cropper) return;
                try {
                    var canvas = cropper.getCroppedCanvas({
                        width: 400,
                        height: 400,
                        imageSmoothingQuality: 'high',
                    });
                    if (!canvas) {
                        alert('Failed to crop the image. Please try again.');
                        return;
                    }
                    var dataUrl = canvas.toDataURL('image/jpeg', 0.92);
                    if (activeHiddenField) {
                        activeHiddenField.value = dataUrl;
                    }
                    updatePreview(dataUrl);
                    if (activeSaveBtn) {
                        activeSaveBtn.style.display = 'inline-flex';
                    }
                    destroyCropper();
                    var modalEl = getModal();
                    if (modalEl) {
                        bootstrap.Modal.getInstance(modalEl).hide();
                    }
                    // If the form has an auto-save attribute or company logo form, submit automatically or show save button
                    if (activeForm && activeForm.id === 'companyLogoFormAuto') {
                        activeForm.submit();
                    }
                } catch (e) {
                    console.error('Crop confirmation error:', e);
                    alert('Failed to process the cropped image. Please try again.');
                }
            });
        }

        var modalEl = getModal();
        if (modalEl) {
            modalEl.addEventListener('hidden.bs.modal', destroyCropper);
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', bindTriggers);
    } else {
        bindTriggers();
    }
})();
