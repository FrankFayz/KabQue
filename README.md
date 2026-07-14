# KabQue

Priority queue for **Kabale University** fresher document approval.

Students register on campus (GPS-checked) with their admission registration number, join a FIFO queue, and receive email/SMS with a secret code when the admin schedules their approval day.

## Stack

- **Frontend:** React (Vite)
- **Backend:** Django REST Framework + JWT
- **Database:** PostgreSQL (Neon)

## Quick start

### 1. Backend

```powershell
cd C:\Users\hp\Documents\PROJECTS\Queue_System
.\.venv\Scripts\Activate.ps1
cd backend
python manage.py runserver 127.0.0.1:8000
```

API: `http://127.0.0.1:8000/api/`

Default admin (change after first login):

- username: `admin`
- password: `admin123`

### 2. Frontend

```powershell
cd C:\Users\hp\Documents\PROJECTS\Queue_System\frontend
npm run dev
```

App: `http://127.0.0.1:5173`

## Student flow

1. Arrive on Kikungiri campus
2. Open KabQue → **Register on campus**
3. Enter reg. number, name, email and/or phone, password
4. Browser shares GPS — must be within ~800m of campus
5. Account is created and student is added to the priority queue
6. When notified, student sees the **secret code** and scheduled date
7. At the desk, student gives the code to the admin for check-in / verification

## Admin flow

1. Sign in as admin
2. Set batch size + approval date → **Send notifications**
3. At the desk, enter the student's secret code → confirm identity
4. Mark documents **approved** / **rejected** / **no-show**

## Configuration

Secrets live in `backend/.env` (not committed):

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Neon Postgres connection |
| `CAMPUS_LATITUDE` / `CAMPUS_LONGITUDE` | Kikungiri campus centre |
| `CAMPUS_RADIUS_METERS` | Geofence radius (default 800) |
| `GPS_ENFORCEMENT` | `True`/`False` — set `False` only for off-campus testing |
| `AFRICAS_TALKING_USERNAME` / `API_KEY` | Real SMS (optional; otherwise SMS is printed in the server console) |

Emails use Django's console backend in development (messages appear in the `runserver` terminal).

## Security note

If a database password was shared in chat or committed by mistake, **rotate it in the Neon dashboard** and update `backend/.env`.
