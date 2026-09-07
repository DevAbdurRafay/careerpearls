document.addEventListener('DOMContentLoaded', () => {
    // 1. Mandatory Privacy Policy Consent Validation & Live Registration Validation
    initRegistrationLiveValidator();

    const authForms = document.querySelectorAll('.auth-form');
    authForms.forEach(form => {
        const privacyCheckbox = form.querySelector('input[name="privacy_consent"], #loginPrivacyConsent, #privacyConsent');
        if (privacyCheckbox) {
            let errorEl = form.querySelector('#privacyConsentError');
            if (!errorEl) {
                errorEl = document.createElement('div');
                errorEl.id = 'privacyConsentError';
                errorEl.className = 'invalid-feedback text-danger small mt-1 fw-semibold';
                errorEl.style.display = 'none';
                errorEl.textContent = 'Please accept the privacy policy to register or login.';
                const checkWrap = privacyCheckbox.closest('.form-check') || privacyCheckbox.parentElement;
                checkWrap.appendChild(errorEl);
            }

            privacyCheckbox.addEventListener('change', function() {
                if (this.checked) {
                    errorEl.style.display = 'none';
                    privacyCheckbox.classList.remove('is-invalid');
                }
            });

            form.addEventListener('submit', function(e) {
                if (!privacyCheckbox.checked) {
                    e.preventDefault();
                    e.stopPropagation();
                    errorEl.style.display = 'block';
                    errorEl.textContent = 'Please accept the privacy policy to register.';
                    privacyCheckbox.classList.add('is-invalid');
                    privacyCheckbox.focus();
                    return false;
                }
            });
        }
    });

    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    if (reducedMotion) {
        document.querySelectorAll('.auth-reveal, .auth-field-enter, .auth-form-enter, .auth-feature-item').forEach(el => {
            el.style.animation = 'none';
            el.style.opacity = '1';
            el.style.transform = 'none';
        });
        document.querySelectorAll('.auth-float-pill').forEach(el => {
            el.style.animation = 'none';
            el.style.opacity = '1';
        });
        return;
    }

    initTypewriter('typewriterPrimary', window.authPrimaryTaglines || [], { speed: 48, pause: 2200 });
    initTypewriter('typewriterSecondary', window.authSecondaryTaglines || [], { speed: 38, pause: 2000, delay: 500 });
    initTypewriter('heroAccent', window.authHeroAccents || [], { speed: 42, pause: 1800, delay: 300 });
    initFeatureRotators();
    initFloatTags(window.authFloatTags || []);
    initFeatureStagger();
});

function initTypewriter(elementId, phrases, opts = {}) {
    const el = document.getElementById(elementId);
    if (!el || !phrases.length) return;

    const speed = opts.speed || 55;
    const deleteSpeed = opts.deleteSpeed || 26;
    const pause = opts.pause || 2200;
    const startDelay = opts.delay || 0;

    let phraseIdx = 0;
    let charIdx = 0;
    let deleting = false;

    function tick() {
        const current = phrases[phraseIdx];
        if (!deleting) {
            el.textContent = current.substring(0, charIdx + 1);
            charIdx++;
            if (charIdx === current.length) {
                deleting = true;
                setTimeout(tick, pause);
                return;
            }
            setTimeout(tick, speed);
        } else {
            el.textContent = current.substring(0, charIdx - 1);
            charIdx--;
            if (charIdx === 0) {
                deleting = false;
                phraseIdx = (phraseIdx + 1) % phrases.length;
                setTimeout(tick, 350);
                return;
            }
            setTimeout(tick, deleteSpeed);
        }
    }

    setTimeout(tick, startDelay);
}

function initFeatureRotators() {
    document.querySelectorAll('.auth-feature-text[data-texts]').forEach((el, i) => {
        let texts;
        try {
            texts = JSON.parse(el.dataset.texts);
        } catch {
            return;
        }
        if (texts.length < 2) return;

        let idx = 0;
        el.style.transition = 'opacity 0.45s ease, transform 0.45s ease';

        setInterval(() => {
            el.style.opacity = '0';
            el.style.transform = 'translateX(-10px)';
            setTimeout(() => {
                idx = (idx + 1) % texts.length;
                el.textContent = texts[idx];
                el.style.opacity = '1';
                el.style.transform = 'translateX(0)';
            }, 450);
        }, 3400 + i * 500);
    });
}

function initFloatTags(tags) {
    const container = document.getElementById('authFloatTags');
    if (!container || !tags.length) return;

    tags.forEach((tag, i) => {
        const pill = document.createElement('span');
        pill.className = 'auth-float-pill';
        pill.textContent = tag;
        pill.style.animationDelay = `${0.1 + i * 0.12}s`;
        container.appendChild(pill);
    });
}

function initFeatureStagger() {
    document.querySelectorAll('.auth-feature-item').forEach((item, i) => {
        item.style.animationDelay = `${0.6 + i * 0.12}s`;
    });
}

