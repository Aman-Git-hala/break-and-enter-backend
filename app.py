from flask import Flask, request, jsonify, session
from werkzeug.utils import secure_filename
from extensions import db
from models import *
import os
import re
import pdfplumber
import docx
import json
import requests
from requests.exceptions import Timeout, RequestException
from config import SQLALCHEMY_DATABASE_URI, SQLALCHEMY_TRACK_MODIFICATIONS
from flask_cors import CORS
import fitz
from flask_migrate import Migrate

DEMO_MODE = True 

app = Flask(__name__)
# Allow CORS for your React Frontend
# Allow ALL origins (Vercel, Localhost, etc.)
CORS(app, resources={r"/*": {"origins": "*"}})

# Ensure upload folder exists
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["SQLALCHEMY_DATABASE_URI"] = SQLALCHEMY_DATABASE_URI
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = SQLALCHEMY_TRACK_MODIFICATIONS
app.secret_key = "super_secret_key_for_hackathon"
app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False, 
    SESSION_COOKIE_HTTPONLY=True, 
    SESSION_PERMANENT=True
)

db.init_app(app)
migrate = Migrate(app, db)

# --- HELPER FUNCTIONS ---

def get_or_create_demo_user():
    demo_email = "demo@judge.com"
    user = Users.query.filter_by(email=demo_email).first()
    if not user:
        user = Users(email=demo_email, password_hash="demo", role="candidate")
        db.session.add(user)
        db.session.commit()
        candidate = Candidates(user_id=user.user_id, full_name="Demo Judge", experience_years=10)
        db.session.add(candidate)
        db.session.commit()
    return user

def extract_text_and_links(file_path):
    text = ""
    links = []
    try:
        if file_path.endswith(".pdf"):
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    text += page.extract_text() or ""
            doc = fitz.open(file_path)
            for page in doc:
                for link in page.get_links():
                    if link.get("uri"): links.append(link.get("uri"))
        elif file_path.endswith(".docx"):
            doc = docx.Document(file_path)
            for para in doc.paragraphs:
                text += para.text + "\n"
            for rel in doc.part.rels.values():
                if "http" in rel.target_ref:
                    links.append(rel.target_ref)
    except Exception as e:
        print(f"Error reading file: {e}")
    return text.lower(), links

KNOWN_SKILLS = ["python", "c", "c++", "java", "javascript", "html", "css", "sql", "flask", "django", "react", "node", "machine learning", "deep learning", "go", "golang", "rust"]

def extract_skills(text):
    found_skills = set()
    for skill in KNOWN_SKILLS:
        if re.search(r"\b" + re.escape(skill) + r"\b", text):
            found_skills.add(skill.capitalize())
    return list(found_skills)

def extract_github_username(text, links):
    match = re.search(r"github\.com/([a-zA-Z0-9_-]+)", text)
    if match: return match.group(1)
    for link in links:
        match = re.search(r"github\.com/([a-zA-Z0-9_-]+)", link)
        if match: return match.group(1)
    return None

