import os
import re
import io
from PIL import Image

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

try:
    import pypdf
except ImportError:
    pypdf = None

try:
    import pytesseract
except ImportError:
    pytesseract = None


# Explicit Skills Headings required for standard ATS resume verification
SKILLS_SECTION_PATTERNS = [
    r'\bskills\b', r'\btechnical\s+skills\b', r'\btech\s+stack\b', r'\btechnologies\b',
    r'\bcore\s+competencies\b', r'\bkey\s+skills\b', r'\bskills\s*&\s*expertise\b',
    r'\bareas\s+of\s+expertise\b', r'\btechnical\s+proficiencies\b', r'\btools\s*&\s*technologies\b',
    r'\bprogramming\s+languages\b', r'\bsoftware\s+skills\b', r'\bhard\s+skills\b',
    r'\bframeworks\s*&\s*libraries\b', r'\bdeveloper\s+skills\b', r'\btechnical\s+summary\b'
]

# Standard resume section headings
EXPERIENCE_SECTION_PATTERNS = [
    r'\bexperience\b', r'\bwork\s+experience\b', r'\bprofessional\s+experience\b',
    r'\bwork\s+history\b', r'\bemployment\s+history\b', r'\bcareer\s+history\b',
    r'\bemployment\b', r'\binternship\b', r'\binternships\b'
]

EDUCATION_SECTION_PATTERNS = [
    r'\beducation\b', r'\bacademic\s+background\b', r'\bacademic\s+history\b',
    r'\bqualifications\b', r'\bacademic\s+qualifications\b', r'\bdegrees?\b',
    r'\buniversity\b', r'\bcollege\b', r'\bbachelor\b', r'\bmaster\b'
]

OTHER_RESUME_SECTION_PATTERNS = [
    r'\bprojects\b', r'\bkey\s+projects\b', r'\bportfolio\b', r'\bcertifications\b',
    r'\bcertificates\b', r'\blicenses\b', r'\bachievements\b', r'\bawards\b',
    r'\bcontact\b', r'\bsummary\b', r'\bprofessional\s+summary\b', r'\bexecutive\s+summary\b',
    r'\bprofile\b', r'\babout\s+me\b', r'\bobjective\b', r'\bcareer\s+objective\b'
]

