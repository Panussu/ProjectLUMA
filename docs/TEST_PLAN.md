# LUMA Test Plan

## Automated checks

Run from the repository root:

```powershell
python -m venv backend/.venv
./backend/.venv/Scripts/pip.exe install -r requirements-dev.txt
./backend/.venv/Scripts/python.exe -m pytest
node --check frontend/assets/app.js
docker compose config --quiet
```

The automated tests cover authentication, user isolation, request validation, generation, editing, private AI authentication, persisted job state, signed media links, and deterministic development-provider output.

## Manual browser checklist

- Layout remains usable on desktop and mobile widths.
- Keyboard focus reaches navigation, tabs, forms, modal controls, and jobs.
- Registration and login errors are visible and understandable.
- A generation shows queued/processing progress and then its image.
- A valid PNG, JPEG, or WebP can be edited.
- Invalid or oversized uploads show an error.
- Refreshing the page restores the signed-in session until its token expires.
- One account cannot see another account's jobs.
- AI outage is visible in the health badge and job error.
- A completed image can be downloaded.

## Three-computer same-VLAN acceptance test

Before testing, record the actual IPv4 address from `ipconfig` on each PC. Confirm PC 2 can reach Flask on PC 3 and PC 3 can reach FastAPI on PC 1:

```powershell
# PC 2
Test-NetConnection 192.168.1.20 -Port 5000

# PC 3
Test-NetConnection 192.168.1.30 -Port 8000
```

| Check | Expected result |
| --- | --- |
| Browser opens `192.168.1.10` | Nginx serves the LUMA frontend |
| Browser calls `/api/v1/health` | Nginx forwards to Flask |
| Flask calls FastAPI at `192.168.1.30:8000/health` | AI dependency reports `ok` |
| Generate request | HTTP 202 followed by a completed job |
| Edit request | Upload reaches Flask, then the AI computer |
| Result request | Signed `/media` URL returns the PNG |
| AI computer stopped | Backend remains reachable and reports AI unavailable |
| Invalid service token | AI service returns HTTP 401 |
| Backend computer stopped | Nginx returns a gateway error; frontend files remain reachable |

Record the VLAN name, actual addresses, test date, tester, result, and evidence before the demonstration. Do not claim the three-PC deployment works until this table is executed on the real computers.

