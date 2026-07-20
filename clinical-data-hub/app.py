"""
Enterprise Clinical Data Hub
----------------------------
A simple-base full-stack reference implementation: Flask + SQLAlchemy + SQLite,
server-rendered templates, session auth, role-based access control (RBAC),
and an audit trail for every write action — the baseline shape of a real
clinical data system without external services or a build step.

Run:
    pip install -r requirements.txt
    python app.py
Then open http://localhost:5000  (seeded users: admin/admin123, doctor/doctor123, nurse/nurse123)
"""
import os
from datetime import datetime, date
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for,
                    session, flash, abort)

from models import db, log_action, User, Patient, Visit, LabResult, AuditLog, ROLES

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INSTANCE_DIR = os.path.join(BASE_DIR, "instance")
os.makedirs(INSTANCE_DIR, exist_ok=True)

app = Flask(__name__)
app.config["SECRET_KEY"] = "dev-secret-change-me-in-production"
app.config["SQLALCHEMY_DATABASE_URI"] = f"sqlite:///{os.path.join(INSTANCE_DIR, 'clinical_hub.db')}"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db.init_app(app)


# --------------------------------------------------------------------------
# Auth helpers / RBAC
# --------------------------------------------------------------------------
def current_user():
    uid = session.get("user_id")
    return User.query.get(uid) if uid else None


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def roles_required(*allowed_roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = current_user()
            if not user:
                return redirect(url_for("login", next=request.path))
            if user.role not in allowed_roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapped
    return decorator


@app.context_processor
def inject_globals():
    return {"current_user": current_user(), "current_year": datetime.utcnow().year}


# --------------------------------------------------------------------------
# Auth routes
# --------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user():
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = User.query.filter_by(username=username).first()

        if user and user.is_active and user.check_password(password):
            session["user_id"] = user.id
            log_action(user, "LOGIN", "User", user.id, "Successful login", request.remote_addr)
            flash(f"Welcome back, {user.full_name}.", "success")
            next_url = request.args.get("next") or url_for("dashboard")
            return redirect(next_url)

        log_action(None, "LOGIN_FAILED", "User", None, f"Failed login for '{username}'", request.remote_addr)
        flash("Invalid username or password.", "error")

    return render_template("login.html")


@app.route("/logout")
def logout():
    user = current_user()
    if user:
        log_action(user, "LOGOUT", "User", user.id, "User logged out", request.remote_addr)
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("login"))


# --------------------------------------------------------------------------
# Dashboard
# --------------------------------------------------------------------------
@app.route("/")
@login_required
def dashboard():
    total_patients = Patient.query.count()
    critical_patients = Patient.query.filter_by(status="Critical").count()
    active_patients = Patient.query.filter_by(status="Active").count()
    recent_visits = Visit.query.order_by(Visit.visit_date.desc()).limit(6).all()
    critical_labs = (LabResult.query.filter_by(flag="Critical")
                      .order_by(LabResult.collected_at.desc()).limit(6).all())
    recent_patients = Patient.query.order_by(Patient.created_at.desc()).limit(6).all()

    return render_template(
        "dashboard.html",
        total_patients=total_patients,
        critical_patients=critical_patients,
        active_patients=active_patients,
        recent_visits=recent_visits,
        critical_labs=critical_labs,
        recent_patients=recent_patients,
    )


# --------------------------------------------------------------------------
# Patients — list / create / view / edit / delete
# --------------------------------------------------------------------------
@app.route("/patients")
@login_required
def patients_list():
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")

    query = Patient.query
    if q:
        like = f"%{q}%"
        query = query.filter(
            db.or_(Patient.first_name.ilike(like),
                   Patient.last_name.ilike(like),
                   Patient.mrn.ilike(like))
        )
    if status:
        query = query.filter_by(status=status)

    patients = query.order_by(Patient.created_at.desc()).all()
    return render_template("patients.html", patients=patients, q=q, status=status)


