# Working with the GitHub repository

The project is published at [diabloque/F1-Race-OS-](https://github.com/diabloque/F1-Race-OS-).
GitHub stores the source and runs checks. Run the application on your computer.

## Clone and run

Install Python 3.11 and Node.js 24 LTS. Open a terminal in the folder where you
want the project. To keep it on E:, choose a folder on E: before cloning.

```powershell
git clone https://github.com/diabloque/F1-Race-OS-.git
cd F1-Race-OS-
python run.py
```

The launcher creates the environment, installs locked dependencies, builds the
frontend, and opens the app. A fresh clone has an empty session library. Open a
Race or Qualifying session in the app to download only the data it needs.
Use `python run.py --setup-only` to install and build without starting the server.

## Check changes

After setup on Windows:

```powershell
.\.venv\Scripts\python.exe -m pytest -q --basetemp=data/tmp/pytest-manual
npm --prefix frontend test
npm --prefix frontend run build
npm --prefix frontend run test:smoke
```

The smoke check uses installed Edge on Windows. Linux/macOS use Playwright
Chromium; install it first with `npx playwright install chromium` from `frontend`.
This browser download is optional for ordinary app use. GitHub Actions installs
its browser in the temporary CI runner.

## Upload later changes

A clone already has `origin` configured. Review the files before committing:

```powershell
git status
git diff
git add <files-you-changed>
git commit -m "Describe the change"
git push
```

Authenticate through your normal Git credential flow. Keep tokens out of source
files. GitHub Actions runs setup, backend/frontend tests, and the offline browser
smoke check for each push or pull request. See the **Actions** tab for results.

## Tracked and ignored files

Source, tests, dependency locks, current guides, screenshots, and CI are tracked.
`data/`, `.venv/`, `node_modules/`, generated builds, and `.env` files are ignored.
The remote cache is capped at 200 MiB. Local archives and backups stay separate.
Earlier phase reports and the obsolete chart implementation remain in Git history.
