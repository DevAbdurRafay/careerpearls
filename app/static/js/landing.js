// CareerPearls Landing Page JavaScript (GPU-Optimized & Passive Scroll)

document.addEventListener('DOMContentLoaded', function() {
    'use strict';

    // 1. Smooth scrolling for navigation links
    document.querySelectorAll('a[href^="#"]').forEach(function(anchor) {
        anchor.addEventListener('click', function(e) {
            var href = this.getAttribute('href');
            if (href && href !== '#' && href.startsWith('#')) {
                var target = document.querySelector(href);
                if (target) {
                    e.preventDefault();
                    target.scrollIntoView({
                        behavior: 'smooth',
                        block: 'start'
                    });
                }
            }
        });
    });

    // 2. Intersection Observer for Scroll Reveal Animations (Off-Main-Thread)
    if ('IntersectionObserver' in window) {
        var observerOptions = {
            threshold: 0.08,
            rootMargin: '0px 0px -40px 0px'
        };

        var revealObserver = new IntersectionObserver(function(entries) {
            entries.forEach(function(entry) {
                if (entry.isIntersecting) {
                    entry.target.classList.add('animate-in');
                    revealObserver.unobserve(entry.target);
                }
            });
        }, observerOptions);

        document.querySelectorAll('.feature-card, .step-card, .job-card, .lp-feature-card, .lp-step-card, .lp-company-card').forEach(function(el) {
            revealObserver.observe(el);
        });

        // Stats Counter Animation Observer
        var statsObserver = new IntersectionObserver(function(entries) {
            entries.forEach(function(entry) {
                if (entry.isIntersecting) {
                    var statValues = entry.target.querySelectorAll('.stat-band-value, .lp-band-val');
                    statValues.forEach(function(stat) {
                        var text = stat.textContent;
                        var number = parseInt(text.replace(/[^0-9]/g, ''), 10);
                        if (!isNaN(number)) {
                            animateCounter(stat, number);
                        }
                    });
                    statsObserver.unobserve(entry.target);
                }
            });
        }, { threshold: 0.3 });

        var statsBand = document.querySelector('.stats-band, .lp-stats-band');
        if (statsBand) {
            statsObserver.observe(statsBand);
        }
    }

    // High-performance RAF Counter
    function animateCounter(element, target, duration) {
        duration = duration || 1600;
        var start = 0;
        var startTime = null;

        function step(timestamp) {
            if (!startTime) startTime = timestamp;
            var progress = Math.min((timestamp - startTime) / duration, 1);
            // Ease out cubic
            var easeProgress = 1 - Math.pow(1 - progress, 3);
            var current = Math.floor(easeProgress * target);
            element.textContent = current.toLocaleString();
            if (progress < 1) {
                window.requestAnimationFrame(step);
            } else {
                element.textContent = target.toLocaleString();
            }
        }
        window.requestAnimationFrame(step);
    }

    // 3. Form Validation for Contact Form
    var contactForm = document.querySelector('.contact-form, form[action*="contact"]');
    if (contactForm) {
        contactForm.addEventListener('submit', function(e) {
            var phoneInput = this.querySelector('input[name="phone"]');
            if (phoneInput) {
                var phoneValue = phoneInput.value.replace(/\D/g, '');
                if (phoneValue.length !== 11) {
                    e.preventDefault();
                    alert('Please enter a valid 11-digit phone number');
                    phoneInput.focus();
                }
            }
        });
    }

    // 4. Mobile Menu Toggle
    var navbarToggler = document.querySelector('.navbar-toggler');
    var navbarCollapse = document.querySelector('.navbar-collapse');
    if (navbarToggler && navbarCollapse) {
        navbarToggler.addEventListener('click', function() {
            navbarCollapse.classList.toggle('show');
        });

        document.querySelectorAll('.nav-link').forEach(function(link) {
            link.addEventListener('click', function() {
                if (window.innerWidth < 992 && navbarCollapse.classList.contains('show')) {
                    navbarCollapse.classList.remove('show');
                }
            });
        });
    }
});