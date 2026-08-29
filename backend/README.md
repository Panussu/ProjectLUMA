# LUMA Backend

The backend owns authentication, users, jobs, database records, private AI-service calls, and result images.

## Development

```powershell
python -m venv .venv
./.venv/Scripts/pip.exe install -r requirements.txt
Copy-Item .env.example .env
./.venv/Scripts/python.exe run.py
```

SQLite is created automatically under `backend/data`. Set `DATABASE_URL` to move to PostgreSQL.

The first version uses an in-process thread pool for jobs. Run one backend process for the classroom demonstration. For multiple backend processes, replace it with a shared queue such as Celery or RQ before scaling.

