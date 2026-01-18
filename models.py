from extensions import db
from sqlalchemy_utils import PasswordType # used for password hashing 
from datetime import datetime, timezone

class Users(db.Model):
    user_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(PasswordType(schemes=['pbkdf2_sha512']), nullable=False)
    role = db.Column(db.String(20), db.CheckConstraint("role IN ('candidate', 'recruiter')"), nullable=False)
    created_at = db.Column(db.DateTime, default= lambda: datetime.now(timezone.utc) , nullable=False)


class Candidates(db.Model):
    candidate_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), unique=True, nullable=False )
    full_name = db.Column(db.String(100), nullable=False)
    experience_years = db.Column(db.Integer)


class Recruiters(db.Model):
    recruiter_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.user_id"), unique=True, nullable=False )
    company_name = db.Column(db.String(255))


class Resumes(db.Model):
    resume_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    candidate_id = db.Column(db.Integer, db.ForeignKey("candidates.candidate_id"), nullable=False )
    resume_path = db.Column(db.String(255), nullable=False)
    uploaded_at = db.Column(db.DateTime, default= lambda: datetime.now(timezone.utc), nullable=False)
    analysis_json = db.Column(db.JSON, nullable=True)  # EXACT analyze output, anlysis of each resume

    
class Skillclaims(db.Model):
    claim_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    resume_id = db.Column(db.Integer, db.ForeignKey("resumes.resume_id"), nullable=False )
    skill_name = db.Column(db.String(100), nullable=False)


class Platforms(db.Model):
    platform_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    platform_name = db.Column(db.String(100), unique=True, nullable=False)


class ClaimVerification(db.Model): # actual tablename is Claim_verification 
    verification_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    claim_id = db.Column(db.Integer, db.ForeignKey("skillclaims.claim_id"), nullable=False) # skill kya hai
    platform_id = db.Column(db.Integer, db.ForeignKey("platforms.platform_id"), nullable=False) # skill kis platform pe hai
    evaluation_json = db.Column(db.JSON, nullable=False) # full ML response per skill per platform
    model_version = db.Column(db.String(100))
    verified_at = db.Column(db.DateTime, default= lambda: datetime.now(timezone.utc) , nullable=False)
    
    __table_args__ = (
    db.UniqueConstraint("claim_id", "platform_id"),
    )
