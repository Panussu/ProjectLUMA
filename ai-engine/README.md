# LUMA AI Engine

This private Flask service implements the image-provider boundary used by the LUMA backend.

The default provider creates deterministic procedural images and applies local image effects. It exists so authentication, routing, uploads, queues, storage, and UI behavior can be demonstrated without a GPU. It must not be described as a trained generative model in a report.

To connect a real model, preserve these endpoints and replace the two provider functions in `app.py`:

- `generate_development_image`
- `edit_development_image`

All non-health requests require the `X-LUMA-Service-Token` header.

Start locally:

```powershell
python -m venv .venv
./.venv/Scripts/pip.exe install -r requirements.txt
Copy-Item .env.example .env
./.venv/Scripts/python.exe app.py
```