function initRegistrationLiveValidator() {
    const pwInput = document.getElementById('regPassword');
    const confirmPwInput = document.getElementById('regConfirmPassword');
    const submitBtn = document.getElementById('btnRegisterSubmit');
    const privacyCheckbox = document.getElementById('privacyConsent');
    const pwStrengthWrap = document.getElementById('pwStrengthWrap');
    const pwStrengthBar = document.getElementById('pwStrengthBar');
    const pwStrengthLabel = document.getElementById('pwStrengthLabel');
    const pwRequirementHint = document.getElementById('pwRequirementHint');
    const pwMatchFeedback = document.getElementById('pwMatchFeedback');

    if (!pwInput || !confirmPwInput || !submitBtn) return;

    function validate() {
        const password = pwInput.value || '';
        const confirmPassword = confirmPwInput.value || '';
        const privacyChecked = privacyCheckbox ? privacyCheckbox.checked : true;

        // 1. Password Strength Evaluation
        let score = 0;
        const lenOk = password.length >= 8;
        const upperOk = /[A-Z]/.test(password);
        const lowerOk = /[a-z]/.test(password);
        const numOk = /[0-9]/.test(password);
        const specialOk = /[^A-Za-z0-9]/.test(password);

        if (lenOk) score++;
        if (upperOk) score++;
        if (lowerOk) score++;
        if (numOk) score++;
        if (specialOk) score++;

        const isStrong = (score === 5);

        if (password.length > 0) {
            pwStrengthWrap.style.display = 'block';
            if (score <= 2) {
                pwStrengthBar.style.width = '25%';
                pwStrengthBar.style.backgroundColor = '#ef4444';
                pwStrengthLabel.style.color = '#ef4444';
                pwStrengthLabel.textContent = 'Weak Password';
            } else if (score === 3) {
                pwStrengthBar.style.width = '55%';
                pwStrengthBar.style.backgroundColor = '#f59e0b';
                pwStrengthLabel.style.color = '#f59e0b';
                pwStrengthLabel.textContent = 'Moderate Password';
            } else if (score === 4) {
                pwStrengthBar.style.width = '80%';
                pwStrengthBar.style.backgroundColor = '#38bdf8';
                pwStrengthLabel.style.color = '#38bdf8';
                pwStrengthLabel.textContent = 'Good Password';
            } else {
                pwStrengthBar.style.width = '100%';
                pwStrengthBar.style.backgroundColor = '#22c55e';
                pwStrengthLabel.style.color = '#22c55e';
                pwStrengthLabel.textContent = 'Strong Password';
            }

            if (isStrong) {
                pwRequirementHint.className = 'cp-password-hint mt-1 mb-0 text-success fw-semibold';
                pwRequirementHint.innerHTML = '<i class="bi bi-check-circle-fill me-1"></i> Strong password requirements satisfied.';
                pwInput.classList.remove('is-invalid');
                pwInput.classList.add('is-valid');
            } else {
                pwRequirementHint.className = 'cp-password-hint mt-1 mb-0';
                pwRequirementHint.textContent = 'Must include uppercase, lowercase, a number, and a special character (min. 8 characters).';
                pwInput.classList.remove('is-valid');
            }
        } else {
            pwStrengthWrap.style.display = 'none';
            pwRequirementHint.className = 'cp-password-hint mt-1 mb-0';
            pwRequirementHint.textContent = 'Must include uppercase, lowercase, a number, and a special character (min. 8 characters).';
            pwInput.classList.remove('is-valid', 'is-invalid');
        }

        // 2. Confirm Password Match Evaluation
        let isMatch = false;
        if (confirmPassword.length > 0) {
            pwMatchFeedback.style.display = 'block';
            if (confirmPassword === password) {
                isMatch = true;
                pwMatchFeedback.className = 'small mt-1.5 fw-semibold text-success';
                pwMatchFeedback.innerHTML = '<i class="bi bi-check-circle-fill me-1"></i> Passwords match perfectly!';
                confirmPwInput.classList.remove('is-invalid');
                confirmPwInput.classList.add('is-valid');
            } else {
                isMatch = false;
                pwMatchFeedback.className = 'small mt-1.5 fw-semibold text-danger';
                pwMatchFeedback.innerHTML = '<i class="bi bi-x-circle-fill me-1"></i> Passwords do not match.';
                confirmPwInput.classList.remove('is-valid');
                confirmPwInput.classList.add('is-invalid');
            }
        } else {
            pwMatchFeedback.style.display = 'none';
            confirmPwInput.classList.remove('is-valid', 'is-invalid');
        }

        // 3. Submit Button State Control
        const canSubmit = isStrong && isMatch && privacyChecked;

        if (canSubmit) {
            submitBtn.disabled = false;
            submitBtn.style.opacity = '1';
            submitBtn.style.cursor = 'pointer';
            submitBtn.removeAttribute('title');
        } else {
            submitBtn.disabled = true;
            submitBtn.style.opacity = '0.55';
            submitBtn.style.cursor = 'not-allowed';
            let reason = [];
            if (!isStrong) reason.push('create a strong password (full green)');
            if (!isMatch) reason.push('match confirm password');
            if (!privacyChecked) reason.push('accept the Privacy Policy');
            submitBtn.setAttribute('title', 'Please ' + reason.join(', ') + ' to proceed.');
        }
    }

    pwInput.addEventListener('input', validate);
    confirmPwInput.addEventListener('input', validate);
    if (privacyCheckbox) {
        privacyCheckbox.addEventListener('change', validate);
    }

    // Initial check
    validate();
}

