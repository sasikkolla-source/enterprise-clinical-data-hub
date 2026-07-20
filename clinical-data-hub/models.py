"""
Enterprise Clinical Data Hub — Data Models
-------------------------------------------
SQLAlchemy models for users, patients, visits, lab results, and the
audit trail. Kept in one module so the schema is easy to read end to end.
"""
from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()

ROLES = ("admin", "doctor", "nurse")


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    full_name = db.Column(db.String(120), nullable=False)
    username = db.Column(db.String(60), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="nurse")
    department = db.Column(db.String(80), default="General")
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def set_password(self, raw_password: str) -> None:
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password: str) -> bool:
        return check_password_hash(self.password_hash, raw_password)

    @property
    def initials(self) -> str:
        parts = self.full_name.split()
        return "".join(p[0] for p in parts[:2]).upper()


class Patient(db.Model):
    __tablename__ = "patients"

    id = db.Column(db.Integer, primary_key=True)
    mrn = db.Column(db.String(20), unique=True, nullable=False)  # Medical Record Number
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    date_of_birth = db.Column(db.Date, nullable=False)
    sex = db.Column(db.String(1), default="U")  # M / F / U
    blood_type = db.Column(db.String(4), default="")
    phone = db.Column(db.String(30), default="")
    email = db.Column(db.String(120), default="")
    address = db.Column(db.String(255), default="")
    allergies = db.Column(db.Text, default="")
    primary_condition = db.Column(db.String(160), default="")
    status = db.Column(db.String(20), default="Active")  # Active / Discharged / Critical
    admitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    created_by = db.relationship("User", foreign_keys=[created_by_id])
    visits = db.relationship("Visit", backref="patient", cascade="all, delete-orphan",
                              order_by="desc(Visit.visit_date)")
    lab_results = db.relationship("LabResult", backref="patient", cascade="all, delete-orphan",
                                   order_by="desc(LabResult.collected_at)")

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def age(self) -> int:
        today = date.today()
        dob = self.date_of_birth
        return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


class Visit(db.Model):
    __tablename__ = "visits"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    visit_date = db.Column(db.DateTime, default=datetime.utcnow)
    visit_type = db.Column(db.String(40), default="Outpatient")  # Outpatient / Inpatient / ER / Telehealth
    clinician_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    reason = db.Column(db.String(200), default="")
    notes = db.Column(db.Text, default="")
    diagnosis = db.Column(db.String(200), default="")
    heart_rate = db.Column(db.Integer)
    systolic_bp = db.Column(db.Integer)
    diastolic_bp = db.Column(db.Integer)
    temperature_c = db.Column(db.Float)
    spo2 = db.Column(db.Integer)

    clinician = db.relationship("User", foreign_keys=[clinician_id])


class LabResult(db.Model):
    __tablename__ = "lab_results"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    test_name = db.Column(db.String(120), nullable=False)
    result_value = db.Column(db.String(60), nullable=False)
    unit = db.Column(db.String(30), default="")
    reference_range = db.Column(db.String(60), default="")
    flag = db.Column(db.String(10), default="Normal")  # Normal / Low / High / Critical
    collected_at = db.Column(db.DateTime, default=datetime.utcnow)
    ordered_by_id = db.Column(db.Integer, db.ForeignKey("users.id"))

    ordered_by = db.relationship("User", foreign_keys=[ordered_by_id])


class AuditLog(db.Model):
    __tablename__ = "audit_log"

    id = db.Column(db.Integer, primary_key=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    action = db.Column(db.String(40), nullable=False)     # CREATE / UPDATE / DELETE / LOGIN / LOGIN_FAILED
    entity = db.Column(db.String(40), nullable=False)      # Patient / Visit / LabResult / User
    entity_id = db.Column(db.Integer)
    detail = db.Column(db.String(255), default="")
    ip_address = db.Column(db.String(60), default="")

    user = db.relationship("User", foreign_keys=[user_id])


def log_action(user, action, entity, entity_id=None, detail="", ip_address=""):
    entry = AuditLog(
        user_id=user.id if user else None,
        action=action,
        entity=entity,
        entity_id=entity_id,
        detail=detail,
        ip_address=ip_address,
    )
    db.session.add(entry)
    db.session.commit()