@app.route("/patients/new", methods=["GET", "POST"])
@roles_required("admin", "doctor", "nurse")
def patient_new():
    if request.method == "POST":
        mrn = request.form.get("mrn").strip()
        if Patient.query.filter_by(mrn=mrn).first():
            flash(f"MRN '{mrn}' already exists.", "error")
            return render_template("patient_form.html", patient=None, form=request.form)

        p = Patient(
            mrn=mrn,
            first_name=request.form.get("first_name", "").strip(),
            last_name=request.form.get("last_name", "").strip(),
            date_of_birth=datetime.strptime(request.form.get("date_of_birth"), "%Y-%m-%d").date(),
            sex=request.form.get("sex", "U"),
            blood_type=request.form.get("blood_type", ""),
            phone=request.form.get("phone", ""),
            email=request.form.get("email", ""),
            address=request.form.get("address", ""),
            allergies=request.form.get("allergies", ""),
            primary_condition=request.form.get("primary_condition", ""),
            status=request.form.get("status", "Active"),
            created_by_id=current_user().id,
        )
        db.session.add(p)
        db.session.commit()
        log_action(current_user(), "CREATE", "Patient", p.id, f"Created patient {p.full_name} ({p.mrn})",
                   request.remote_addr)
        flash(f"Patient {p.full_name} created.", "success")
        return redirect(url_for("patient_detail", patient_id=p.id))

    return render_template("patient_form.html", patient=None, form={})


