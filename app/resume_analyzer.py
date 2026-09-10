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


# Explicit Skills Headings required for valid resume verification
SKILLS_SECTION_PATTERNS = [
    r'\bskills\b', r'\btechnical\s+skills\b', r'\btech\s+stack\b', r'\btechnologies\b',
    r'\bcore\s+competencies\b', r'\bkey\s+skills\b', r'\bskills\s*&\s*expertise\b',
    r'\bareas\s+of\s+expertise\b', r'\btechnical\s+proficiencies\b',
    r'\btools\s*&\s*technologies\b', r'\bprogramming\s+languages\b', r'\bsoftware\s+skills\b'
]

# Other standard resume section headings
OTHER_RESUME_SECTION_PATTERNS = [
    r'\bexperience\b', r'\bwork\s+history\b', r'\bemployment\b', r'\bprofessional\s+experience\b',
    r'\beducation\b', r'\bacademic\b', r'\bqualification\b', r'\bdegree\b',
    r'\bprojects\b', r'\bportfolio\b', r'\bcertifications\b', r'\bcontact\b',
    r'\bsummary\b', r'\bprofile\b'
]


def extract_text_from_file(file_storage):
    """
    Extracts plain text from PDF or image files (PNG, JPG, JPEG).
    Returns (extracted_text, error_message).
    """
    filename = (file_storage.filename or '').lower()
    file_bytes = file_storage.read()
    file_storage.seek(0)

    if not file_bytes:
        return "", "Uploaded file is empty."

    extracted_text = ""

    # PDF Processing
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

    # Image Processing (PNG, JPG, JPEG)
    elif any(filename.endswith(ext) for ext in ['.png', '.jpg', '.jpeg']):
        try:
            img = Image.open(io.BytesIO(file_bytes))
            if pytesseract:
                try:
                    extracted_text = pytesseract.image_to_string(img).strip()
                except Exception:
                    extracted_text = ""
        except Exception as e:
            return "", f"Could not process image file: {str(e)}"

    return extracted_text, None


