# Project LUMA: Version Comparison and Local Fixes

**Date:** 14 October 2026 (Asia/Bangkok)  
**Repository:** [Panussu/ProjectLUMA](https://github.com/Panussu/ProjectLUMA)

## 1. What changed between the previous and latest GitHub versions?

The latest component commits improve the project, but do not fully resolve the issues reported on 13 October.

| Component | Previous version | Latest GitHub version |
|---|---|---|
| AiEngine | `1aed165` | `23daaf9` |
| Backend | `12d4290` | `1919a02` |
| Frontend | `2b73b50` | `3f940c1` |
| QA | `26680f6` | Unchanged |

| Area | Latest GitHub change | Result of recheck |
|---|---|---|
| Invalid requests and uploads | Added JSON and image validation | Reported malformed-input and corrupt-interrogation cases pass |
| Image metadata | Safely handles JPEG/WebP metadata | Both formats pass |
| Tag suggestions | Clamps requested limits | Negative limits no longer return thousands of tags |
| Image filters | Aligns edge and blur processing | Results match between services |
| Main frontend layout | Fixes smaller-screen overflow | Main application passes at 390, 768, and 1440 px |
| Deployment files | Restores both Dockerfiles and the maintenance CLI | Missing files repaired; container execution remains unverified |
| Worker cancellation | Adds database refreshes and state checks | Earlier cancellation cases pass, but later races still fail |
| Job isolation | Frontend and Backend send job IDs | AI queue and controls still do not consume those IDs correctly |
| GPU controls | Adds limited interrupt ownership checking | Authentication remains optional; interrupt/skip remain unsafe |
| Upscaler selection | Backend forwards selected method | Development provider still ignores the resize selection |
| Edit upload interface | Removes preview, clear, drop, and paste conveniences | These previously working features regress |
| QA setup and backup/restore | No effective repair | Test harness/dependency and database-path problems remain |
| Overview site | No changes | Broken links and mobile overflow remain |

GitHub `main` remained unchanged at `bdfd3ed`. These component changes had not been integrated into it when checked.

## 2. Fixes implemented locally

The failed cases were repaired in a separate Git checkout on local branch `fix/audit-20261014`. The original checkout and its untracked overview folder were preserved. No changes were pushed to GitHub.

### Authentication and ownership

- Interrupt, skip, and progress routes now require valid user authentication.
- GPU controls require a job ID and verify that the job belongs to the requesting user.
- Invalid tokens are rejected before provider calls.
- Skip only accepts an owned processing job.
- Progress reuses the owned-job endpoint rather than exposing global GPU state.

### AI queue and job isolation

- Restored queue tracking for active and cancelled job IDs.
- Generation and editing consume `X-LUMA-Job-ID` from Backend requests.
- Progress and previews are scoped to the matching job.
- Interrupt and skip only affect the matching active job.
- Cancelled queued jobs cannot begin later, and waiting requests check cancellation periodically.
- Forge concurrency is limited to one because its progress/control interface is global.

### Cancellation races

- Workers claim queued jobs with a conditional database transition.
- Completion only succeeds while the job is still processing.
- Late cancellation cannot be overwritten as completed.
- Timeout and other error handlers cannot overwrite a cancelled job as failed.
- Results written during a lost completion race are removed.
- Cancellation is saved before the provider interrupt is sent, with a conditional state transition to avoid overwriting completed jobs.

### Frontend

- Polling now checks the owned job and its owned progress endpoint.
- Terminal jobs do not start or retain polling timers.
- Old preview images are removed when current progress has no preview.
- One percent progress stays one percent.
- Restored edit image preview, clear, drop, and clipboard paste.
- Restored catalogue refresh after authentication.
- Updated the Node harness to execute the real application's exports instead of slicing source at an obsolete marker.

### QA, recovery, and documentation

- Development requirements now include the AI dependencies and compatible test client.
- Added regression tests for authentication bypass, late cancellation, timeout cancellation, configured recovery, missing databases, and unsafe archives.
- Generic backup and restore scripts use application-configured database and media paths.
- Backup uses SQLite's backup API and refuses to report success when the configured database is missing.
- Restore validates the archive/database and replaces the configured database file atomically. Backend services must be stopped before restoration.
- Development resizing honors Nearest, Bicubic, and Bilinear selections instead of always using Lanczos.
- Repaired all eight broken overview links and both documentation pages' smaller-screen overflow.

## 3. Verification

| Checks | Previous GitHub components | Latest GitHub components before local fixes | After local fixes |
|---|---|---|---|
| Existing Python regressions | 56 passed / 9 failed | 59 passed / 6 failed | Existing cases pass |
| Full Python suite including added regressions | Not available | Five extra security/cancellation cases fail | **74 passed / 0 failed** |
| Existing frontend Node tests | 8 blocked | 8 blocked | **8 passed / 0 failed** |
| HTTP/API checks | 72 passed / 11 failed | 80 passed / 3 failed | **83 passed / 0 failed** |
| Browser checks | 43 passed / 6 failed | 43 passed / 6 failed | **49 passed / 0 failed** |
| Clean dependency installation and Python suite | Incomplete QA dependency list | Still incomplete | **Fresh installation succeeds; 74 tests pass** |
| PowerShell backup/restore round trip | Wrong database paths | Still wrong | **Restores a valid SQLite fixture to its configured location** |
| Patch application | — | — | **Both patches pass application checks against audited source versions** |

The Python total includes new tests and is not a direct same-size comparison with the original 65-case regression suite. Test groups overlap and should not be summed as unique requirements.

Python/JavaScript compilation, PowerShell parsing, dependency consistency, and Compose configuration checks also pass.

Real HTTP/browser checks used local Nginx, Flask/Waitress, FastAPI, synthetic accounts/storage, and the development procedural provider. Browser checks covered generation, editing, downloads, filters, upscaling, authentication, catalogue controls, metadata, upload conveniences, and both overview pages.

## 4. Files for the team

The accompanying `ProjectLUMA_Fixes_2026-10-14.zip` contains:

- `core-fixes.patch`: application, recovery, dependency, and test repairs.
- `overview-fixes.patch`: documentation navigation and layout repairs.
- `patched-files/`: the 18 repaired/new files for review or manual integration.
- `README.md`: base versions and application instructions.
- This comparison report.

Apply the core patch to an integration checkout containing the audited component versions and the existing test files. It is not a patch against the old GitHub `main`. Review local changes first and run the patch application check before applying it.

The overview patch requires the existing overview folder, which is currently untracked locally. It is separate so it does not block application fixes when that folder has not been shared yet.

## 5. What remains unverified?

- Real Forge/CUDA generation and actual model/LoRA effects.
- Real neural upscaler output. Development resizing is tested; it is not a substitute for AI super-resolution.
- Container build/runtime because the Docker engine was unavailable.
- Three-PC/Hamachi acceptance testing.
- Actual GitHub Actions execution and browser engines other than Chromium.

All temporary test services were stopped after testing. The previous reports are preserved. These results demonstrate that the exercised failed cases are repaired locally; they do not guarantee that every possible production issue has been eliminated.
