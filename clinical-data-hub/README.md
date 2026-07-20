# Enterprise Clinical Data Hub

A simple-base reference implementation of a clinical data management system:
patient records, visits, lab results, role-based access control, and a full
audit trail — built with Flask, SQLAlchemy, and SQLite so it runs anywhere
with just Python (no external database or build step required).

## Features

- **Patient records** — create, search, view, edit, and (admin-only) delete
- **Visit history** — log outpatient/inpatient/ER/telehealth visits with vitals (HR, BP, temp, SpO₂)
- **Lab results** — record results with reference ranges and Normal/Low/High/Critical flags
- **Role-based access control** — `admin`, `doctor`, `nurse` roles with different permissions
- **Staff account management** — admins can create and enable/disable accounts
- **Audit log** — every create, update, delete, and login/logout is recorded with timestamp, user, and IP
- **Dashboard** — live counts, recent visits, critical lab flags, recently admitted patients

## Getting started

```bash
pip install -r requirements.txt
python app.py
```

Then open **http://localhost:5000**. The database is created and seeded automatically
on first run (`instance/clinical_hub.db`).

### Demo accounts

| Username | Password    | Role   |
|----------|-------------|--------|
| admin    | admin123    | admin  |
| doctor   | doctor123   | doctor |
| nurse    | nurse123    | nurse  |

⚠️ These are demo credentials for local evaluation only — change them (and the
Flask `SECRET_KEY` in `app.py`) before deploying anywhere real.

## Project structure

```
clinical-data-hub/
├── app.py              # Routes, auth, RBAC, seed data
├── models.py            # SQLAlchemy models + audit logging helper
├── requirements.txt
├── static/css/style.css # Design system (tokens, layout, components)
└── templates/           # Server-rendered Jinja2 pages
```

## Permissions

| Action                        | Admin | Doctor | Nurse |
|--------------------------------|:-----:|:------:|:-----:|
| View patients / dashboard      |  ✅   |  ✅    |  ✅   |
| Create / edit patients         |  ✅   |  ✅    |  ✅   |
| Log visits / lab results       |  ✅   |  ✅    |  ✅   |
| Delete patients                |  ✅   |  ❌    |  ❌   |
| Manage staff accounts          |  ✅   |  ❌    |  ❌   |
| View audit log                 |  ✅   |  ❌    |  ❌   |

## Notes on scope

This is a **base/reference implementation**, intentionally kept to a single
Flask process and SQLite for portability. For a production enterprise
deployment you'd typically add: a managed database (Postgres), HTTPS +
proper secret management, password reset/MFA, HIPAA-grade encryption at
rest and in transit, pagination on large tables, and a real deployment
target (Gunicorn/uWSGI behind a reverse proxy).