def validate_resume_structure(text):
    """
    Evaluates whether the extracted text represents an authentic resume.
    STRICT RULE: The document MUST include a recognizable Skills heading
    (Skills, Technical Skills, Tech Stack, etc.) and other resume anchors.
    """
    REJECTION_ERROR = "It seems like the uploaded file is not a resume. If it is, then it must include headings like Skills, Technical Skills, Tech Stack, etc."

    if not text or len(text.strip()) < 90:
        return False, REJECTION_ERROR

    clean_text = text.lower()
    words = re.findall(r'\w+', clean_text)
    if len(words) < 30:
        return False, REJECTION_ERROR

    # 1. Mandatory Check: Must contain an explicit Skills heading
    has_skills_heading = False
    for pattern in SKILLS_SECTION_PATTERNS:
        if re.search(pattern, clean_text):
            has_skills_heading = True
            break

    if not has_skills_heading:
        return False, REJECTION_ERROR

    # 2. Check for at least 1 other standard resume section (Experience, Education, Projects, Contact, Profile)
    has_other_section = False
    for pattern in OTHER_RESUME_SECTION_PATTERNS:
        if re.search(pattern, clean_text):
            has_other_section = True
            break

    # Check for email/phone contact pattern as alternative anchor
    has_contact = bool(re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', clean_text) or re.search(r'\+?\d[\d\s\-]{8,}', clean_text))

    if has_skills_heading and (has_other_section or has_contact):
        return True, None

    return False, REJECTION_ERROR


def calculate_resume_job_match(resume_text, job):
    """
    Calculates straightforward, highly accurate match score against the active job requirements.
    STRICT RULE: Only evaluates skills required for THIS specific job.
    """
    resume_lower = resume_text.lower()
    job_title = (job.title or '').strip()
    job_desc = (job.description or '').lower()
    job_reqs = (job.requirements or '').lower()

    # Collect actual skills required for the job
    job_skills_list = []
    if hasattr(job, 'skills') and job.skills:
        try:
            job_skills_list = [s.skill_name.strip() for s in job.skills if s.skill_name]
        except Exception:
            job_skills_list = []

    # Parse key tech/domain skills from job description if list is short
    parsed_skills = []
    skill_dictionary = [
        'figma', 'ui/ux', 'user research', 'wireframing', 'prototyping', 'design systems',
        'python', 'javascript', 'typescript', 'react', 'vue', 'angular', 'node', 'flask',
        'django', 'fastapi', 'sql', 'postgresql', 'mysql', 'mongodb', 'aws', 'docker',
        'kubernetes', 'ci/cd', 'linux', 'git', 'power bi', 'tableau', 'data analysis',
        'excel', 'statistics', 'machine learning', 'devops', 'cybersecurity', 'agile', 'scrum'
    ]

    for term in skill_dictionary:
        if term in job_desc or term in job_reqs or term in job_title.lower():
            if not any(term.lower() == s.lower() for s in job_skills_list):
                parsed_skills.append(term.title())

    combined_job_skills = list(dict.fromkeys(job_skills_list + parsed_skills))
    if not combined_job_skills:
        combined_job_skills = [job_title]

    # Synonyms dictionary for flexible resume matching
    SYNONYMS = {
        'sql': ['sql', 'postgresql', 'mysql', 'database', 'sqlite', 't-sql', 'pl/sql'],
        'power bi': ['power bi', 'powerbi', 'dax', 'power query'],
        'data analysis': ['data analysis', 'data analyst', 'analytics', 'statistics', 'statistical analysis', 'data analytics'],
        'excel': ['excel', 'ms excel', 'spreadsheets', 'vlookup', 'pivot tables'],
        'python': ['python', 'pandas', 'numpy'],
        'tableau': ['tableau'],
        'statistics': ['statistics', 'statistical', 'probability'],
        'machine learning': ['machine learning', 'ml', 'deep learning', 'scikit-learn']
    }

    matched_skills = []
    missing_skills = []

    for skill in combined_job_skills:
        s_clean = skill.lower()
        is_matched = bool(re.search(r'\b' + re.escape(s_clean) + r'\b', resume_lower) or s_clean in resume_lower)
        
        if not is_matched and s_clean in SYNONYMS:
            is_matched = any(syn in resume_lower for syn in SYNONYMS[s_clean])

        if is_matched:
            matched_skills.append(skill)
        else:
            missing_skills.append(skill)

    total_required = len(combined_job_skills)
    hard_skills_ratio = len(matched_skills) / max(total_required, 1)
    hard_skills_score = hard_skills_ratio * 100

    # Domain / Title Relevance
    title_words = [w for w in re.findall(r'\w+', job_title.lower()) if len(w) > 3 and w not in ['senior', 'lead', 'junior', 'staff', 'specialist']]
    title_matches = sum(1 for w in title_words if w in resume_lower)
    title_relevance_score = (title_matches / max(len(title_words), 1)) * 100 if title_words else 50

    # Composite Match Score Calculation (70% hard skills match, 30% title relevance)
    match_percentage = int(round(
        (hard_skills_score * 0.70) +
        (title_relevance_score * 0.30)
    ))
    match_percentage = max(10, min(match_percentage, 98))

    if match_percentage >= 75:
        badge_color = 'green'
        badge_label = 'High Chance of Hiring / Strong Alignment'
    elif match_percentage >= 50:
        badge_color = 'orange'
        badge_label = 'Moderate Match / Partial Skill Gaps Identified'
    else:
        badge_color = 'red'
        badge_label = 'Low Match / Critical Requirement Gaps'

    return {
        "match_percentage": match_percentage,
        "badge_color": badge_color,
        "badge_label": badge_label,
        "matched_skills": matched_skills,
        "missing_skills": missing_skills,
        "combined_job_skills": combined_job_skills
    }
