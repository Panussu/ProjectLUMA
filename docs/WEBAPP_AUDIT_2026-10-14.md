# Web application audit - 14 October 2026

Base: main 01afe9e. Checks ran against the current integrated checkout.

## Corrections

- Reject public example keys for signed private media, validate token payloads, and exclude signed query tokens from application and Nginx access logs.
- Permit PUT/DELETE CORS preflights for favorites and reject non-object favorite request bodies.
- Match browser/backend generation limits to the AI wrapper: 256-1024 pixels in multiples of 64, and 1-50 steps.
- Clear private results and polling on logout; ignore late history, image processing, submission, and authentication responses from older sessions.
- Disable interruption until a job ID exists; cancel via one owned-job endpoint and retain polling after temporary service failures.
- Validate image editing options and malformed images; bound fallback image processing dimensions and tolerate malformed optional AI metadata.
- Remove abandoned result files if a worker fails after writing an image; prevent internal exceptions reaching job error responses.
- Use the actual FORGE_URL/credentials in production Compose, persist queued edit uploads, and enable recovery and production secret validation.
- Propagate native-command failures from deployment and service launch scripts.
- Serve pinned Bootstrap 5.3.3 and its MIT license locally so authentication UI does not depend on an external CDN; update asset cache versions.

## Verified results

| Check | Result |
| --- | --- |
| Python regression suite | 109 passed |
| Frontend Node suite | 15 passed |
| HTTP/API checks through real Nginx, Flask and FastAPI | 78 passed |
| Chromium browser checks, including app, documentation, responsive layout, and regressions | 53 passed (39 + 10 + 4) |
| Python compilation and JavaScript syntax | Passed |
| Dependency consistency | pip check passed |
| Nginx native and container configuration syntax with local test addresses | Passed |
| Development and production Compose configuration | Passed; production used test fixture settings |
| PowerShell parsing | All 12 scripts passed |
| Deployment command failure handling | Simulated failing Docker command returned failure |
| External internet blocked | Local login dialog and Bootstrap behavior passed |

Before fixes, all 12 initial new regression cases failed; they passed after correction. The final 21 new Python audit cases and 7 new Node cases extend the existing suite.

The browser suite used synthetic checkpoint/LoRA files and a procedural AI provider. Those are test fixtures, not real AI models or measured GPU results. Backup/restore is exercised by the Python suite using temporary SQLite/media fixtures.

## Verification limits

Docker Desktop's Linux engine was not available, so container builds and runtime deployment were not exercised. Real Forge inference, a GPU, production data migration, and the physical three-PC VLAN were not tested. Local procedural generation demonstrates application integration, not Stable Diffusion quality. Passing these checks does not establish that every possible defect is absent.
