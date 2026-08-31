# LUMA AI Engine

This private FastAPI service implements the image-provider boundary used by the LUMA backend. Its normal provider is Stable Diffusion WebUI Forge installed and launched through Stability Matrix.

## Stability Matrix and Forge

1. Install the Stable Diffusion WebUI Forge package in Stability Matrix.
2. Add `--api --port 7860` to the package launch arguments.
3. Do not add `--listen` when this wrapper and Forge run on the same AI computer. Keeping Forge on localhost prevents other LAN computers from bypassing LUMA authentication.
4. Launch Forge and confirm `http://127.0.0.1:7860/docs` includes `/sdapi/v1/txt2img` and `/sdapi/v1/img2img`.
5. Copy `.env.example` to `.env`, use `AI_PROVIDER=forge`, and start this wrapper on port 8000.

The wrapper translates LUMA requests into Forge's API format, decodes the Base64 response, and returns a PNG to the backend. If Forge uses `--api-auth`, set `FORGE_USERNAME` and `FORGE_PASSWORD` in `.env`.

After starting the wrapper, open `http://127.0.0.1:8000/docs` on the AI computer to inspect and test the FastAPI endpoints. Private requests still require the service token.

## Development provider

Set `AI_PROVIDER=development-procedural` to test authentication, routing, uploads, queues, storage, and UI behavior without Forge or a GPU. This provider is not a trained generative model and must not be presented as one.

All non-health requests require the `X-LUMA-Service-Token` header.

## PC 1 on the classroom VLAN

For the three-computer demonstration, PC 1 runs both WebUI Forge and this FastAPI wrapper. Forge remains on `127.0.0.1:7860`, while FastAPI listens on `0.0.0.0:8000` so only the Flask computer needs network access to it.

```powershell
Copy-Item .env.vlan.example .env
python app.py
```

Confirm PC 1's actual VLAN address with `ipconfig`. The proposed address is `192.168.1.30`; it is not hard-coded by the application. Allow inbound TCP port `8000` from PC 3, but do not expose Forge port `7860` to the VLAN.

Start locally:

```powershell
python -m venv .venv
./.venv/Scripts/pip.exe install -r requirements.txt
Copy-Item .env.example .env
./.venv/Scripts/python.exe app.py
```