def extract_email(text):
    match = re.search(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', text)
    return match.group(0) if match else "Not found"

def extract_phone(text):
    match = re.search(r'(\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}', text)
    return match.group(0) if match else "Not found"

def clean_extracted_text(text):
    text = re.sub(r'(?<=[a-z])(?=[A-Z])', ' ', text)
    text = re.sub(r'(?<=[a-z])\.(?=[A-Z])', '. ', text)
    text = text.strip().capitalize()
    text = re.sub(r'\s+', ' ', text)
    return text

def extract_education(text):
    keywords = ["university", "college", "institute", "b.tech", "b.sc", "degree", "technology", "bachelor", "master"]
    lines = text.split('\n')
    education_lines = []
    for line in lines:
        if any(word in line.lower() for word in keywords):
            clean = clean_extracted_text(line)
            if len(clean) > 10 and len(clean) < 120:
                education_lines.append(clean)
    return education_lines[:2]

def extract_section(text, header_keywords):
    lines = text.split('\n')
    capture = False
    captured_lines = []
    for line in lines:
        clean_line = line.strip().lower()
        if any(keyword in clean_line for keyword in header_keywords) and len(clean_line) < 40:
            capture = True
            continue
        if capture:
            if any(w in clean_line for w in ["education", "skills", "projects", "experience", "achievements", "certifications", "declaration"]):
                break
            if len(line.strip()) > 3:
                cleaned = clean_extracted_text(line)
                if len(cleaned.split()) > 1 and len(cleaned) < 200:
                    captured_lines.append(cleaned)
    return captured_lines[:5]

def parse_resume(file_path):
    text_lower, links = extract_text_and_links(file_path)
    
    raw_text_original = ""
    try:
        if file_path.endswith(".pdf"):
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    raw_text_original += page.extract_text() or ""
        elif file_path.endswith(".docx"):
            doc = docx.Document(file_path)
            for para in doc.paragraphs:
                raw_text_original += para.text + "\n"
    except:
        raw_text_original = text_lower

    if not raw_text_original: raw_text_original = text_lower

    return {
        "skills": extract_skills(text_lower),
        "github_username": extract_github_username(text_lower, links),
        "email": extract_email(text_lower),
        "phone": extract_phone(text_lower),
        "education": extract_education(raw_text_original),
        "experience": extract_section(raw_text_original, ["experience", "work history", "employment"]),
        "projects": extract_section(raw_text_original, ["projects", "personal projects"])
    }

# --- ROUTES ---

@app.route("/dashboard")
def dashboard():
    if DEMO_MODE and "user_id" not in session:
        user = get_or_create_demo_user()
        session.clear()
        session["user_id"] = user.user_id
        session["role"] = user.role
    if "user_id" not in session: return jsonify({"error": "Unauthorized"}), 401
    return jsonify({"message": "Welcome to Dashboard"})

@app.route("/analyze", methods=["POST"])
def analyze_resume():
    if DEMO_MODE and "user_id" not in session:
        user = get_or_create_demo_user()
        session["user_id"] = user.user_id

    resume_file = request.files.get("resume")
    if not resume_file: return jsonify({"error": "No resume uploaded"}), 400

    filename = secure_filename(resume_file.filename)
    path = os.path.join(UPLOAD_FOLDER, filename)
    try:
        resume_file.save(path)
    except Exception as e:
        return jsonify({"error": f"Failed to save file: {str(e)}"}), 500

    candidate = Candidates.query.filter_by(user_id=session["user_id"]).first()
    resume = Resumes(candidate_id=candidate.candidate_id, resume_path=path)
    db.session.add(resume)
    db.session.commit()

    # 1. Parse Resume
    parsed_data = parse_resume(path)
    extracted_skills = parsed_data["skills"]
    github_username = parsed_data["github_username"] or "Vishalfot" 

    # 2. Call AI
    ai_url = "https://ror-12-skill-engine.hf.space/analyze/github"
    payload = { "github_username": github_username, "skills": extracted_skills }
    final_ml_results = {}

    try:
        print(f"Calling AI for {github_username}...")
        ai_response = requests.post(ai_url, json=payload, timeout=300)
        ai_response.raise_for_status()

        raw_text = ai_response.text.strip()
        if not raw_text: raise ValueError("Empty AI response")
        
        clean_text = raw_text.replace("\n", "").strip()
        fixed_json_str = clean_text.replace("}{", "},{")
        if not fixed_json_str.startswith("["): fixed_json_str = f"[{fixed_json_str}]"
        
        stream_data = json.loads(fixed_json_str)
        for item in stream_data:
            if "status" in item: continue
            for skill, evaluation in item.items():
                final_ml_results[skill] = evaluation

    except Exception as e:
        print(f"AI Error: {e}")
        # Don't crash, just return empty skills so profile still shows
        final_ml_results = {} 

    # 3. Final Response (Profile + AI Results)
    final_response = {
        "message": "Resume analyzed successfully",
        "platform": "GitHub",
        "response": final_ml_results,
        "parsed_profile": {
            "user": github_username,
            "email": parsed_data["email"],
            "phone": parsed_data["phone"],
            "education": parsed_data["education"],
            "experience": parsed_data["experience"],
            "projects": parsed_data["projects"],
            "skills_found": extracted_skills
        }
    }
    
    resume.analysis_json = final_response
    db.session.commit()

    return jsonify(final_response), 200

if __name__ == "__main__":
    with app.app_context():
        db.create_all()  
    app.run(debug=True, port=5000)