from app import create_app, db
from app.models import User, Company, Recruiter, JobCategory, Job, JobSkill
from datetime import datetime, timedelta

app = create_app()
with app.app_context():
    rec_user = User.query.filter_by(email="analysis.workforce@gmail.com").first()
    if not rec_user:
        print("Error: analysis.workforce user not found")
        exit(1)
        
    company = Company.query.filter_by(official_email="analysis.workforce@gmail.com").first()
    if not company:
        print("Error: Analysis Workforce company not found")
        exit(1)
        
    recruiter = Recruiter.query.filter_by(user_id=rec_user.id).first()
    if not recruiter:
        print("Error: Recruiter profile not found")
        exit(1)

    eng_cat = JobCategory.query.filter_by(name='Engineering').first() or JobCategory.query.first()
    des_cat = JobCategory.query.filter_by(name='Design').first() or eng_cat
    fin_cat = JobCategory.query.filter_by(name='Finance').first() or eng_cat

    # Define 6 top-tier jobs (Without Data Scientist)
    jobs_to_create = [
        {
            'title': 'AI & Machine Learning Engineer',
            'category_id': eng_cat.id,
            'location': 'Remote',
            'salary_range': 'PKR 180,000 - 280,000 / month',
            'salary_min': 180000,
            'salary_max': 280000,
            'employment_type': 'remote',
            'experience_required': '2-4 yrs',
            'description': '<p>Join our core AI Research & Engineering team to develop production-grade deep learning models, natural language processing pipelines, and predictive analytics engines.</p><h6>Key Responsibilities:</h6><ul><li>Train and fine-tune large language models (LLMs) and transformer architectures.</li><li>Deploy low-latency inference microservices using FastAPI and Docker containers.</li><li>Collaborate with engineering leads on automated data engineering and vector embeddings.</li></ul>',
            'requirements': 'Proficiency in Python, PyTorch/TensorFlow, FastAPI, HuggingFace, Scikit-Learn, and Vector DBs.',
            'skills': ['Python', 'Machine Learning', 'PyTorch', 'TensorFlow', 'REST API']
        },
        {
            'title': 'Cloud DevOps & Kubernetes Engineer',
            'category_id': eng_cat.id,
            'location': 'Islamabad',
            'salary_range': 'PKR 160,000 - 240,000 / month',
            'salary_min': 160000,
            'salary_max': 240000,
            'employment_type': 'full_time',
            'experience_required': '3-5 yrs',
            'description': '<p>Lead our cloud infrastructure automation, continuous integration pipelines, and high-availability Kubernetes deployments across AWS and multi-cloud environments.</p><h6>Key Responsibilities:</h6><ul><li>Automate infrastructure provisioning using Terraform and Ansible.</li><li>Manage multi-cluster Kubernetes deployments, ingress controllers, and Helm charts.</li><li>Maintain Prometheus, Grafana observability, and real-time incident monitoring.</li></ul>',
            'requirements': 'Expertise with AWS, Docker, Kubernetes, Terraform, Linux, and GitHub Actions CI/CD.',
            'skills': ['Docker', 'Kubernetes', 'AWS', 'CI/CD', 'Linux']
        },
        {
            'title': 'Senior Full Stack Python Developer',
            'category_id': eng_cat.id,
            'location': 'Karachi',
            'salary_range': 'PKR 140,000 - 220,000 / month',
            'salary_min': 140000,
            'salary_max': 220000,
            'employment_type': 'full_time',
            'experience_required': '3-5 yrs',
            'description': '<p>We are seeking an experienced Senior Full Stack Python Developer to engineer scalable microservices, optimize PostgreSQL data models, and develop high-concurrency API integrations.</p><h6>Key Responsibilities:</h6><ul><li>Architect and maintain robust Flask/Django backend APIs.</li><li>Design secure RESTful endpoints and PostgreSQL relational schemas.</li><li>Build reactive frontend components using React and Tailwind CSS.</li><li>Lead code reviews, automated unit testing, and Docker deployments.</li></ul>',
            'requirements': "Bachelor's in CS/SE; 3+ years experience with Python (Flask/Django), PostgreSQL, Redis, React, and Git.",
            'skills': ['Python', 'PostgreSQL', 'React.js', 'REST API', 'Docker']
        },
        {
            'title': 'Frontend React / Next.js Engineer',
            'category_id': eng_cat.id,
            'location': 'Lahore',
            'salary_range': 'PKR 110,000 - 170,000 / month',
            'salary_min': 110000,
            'salary_max': 170000,
            'employment_type': 'full_time',
            'experience_required': '2-4 yrs',
            'description': '<p>Build modern, ultra-responsive web applications with React.js, Next.js, TypeScript, and modern CSS libraries. Collaborate with backend architects to deliver smooth, high-speed UX.</p><h6>Key Responsibilities:</h6><ul><li>Develop component-driven web applications using React and Next.js.</li><li>Integrate RESTful APIs and handle optimistic UI updates and state management.</li><li>Optimize frontend Core Web Vitals, accessibility, and responsive layouts.</li></ul>',
            'requirements': 'Proficiency in React.js, Next.js, TypeScript, HTML5, CSS3, Tailwind CSS, and RESTful APIs.',
            'skills': ['React.js', 'Next.js', 'TypeScript', 'Tailwind CSS', 'HTML5']
        },
        {
            'title': 'Senior UI/UX Product Designer',
            'category_id': des_cat.id,
            'location': 'Lahore',
            'salary_range': 'PKR 100,000 - 160,000 / month',
            'salary_min': 100000,
            'salary_max': 160000,
            'employment_type': 'full_time',
            'experience_required': '3+ yrs',
            'description': '<p>We are looking for a creative UI/UX Product Designer to conceptualize intuitive user journeys, craft comprehensive design systems, and translate complex technical requirements into elegant visual interfaces.</p><h6>Key Responsibilities:</h6><ul><li>Build interactive high-fidelity prototypes and design systems in Figma.</li><li>Conduct user interviews, usability testing, and wireframing.</li><li>Work closely with frontend engineers to ensure pixel-perfect implementation.</li></ul>',
            'requirements': 'Strong portfolio of shipped SaaS/web products; mastery of Figma, Design Tokens, wireframing, and usability heuristics.',
            'skills': ['Figma', 'UI/UX Research', 'Wireframing', 'Prototyping', 'Design Systems']
        },
        {
            'title': 'Data Analyst & BI Specialist',
            'category_id': fin_cat.id,
            'location': 'Karachi',
            'salary_range': 'PKR 90,000 - 140,000 / month',
            'salary_min': 90000,
            'salary_max': 140000,
            'employment_type': 'full_time',
            'experience_required': '2-4 yrs',
            'description': '<p>Drive data-informed business intelligence by creating interactive Power BI dashboards, automated SQL ETL workflows, and executive performance reports.</p><h6>Key Responsibilities:</h6><ul><li>Write complex SQL analytical queries, window functions, and views.</li><li>Build Power BI and Tableau dashboards with DAX calculations.</li><li>Perform exploratory data analysis and provide actionable growth insights.</li></ul>',
            'requirements': '2+ years analytical experience; advanced SQL, Power BI, Excel modeling, and statistical analysis.',
            'skills': ['SQL', 'Power BI', 'Excel', 'Statistics', 'Data Analysis']
        }
    ]

    for item in jobs_to_create:
        job = Job(
            company_id=company.id,
            posted_by=recruiter.id,
            title=item['title'],
            category_id=item['category_id'],
            location=item['location'],
            salary_range=item['salary_range'],
            salary_min=item['salary_min'],
            salary_max=item['salary_max'],
            employment_type=item['employment_type'],
            experience_required=item['experience_required'],
            description=item['description'],
            requirements=item['requirements'],
            status='active',
            approval_status='approved',
            is_hired=False,
            created_at=datetime.utcnow(),
            closes_at=datetime.utcnow() + timedelta(days=90)
        )
        db.session.add(job)
        db.session.flush()

        for s_name in item['skills']:
            db.session.add(JobSkill(job_id=job.id, skill_name=s_name))

    db.session.commit()
    print("SUCCESS: 6 Featured Jobs created for Analysis Workforce without any applications or hirings.")
