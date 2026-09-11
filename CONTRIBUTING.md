# Contributing to RAG Assistant for Zotero

Thanks for your interest in contributing! This project is copyright © Alexander Hepburn and contributors, and is licensed under GPL-3.0 (see `LICENSE`). By submitting a pull request, you agree that your contribution is licensed under the same terms as the rest of the project.

## Before You Start

For significant changes (new features, architectural changes, dependency additions, UI redesigns), please open an issue first to discuss it. Small fixes — typos, obvious bugs, minor doc edits — can go straight to a pull request.

## Forking and Branching

1. Fork the repo, then add the upstream remote and keep your fork in sync:
   ```bash
   git remote add upstream https://github.com/Quiet-Signals-Lab/RAG-Assistant-for-Zotero.git
   git fetch upstream
   git checkout main
   git merge upstream/main
   ```
2. Work on a dedicated branch (e.g., `fix/zotero-path-detection`), not directly on `main`.
3. Don't commit secrets, API keys, or a populated `.env` file — use `.env.example` as a starting point.
4. Don't commit build artifacts (`release/` from `npm run package:*`) — check `.gitignore` first.
5. Since this project is GPL-3.0, if you publicly distribute a modified version of the app, that version needs to stay open source under GPL-3.0 too.

## Development Setup

- Backend: install `requirements.txt` in a virtual environment.
- Frontend/Electron: `npm install`, then `npm run package:mac` / `package:win` / `package:linux` to build.
- See `docs/BUILD_CHECKLIST.md` and `docs/TECHNICAL_DETAILS.md` for details on the build and the retrieval pipeline.

## Pull Requests

- Keep PRs focused on one change.
- Describe what changed, why, and how you tested it (platform + LLM provider used).
- Match the existing code style (Python in `backend/`, TypeScript/React in `frontend/`).
- Preserve the privacy model — excluded collections/tags must never be sent to a cloud provider.
- Push follow-up commits to the same branch instead of force-pushing over reviewed history.

## Reporting Issues

- Search existing issues first.
- Include your OS, install method, LLM provider, and steps to reproduce.
- For security issues, follow `SECURITY.md` instead of opening a public issue.
