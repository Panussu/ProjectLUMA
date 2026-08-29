# LUMA AI Engine

This private Flask service implements the image-provider boundary used by the LUMA backend. Its normal provider is Stable Diffusion WebUI Forge installed and launched through Stability Matrix.

## Stability Matrix and Forge

1. Install the Stable Diffusion WebUI Forge package in Stability Matrix.
2. Add `--api --port 7860` to the package launch arguments.
3. Do not add `--listen` when this wrapper and Forge run on the same AI computer. Keeping Forge on localhost prevents other LAN computers from bypassing LUMA authentication.
4. Launch Forge and confirm `http://127.0.0.1:7860/docs` includes `/sdapi/v1/txt2img` and `/sdapi/v1/img2img`.
5. Copy `.env.example` to `.env`, use `AI_PROVIDER=forge`, and start this wrapper on port 8000.

The wrapper translates LUMA requests into Forge's API format, decodes the Base64 response, and returns a PNG to the backend. If Forge uses `--api-auth`, set `FORGE_USERNAME` and `FORGE_PASSWORD` in `.env`.

## Development provider

Set `AI_PROVIDER=development-procedural` to test authentication, routing, uploads, queues, storage, and UI behavior without Forge or a GPU. This provider is not a trained generative model and must not be presented as one.

All non-health requests require the `X-LUMA-Service-Token` header.

Start locally:

```powershell
python -m venv .venv
./.venv/Scripts/pip.exe install -r requirements.txt
Copy-Item .env.example .env
./.venv/Scripts/python.exe app.py
```

