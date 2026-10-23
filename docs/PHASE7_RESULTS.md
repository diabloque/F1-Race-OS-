# Phase 7: local setup and automated checks

Approved 2026-10-22. The user chose to finish locally and upload to GitHub at
the end. This milestone prepares the repository; it does not publish a hosted
application or upload source to a remote repository.

## Changes

- `python run.py` creates the local Python environment, installs locked Python
  and JavaScript dependencies, builds changed frontend sources, and starts one
  server. It opens the browser when the backend is ready. Setup-only, custom
  port, and no-browser options are available.
- Install caches, temporary files, browser test profiles, and data stay under
  the project. On Windows, old pip receives a bundle of the system's trusted
  certificates, retaining TLS verification. Node also uses system certificates.
- A local Git repository is initialized on `main`. Git trusts this exact E: folder
  through a small user Git setting because the drive does not record ownership. Data, old archives, backups,
  environments, dependency folders, builds, and `.env` files are excluded.
- `.github/workflows/checks.yml` installs/builds a clean checkout with Python
  3.11 and Node 24, runs backend/frontend tests, and checks the empty dashboard
  in Chromium. Actions are pinned to verified official commit references.
- The browser smoke check uses its own empty database and an intercepted empty
  schedule. It covers backend health, `/`, `/docs`, empty library, comparison
  guards, mobile overflow, and JavaScript errors without remote F1 requests.
- README and `GITHUB_SETUP.md` explain startup, optional tests, and later upload.

## Verification

A clean checkout containing only Git-tracked files was exported to
`data/tmp/fresh-checkout-20261022` on E:. It had no virtual environment,
JavaScript dependencies, frontend build, database, or saved-session library.
`run.py --setup-only` installed the locked dependencies and built successfully.
A second setup run reused the finished setup without reinstalling or rebuilding.
`pip check` reported no broken requirements.

In that clean environment, all **125 Python tests** and **10 frontend tests**
passed. The production TypeScript/Vite build and installed-Edge offline smoke
check passed. One dependency deprecation warning is emitted by Starlette's
TestClient; tests still pass. No C-drive project dependency/browser downloads
were needed. Browser evidence and `data/phase7-validation.json` remain on E:. The disposable
clean checkout and its duplicate dependencies were removed after validation.
The full local real-data integration suite also passed 24 Edge browser scenarios,
including the new distance overlay and existing replay/engineering features.
Desktop/mobile screenshots were inspected without overflow or JavaScript errors.

GitHub Actions itself cannot run until a future upload. Linux CI is configured;
local validation uses this Windows machine and its installed Edge browser.
Hosting, deployment, and live ingestion remain optional future work.