@app.route("/patients/<int:patient_id>")
@login_required
def patient_detail(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    return render_template("patient_detail.html", patient=patient)


@app.route("/patients/<int:patient_id>/edit", methods=["GET", "POST"])
@roles_required("admin", "doctor", "nurse")
def patient_edit(patient_id):
    patient = Patient.query.get_or_404(patient_id)

    if request.method == "POST":
        patient.first_name = request.form.get("first_name", "").strip()
        patient.last_name = request.form.get("last_name", "").strip()
        patient.date_of_birth = datetime.strptime(request.form.get("date_of_birth"), "%Y-%m-%d").date()
        patient.sex = request.form.get("sex", "U")
        patient.blood_type = request.form.get("blood_type", "")
        patient.phone = request.form.get("phone", "")
        patient.email = request.form.get("email", "")
        patient.address = request.form.get("address", "")
        patient.allergies = request.form.get("allergies", "")
        patient.primary_condition = request.form.get("primary_condition", "")
        patient.status = request.form.get("status", "Active")
        db.session.commit()
        log_action(current_user(), "UPDATE", "Patient", patient.id, f"Updated patient {patient.full_name}",
                   request.remote_addr)
        flash(f"Patient {patient.full_name} updated.", "success")
        return redirect(url_for("patient_detail", patient_id=patient.id))

    return render_template("patient_form.html", patient=patient, form={})


@app.route("/patients/<int:patient_id>/delete", methods=["POST"])
@roles_required("admin")
def patient_delete(patient_id):
    patient = Patient.query.get_or_404(patient_id)
    name, mrn = patient.full_name, patient.mrn
    db.session.delete(patient)
    db.session.commit()
    log_action(current_user(), "DELETE", "Patient", patient_id, f"Deleted patient {name} ({mrn})",
               request.remote_addr)
    flash(f"Patient {name} deleted.", "success")
    return redirect(url_for("patients_list"))


# --------------------------------------------------------------------------
# Visits
# --------------------------------------------------------------------------
@app.route("/patients/<int:patient_id>/visits/new", methods=["GET", "POST"])
@roles_required("admin", "doctor", "nurse")
def visit_new(patient_id):
    patient = Patient.query.get_or_404(patient_id)

    if request.method == "POST":
        v = Visit(
            patient_id=patient.id,
            visit_type=request.form.get("visit_type", "Outpatient"),
            clinician_id=current_user().id,
            reason=request.form.get("reason", ""),
            notes=request.form.get("notes", ""),
            diagnosis=request.form.get("diagnosis", ""),
            heart_rate=request.form.get("heart_rate") or None,
            systolic_bp=request.form.get("systolic_bp") or None,
            diastolic_bp=request.form.get("diastolic_bp") or None,
            temperature_c=request.form.get("temperature_c") or None,
            spo2=request.form.get("spo2") or None,
        )
        db.session.add(v)
        db.session.commit()
        log_action(current_user(), "CREATE", "Visit", v.id, f"Logged visit for {patient.full_name}",
                   request.remote_addr)
        flash("Visit recorded.", "success")
        return redirect(url_for("patient_detail", patient_id=patient.id))

    return render_template("visit_form.html", patient=patient)


# --------------------------------------------------------------------------
# Lab results
# --------------------------------------------------------------------------
@app.route("/patients/<int:patient_id>/labs/new", methods=["GET", "POST"])
@roles_required("admin", "doctor", "nurse")
def lab_new(patient_id):
    patient = Patient.query.get_or_404(patient_id)

    if request.method == "POST":
        lab = LabResult(
            patient_id=patient.id,
            test_name=request.form.get("test_name", "").strip(),
            result_value=request.form.get("result_value", "").strip(),
            unit=request.form.get("unit", ""),
            reference_range=request.form.get("reference_range", ""),
            flag=request.form.get("flag", "Normal"),
            ordered_by_id=current_user().id,
        )
        db.session.add(lab)
        db.session.commit()
        log_action(current_user(), "CREATE", "LabResult", lab.id,
                   f"Added lab '{lab.test_name}' for {patient.full_name}", request.remote_addr)
        flash("Lab result added.", "success")
        return redirect(url_for("patient_detail", patient_id=patient.id))

    return render_template("lab_form.html", patient=patient)


# --------------------------------------------------------------------------
# User management (admin only)
# --------------------------------------------------------------------------
@app.route("/users")
@roles_required("admin")
def users_list():
    users = User.query.order_by(User.created_at.desc()).all()
    return render_template("users.html", users=users, roles=ROLES)


@app.route("/users/new", methods=["GET", "POST"])
@roles_required("admin")
def user_new():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        if User.query.filter_by(username=username).first():
            flash(f"Username '{username}' already taken.", "error")
            return render_template("user_form.html", roles=ROLES)

        user = User(
            full_name=request.form.get("full_name", "").strip(),
            username=username,
            role=request.form.get("role", "nurse"),
            department=request.form.get("department", "General"),
        )
        user.set_password(request.form.get("password") or "changeme123")
        db.session.add(user)
        db.session.commit()
        log_action(current_user(), "CREATE", "User", user.id, f"Created user {user.username} ({user.role})",
                   request.remote_addr)
        flash(f"User {user.full_name} created.", "success")
        return redirect(url_for("users_list"))

    return render_template("user_form.html", roles=ROLES)


@app.route("/users/<int:user_id>/toggle-active", methods=["POST"])
@roles_required("admin")
def user_toggle_active(user_id):
    user = User.query.get_or_404(user_id)
    user.is_active = not user.is_active
    db.session.commit()
    log_action(current_user(), "UPDATE", "User", user.id,
               f"{'Activated' if user.is_active else 'Deactivated'} user {user.username}", request.remote_addr)
    flash(f"User {user.username} {'activated' if user.is_active else 'deactivated'}.", "success")
    return redirect(url_for("users_list"))


# --------------------------------------------------------------------------
# Audit log (admin only)
# --------------------------------------------------------------------------
@app.route("/audit-log")
@roles_required("admin")
def audit_log_view():
    entries = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(300).all()
    return render_template("audit_log.html", entries=entries)


# --------------------------------------------------------------------------
# Error handlers
# --------------------------------------------------------------------------
@app.errorhandler(403)
def forbidden(e):
    return render_template("error.html", code=403,
                            message="You don't have permission to view this page."), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404, message="That record could not be found."), 404


