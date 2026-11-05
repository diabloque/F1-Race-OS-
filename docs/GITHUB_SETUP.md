# GitHub setup

The source repository is https://github.com/diabloque/F1-Race-OS-.
The project is built and verified locally before upload. The launcher installs
and runs the application locally; it does not upload code or deploy a hosted app.

## Local use and validation

Install Python 3.11 and Node.js 24 LTS, then run `python run.py`. First setup
needs internet. Choose a year, Grand Prix, and Race or Qualifying in the app.
Use `python run.py --setup-only` for installation/build without starting a server.

Windows checks after setup:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=data/tmp/pytest-manual
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run test:smoke
```

The smoke check uses installed Edge on Windows. Linux/macOS use Playwright
Chromium; install it first with `npx playwright install chromium` from `frontend`.
This browser download is optional for ordinary app use. CI installs Chromium in
its temporary runner, not on this user's Windows C drive.

## Upload and later updates

The chosen repository uses the existing local history. After local verification,
the upload commands are:

```powershell
git remote add origin https://github.com/diabloque/F1-Race-OS-.git
git push -u origin main
```

Authenticate using your normal GitHub/Git credential flow. Never put tokens in
source files. The Actions tab shows the workflow result after pushing. GitHub
hosting the repository does not start the Python server or publish a running app.

## What goes into Git

Source, tests, dependency locks, documentation, and the CI workflow are tracked.
`data/`, `.venv/`, `node_modules/`, generated builds, and `.env` files are ignored.
A fresh clone has an empty session library and downloads only requested data.
The new prepared-data cache remains capped at 200 MiB. Existing local archives
and earlier backups are preserved separately.
