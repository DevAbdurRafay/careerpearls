import pathlib, os

# ============= landing.html =============
landing = open('app/templates/landing_new.html', 'w', encoding='utf-8')
landing.write('''<!DOCTYPE html>
<html lang="en" data-bs-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CareerPearls - Find Your Dream Career</title>
    {% include "_favicon.html" %}
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap-icons@1.11.3/font/bootstrap-icons.min.css" rel="stylesheet">
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&family=Poppins:wght@400;600;700;800&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="{{ url_for(\'static\', filename=\'css/style.css\') }}">
    <link rel="stylesheet" href="{{ url_for(\'static\', filename=\'css/flash-toast.css\') }}">
    <link rel="stylesheet" href="{{ url_for(\'static\', filename=\'css/landing.css\') }}">
</head>
<body class="landing-page">
<div class="falling-particle"></div><div class="falling-particle"></div><div class="falling-particle"></div>
<div class="falling-particle"></div><div class="falling-particle"></div><div class="falling-particle"></div>
<div class="falling-particle"></div><div class="falling-particle"></div><div class="falling-particle"></div>
<div class="falling-particle"></div>
<nav class="navbar navbar-expand-lg navbar-dark fixed-top cp-navbar cp-navbar-glass" id="landingNav">
    <div class="container-fluid px-3 px-lg-5">
        {% set brand_href = url_for("index") %}
        {% include "_navbar_brand.html" %}
        <button class="navbar-toggler border-0 px-1 py-0" type="button" data-bs-toggle="collapse" data-bs-target="#navLanding">
            <span class="navbar-toggler-icon"></span>
        </button>
        <div class="collapse navbar-collapse" id="navLanding">
            <ul class="navbar-nav mx-auto align-items-center gap-1 my-2 my-lg-0">
                <li class="nav-item"><a class="nav-link px-3" href="#features">Features</a></li>
                <li class="nav-item"><a class="nav-link px-3" href="#how-it-works">How It Works</a></li>
                <li class="nav-item"><a class="nav-link px-3" href="#featured-jobs">Jobs</a></li>
                <li class="nav-item"><a class="nav-link px-3" href="#contact">Contact</a></li>
            </ul>
            <div class="d-flex align-items-center gap-2 mt-3 mt-lg-0">
                {% if current_user.is_authenticated %}
                <a href="{% if current_user.is_admin() %}{{ url_for("admin.dashboard") }}{% elif current_user.is_employer() %}{{ url_for("employer.dashboard") }}{% else %}{{ url_for("candidate.profile") }}{% endif %}" class="btn btn-cp-primary btn-sm px-4"><i class="bi bi-speedometer2 me-1"></i>Dashboard</a>
                {% else %}
                <a href="{{ url_for("auth.login") }}" class="btn btn-cp-ghost btn-sm px-3">Sign In</a>
                <a href="{{ url_for("auth.register", role="candidate") }}" class="btn btn-cp-primary btn-sm px-4">Get Started Free</a>
                {% endif %}
            </div>
        </div>
    </div>
</nav>
''')
landing.close()
print("Step 1 done, size:", pathlib.Path('app/templates/landing_new.html').stat().st_size)