# --------------------------------------------------------------------------
# Database bootstrap + seed data
# --------------------------------------------------------------------------
def seed_data():
    if User.query.first():
        return  # already seeded

    admin = User(full_name="Amara Okafor", username="admin", role="admin", department="Administration")
    admin.set_password("admin123")
    doctor = User(full_name="Dr. Priya Nair", username="doctor", role="doctor", department="Internal Medicine")
    doctor.set_password("doctor123")
    nurse = User(full_name="Jordan Blake", username="nurse", role="nurse", department="General Ward")
    nurse.set_password("nurse123")
    db.session.add_all([admin, doctor, nurse])
    db.session.commit()

    patients = [
        Patient(mrn="MRN-10001", first_name="Elena", last_name="Vargas",
                date_of_birth=date(1985, 4, 12), sex="F", blood_type="O+",
                phone="+1-555-0142", email="elena.vargas@example.com",
                allergies="Penicillin", primary_condition="Type 2 Diabetes",
                status="Active", created_by_id=admin.id),
        Patient(mrn="MRN-10002", first_name="Marcus", last_name="Chen",
                date_of_birth=date(1972, 11, 3), sex="M", blood_type="A-",
                phone="+1-555-0198", email="marcus.chen@example.com",
                allergies="None known", primary_condition="Hypertension",
                status="Critical", created_by_id=doctor.id),
        Patient(mrn="MRN-10003", first_name="Aisha", last_name="Rahman",
                date_of_birth=date(1998, 7, 22), sex="F", blood_type="B+",
                phone="+1-555-0110", email="aisha.rahman@example.com",
                allergies="Latex", primary_condition="Asthma",
                status="Active", created_by_id=nurse.id),
        Patient(mrn="MRN-10004", first_name="Tomás", last_name="Silva",
                date_of_birth=date(1960, 2, 9), sex="M", blood_type="AB+",
                phone="+1-555-0173", email="tomas.silva@example.com",
                allergies="Sulfa drugs", primary_condition="Chronic Kidney Disease",
                status="Discharged", created_by_id=doctor.id),
    ]
    db.session.add_all(patients)
    db.session.commit()

    visits = [
        Visit(patient_id=patients[0].id, visit_type="Outpatient", clinician_id=doctor.id,
              reason="Routine diabetes check-up", diagnosis="Type 2 Diabetes — stable",
              notes="A1C improved since last visit. Continue current regimen.",
              heart_rate=76, systolic_bp=128, diastolic_bp=82, temperature_c=36.7, spo2=98),
        Visit(patient_id=patients[1].id, visit_type="ER", clinician_id=doctor.id,
              reason="Chest pain, shortness of breath", diagnosis="Hypertensive crisis",
              notes="Admitted for observation. Started on IV antihypertensives.",
              heart_rate=112, systolic_bp=182, diastolic_bp=110, temperature_c=37.1, spo2=94),
        Visit(patient_id=patients[2].id, visit_type="Telehealth", clinician_id=nurse.id,
              reason="Asthma follow-up", diagnosis="Mild persistent asthma",
              notes="Inhaler technique reviewed. Peak flow within target range.",
              heart_rate=80, systolic_bp=118, diastolic_bp=76, temperature_c=36.5, spo2=97),
    ]
    db.session.add_all(visits)

    labs = [
        LabResult(patient_id=patients[0].id, test_name="HbA1c", result_value="6.9",
                  unit="%", reference_range="4.0 - 5.6", flag="High", ordered_by_id=doctor.id),
        LabResult(patient_id=patients[1].id, test_name="Serum Creatinine", result_value="2.1",
                  unit="mg/dL", reference_range="0.6 - 1.3", flag="Critical", ordered_by_id=doctor.id),
        LabResult(patient_id=patients[2].id, test_name="Peak Expiratory Flow", result_value="410",
                  unit="L/min", reference_range="380 - 550", flag="Normal", ordered_by_id=nurse.id),
        LabResult(patient_id=patients[3].id, test_name="eGFR", result_value="38",
                  unit="mL/min/1.73m²", reference_range=">60", flag="Critical", ordered_by_id=doctor.id),
    ]
    db.session.add_all(labs)
    db.session.commit()


with app.app_context():
    db.create_all()
    seed_data()


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