# Comprehensive Skill Lexicon across Tech, Data, Cloud, Design, Finance, and Management
SKILL_LEXICON = {
    # Programming & Web
    'python': ['python', 'py'],
    'javascript': ['javascript', 'js', 'es6', 'ecmascript'],
    'typescript': ['typescript', 'ts'],
    'react': ['react', 'react.js', 'reactjs'],
    'next.js': ['next.js', 'nextjs', 'next js'],
    'vue': ['vue', 'vue.js', 'vuejs'],
    'angular': ['angular', 'angularjs'],
    'node.js': ['node.js', 'nodejs', 'node js', 'node'],
    'express': ['express', 'express.js', 'expressjs'],
    'flask': ['flask'],
    'django': ['django', 'django rest framework', 'drf'],
    'fastapi': ['fastapi', 'fast-api'],
    'html5': ['html5', 'html'],
    'css3': ['css3', 'css', 'sass', 'scss'],
    'tailwind css': ['tailwind css', 'tailwind', 'tailwindcss'],
    'bootstrap': ['bootstrap'],
    'rest api': ['rest api', 'restful', 'restful apis', 'rest apis', 'web api', 'endpoints'],
    'graphql': ['graphql'],
    
    # Databases & Caching
    'sql': ['sql', 'ansi sql', 't-sql', 'pl/sql'],
    'postgresql': ['postgresql', 'postgres', 'psql'],
    'mysql': ['mysql'],
    'sqlite': ['sqlite', 'sqlite3'],
    'mongodb': ['mongodb', 'mongo'],
    'redis': ['redis'],
    
    # Cloud, DevOps & Tools
    'docker': ['docker', 'containerization', 'containers'],
    'kubernetes': ['kubernetes', 'k8s'],
    'aws': ['aws', 'amazon web services', 'ec2', 's3', 'lambda'],
    'google cloud': ['google cloud', 'gcp', 'google cloud platform'],
    'azure': ['azure', 'microsoft azure'],
    'ci/cd': ['ci/cd', 'ci cd', 'continuous integration', 'github actions', 'jenkins', 'gitlab ci'],
    'git': ['git', 'github', 'gitlab', 'version control'],
    'linux': ['linux', 'ubuntu', 'debian', 'centos', 'bash', 'shell scripting'],
    'terraform': ['terraform', 'iac'],
    
    # AI, ML & Data Analytics
    'machine learning': ['machine learning', 'ml', 'deep learning', 'supervised learning', 'unsupervised learning'],
    'deep learning': ['deep learning', 'neural networks', 'cnn', 'rnn', 'transformers', 'llms', 'llm'],
    'pytorch': ['pytorch', 'torch'],
    'tensorflow': ['tensorflow', 'keras'],
    'scikit-learn': ['scikit-learn', 'sklearn'],
    'pandas': ['pandas'],
    'numpy': ['numpy'],
    'data analysis': ['data analysis', 'data analytics', 'exploratory data analysis', 'eda', 'analytics'],
    'power bi': ['power bi', 'powerbi', 'dax', 'power query'],
    'tableau': ['tableau'],
    'excel': ['excel', 'advanced excel', 'ms excel', 'vlookup', 'pivot tables', 'spreadsheets'],
    'statistics': ['statistics', 'statistical modeling', 'hypothesis testing', 'probability'],
    'natural language processing': ['nlp', 'natural language processing', 'spacy', 'nltk', 'huggingface'],
    
    # UI/UX & Design
    'ui/ux': ['ui/ux', 'ui / ux', 'ui design', 'ux design', 'user interface', 'user experience'],
    'figma': ['figma'],
    'wireframing': ['wireframing', 'wireframes', 'mockups'],
    'prototyping': ['prototyping', 'interactive prototypes', 'prototype'],
    'design systems': ['design systems', 'design system', 'design tokens', 'component library'],
    'user research': ['user research', 'user interviews', 'usability testing', 'heuristics'],
    
    # Engineering & Management
    'agile': ['agile', 'scrum', 'kanban', 'sprint planning'],
    'jira': ['jira'],
    'problem solving': ['problem solving', 'critical thinking', 'analytical thinking'],
    'leadership': ['leadership', 'team leadership', 'mentorship'],
}


