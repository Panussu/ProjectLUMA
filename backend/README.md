# LUMA Backend

The backend owns authentication, users, jobs, database records, private AI-service calls, and result images.

Completed result images can be downloaded either through the expiring signed URL returned with a job or with the owner's `Authorization: Bearer <token>` header. A different user's bearer token never grants access to the image.

## Development

```powershell
python -m venv .venv
./.venv/Scripts/pip.exe install -r requirements.txt
Copy-Item .env.example .env
./.venv/Scripts/python.exe run.py
```

SQLite is created automatically under `backend/data`. Set `DATABASE_URL` to move to PostgreSQL.

## PC 3 on the classroom VLAN

For the three-computer demonstration, PC 3 runs Flask and owns the SQLite database, uploaded images, and generated results. Start from the VLAN example:

```powershell
Copy-Item .env.vlan.example .env
python run.py
```

Confirm the three addresses with `ipconfig` before editing `.env`. The proposed topology is Nginx on `192.168.1.10`, Flask on `192.168.1.20:5000`, and the FastAPI AI wrapper on `192.168.1.30:8000`. The `AI_SERVICE_TOKEN` value must exactly match PC 1. Allow inbound TCP port `5000` from PC 2.

`DEPLOYMENT_MODE=vlan` enables startup safety checks. Replace every example secret with a different random value of at least 32 characters, keep `FLASK_DEBUG=0`, set an explicit frontend origin, and point `AI_SERVICE_URL` at the AI computer. The backend refuses to start when any of these checks fail.

The first version uses an in-process thread pool for jobs. Run one backend process for the classroom demonstration. For multiple backend processes, replace it with a shared queue such as Celery or RQ before scaling.