def extract_text_from_file(file_storage):
    """
    Extracts plain text from PDF or image files (PNG, JPG, JPEG).
    Returns (extracted_text, error_message).
    """
    filename = (file_storage.filename or '').lower()
    file_bytes = file_storage.read()
    file_storage.seek(0)

    if not file_bytes:
        return "", "Uploaded file is empty. Please upload a valid document."

    extracted_text = ""

    # 1. PDF Processing
    if filename.endswith('.pdf'):
        if pdfplumber:
            try:
                with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                    pages_text = []
                    for page in pdf.pages:
                        txt = page.extract_text()
                        if txt:
                            pages_text.append(txt)
                    extracted_text = "\n".join(pages_text).strip()
            except Exception:
                extracted_text = ""

        if not extracted_text and pypdf:
            try:
                reader = pypdf.PdfReader(io.BytesIO(file_bytes))
                pages_text = []
                for page in reader.pages:
                    txt = page.extract_text()
                    if txt:
                        pages_text.append(txt)
                extracted_text = "\n".join(pages_text).strip()
            except Exception:
                pass

    # 2. Image Processing (PNG, JPG, JPEG)
    elif any(filename.endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.webp']):
        try:
            img = Image.open(io.BytesIO(file_bytes))
            if pytesseract:
                try:
                    extracted_text = pytesseract.image_to_string(img).strip()
                except Exception:
                    extracted_text = ""
        except Exception as e:
            return "", f"Could not process image file: {str(e)}"

    # Clean and normalize whitespace
    extracted_text = re.sub(r'[ \t]+', ' ', extracted_text)
    extracted_text = re.sub(r'\n{3,}', '\n\n', extracted_text).strip()

    return extracted_text, None


def validate_resume_structure(text):
    """
    Evaluates whether the extracted text represents an authentic, ATS-parseable resume.
    Detects fake documents, invoices, random images, certificates only, or unformatted text.
    """
    REJECTION_ERROR = (
        "It seems like the uploaded file is not a resume. "
        "If it is, then it must include headings like Skills, Technical Skills, Tech Stack, "
        "Work Experience, and Education so ATS parsers can read it properly."
    )

    if not text or len(text.strip()) < 80:
        return False, REJECTION_ERROR

    clean_text = text.lower()
    words = re.findall(r'\b[a-zA-Z]{2,}\b', clean_text)
    if len(words) < 25:
        return False, REJECTION_ERROR

    # Check 1: Mandatory Skills Heading OR Detected Technical Skills
    has_skills_heading = any(re.search(pattern, clean_text) for pattern in SKILLS_SECTION_PATTERNS)
    
    # Check 2: Experience Heading
    has_exp_heading = any(re.search(pattern, clean_text) for pattern in EXPERIENCE_SECTION_PATTERNS)

    # Check 3: Education Heading
    has_edu_heading = any(re.search(pattern, clean_text) for pattern in EDUCATION_SECTION_PATTERNS)

    # Check 4: Contact info (Email / Phone / URLs)
    has_email = bool(re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', clean_text))
    has_phone = bool(re.search(r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', clean_text) or re.search(r'03\d{2}[-\s]?\d{7}', clean_text))
    has_contact = has_email or has_phone

    # Check 5: Recognized skills count
    detected_skills_count = sum(
        1 for skill_canon, synonyms in SKILL_LEXICON.items()
        if any(re.search(r'\b' + re.escape(syn) + r'\b', clean_text) for syn in synonyms)
    )

    # Strict Rule: Must have Skills section/skills AND at least one other core section (Experience or Education or Contact)
    has_core_sections = (has_skills_heading or detected_skills_count >= 2) and (has_exp_heading or has_edu_heading or has_contact)

    if not has_core_sections:
        return False, REJECTION_ERROR

    return True, None


def extract_skills_from_text(resume_text):
    """
    Extracts all recognized technical and functional skills present in the resume text.
    """
    resume_lower = resume_text.lower()
    extracted = []

    for canonical_name, aliases in SKILL_LEXICON.items():
        for alias in aliases:
            pattern = r'\b' + re.escape(alias) + r'\b'
            if re.search(pattern, resume_lower):
                # Capitalize nicely
                if canonical_name in ['sql', 'html5', 'css3', 'aws', 'ci/cd', 'ui/ux']:
                    extracted.append(canonical_name.upper())
                elif canonical_name in ['node.js', 'next.js', 'vue', 'react']:
                    extracted.append(canonical_name.title())
                else:
                    extracted.append(canonical_name.title())
                break

    return list(dict.fromkeys(extracted))


def calculate_resume_job_match(resume_text, job):
    """
    Performs comprehensive, enterprise-grade ATS evaluation against target job.
    STRICT RULE: Matches against the exact requirements of THIS job.
    """
    resume_lower = resume_text.lower()
    job_title = (job.title or '').strip()
    job_desc = (job.description or '').lower()
    job_reqs = (job.requirements or '').lower()

    # 1. Collect Job Required & Preferred Skills
    job_skills_list = []
    if hasattr(job, 'skills') and job.skills:
        try:
            job_skills_list = [s.skill_name.strip() for s in job.skills if s.skill_name]
        except Exception:
            job_skills_list = []

    # Parse additional keywords from job description & requirements
    parsed_skills = []
    for canonical_name, aliases in SKILL_LEXICON.items():
        for alias in aliases:
            if alias in job_desc or alias in job_reqs or alias in job_title.lower():
                display_name = canonical_name.upper() if canonical_name in ['sql', 'aws', 'ci/cd', 'ui/ux'] else canonical_name.title()
                if not any(display_name.lower() == s.lower() for s in job_skills_list):
                    parsed_skills.append(display_name)
                break

    combined_job_skills = list(dict.fromkeys(job_skills_list + parsed_skills))
    if not combined_job_skills:
        combined_job_skills = [job_title]

    # 2. Strict Skill Matching via Lexicon
    matched_skills = []
    missing_skills = []

    for skill in combined_job_skills:
        s_clean = skill.lower()
        aliases = [s_clean]
        
        # Check if in skill lexicon
        for c_name, c_aliases in SKILL_LEXICON.items():
            if s_clean in c_aliases or c_name == s_clean or s_clean in c_name:
                aliases.extend(c_aliases)
                break

        is_matched = any(re.search(r'\b' + re.escape(syn) + r'\b', resume_lower) for syn in aliases)

        if is_matched:
            matched_skills.append(skill)
        else:
            missing_skills.append(skill)

    total_required = len(combined_job_skills)
    hard_skills_ratio = len(matched_skills) / max(total_required, 1)
    hard_skills_score = hard_skills_ratio * 100

    # 3. Job Title & Domain Alignment
    title_words = [
        w for w in re.findall(r'\w+', job_title.lower())
        if len(w) > 3 and w not in ['senior', 'lead', 'junior', 'staff', 'specialist', 'developer', 'engineer', 'manager']
    ]
    title_matches = sum(1 for w in title_words if w in resume_lower)
    title_relevance_score = (title_matches / max(len(title_words), 1)) * 100 if title_words else 65

    # 4. ATS Formatting & Document Health
    has_contact = bool(re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', resume_lower))
    has_skills_hdr = any(re.search(p, resume_lower) for p in SKILLS_SECTION_PATTERNS)
    has_exp_hdr = any(re.search(p, resume_lower) for p in EXPERIENCE_SECTION_PATTERNS)
    has_edu_hdr = any(re.search(p, resume_lower) for p in EDUCATION_SECTION_PATTERNS)
    has_bullets = bool(re.search(r'[•\-\*]\s+', resume_text))

    ats_checks = [has_contact, has_skills_hdr, has_exp_hdr, has_edu_hdr, has_bullets]
    ats_health_pct = int((sum(1 for c in ats_checks if c) / len(ats_checks)) * 100)

    # 5. Composite Weighted ATS Score Calculation
    # 60% Hard Skills Match + 25% Domain/Title Match + 15% ATS Document Structure
    raw_match_percentage = int(round(
        (hard_skills_score * 0.60) +
        (title_relevance_score * 0.25) +
        (ats_health_pct * 0.15)
    ))

    # If the candidate has 0 matched skills, clamp to very low (< 15%)
    if len(matched_skills) == 0:
        match_percentage = min(raw_match_percentage, 14)
    else:
        match_percentage = max(15, min(raw_match_percentage, 98))

    # Badge assignment
    if match_percentage >= 75:
        badge_color = 'green'
        badge_label = 'High ATS Match / Top Tier Candidate'
    elif match_percentage >= 45:
        badge_color = 'orange'
        badge_label = 'Moderate Match / Key Skill Gaps'
    else:
        badge_color = 'red'
        badge_label = 'Low ATS Match / High Rejection Risk'

    candidate_all_skills = extract_skills_from_text(resume_text)

    return {
        "match_percentage": match_percentage,
        "badge_color": badge_color,
        "badge_label": badge_label,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "combined_job_skills": combined_job_skills,
        "candidate_all_skills": candidate_all_skills,
        "ats_health_pct": ats_health_pct,
        "ats_checklist": {
            "contact_info": has_contact,
            "skills_section": has_skills_hdr,
            "experience_section": has_exp_hdr,
            "education_section": has_edu_hdr,
            "bullet_points": has_bullets
        }
    }

