# Contributing

Contributions are welcome. Please follow these guidelines to keep the project maintainable.

## Getting Started

1. Fork the repository
2. Clone your fork: `git clone https://github.com/YOUR_USERNAME/RAG-Assistant-for-Zotero.git`
3. Set up the development environment:
   ```bash
   ./setup.sh
   source .venv/bin/activate
   npm install
   cd frontend && npm install
   ```
4. Create a branch: `git checkout -b your-feature-name`
5. Make your changes
6. Test locally
7. Submit a pull request

## Development

Run the application in development mode:

```bash
# All-in-one (recommended)
npm run dev

# Or separately:
source .venv/bin/activate && uvicorn backend.main:app --reload  # Terminal 1
cd frontend && npm run dev                                       # Terminal 2
```

## Code Guidelines

**Python:**
- Follow PEP 8
- Add type hints
- Include docstrings for public functions

**TypeScript/React:**
- Use TypeScript for all new code
- Prefer functional components with hooks
- Keep components focused

## Testing

```bash
# Backend (unit tests; markers and paths are in pyproject.toml)
python -m pytest

# Frontend (type-check, lint, build)
cd frontend && npm run typecheck && npm run lint && npm run build
```

The same checks run in GitHub Actions on every push and pull request
(`.github/workflows/ci.yml`). Add tests for new features when applicable.

## Security

Never commit:
- API keys or credentials
- `.env` files with real values
- Personal database paths
- Chat history or profile data
- Files in `~/.zotero-llm/`

The `.gitignore` file already excludes these, but verify before committing: `git status`

## Pull Requests

- Write clear commit messages
- Update documentation if adding features
- Include testing steps in the PR description
- Reference related issues with `#issue-number`

## Bug Reports

When opening an issue for a bug, include:
- Steps to reproduce
- Expected vs actual behavior
- Environment (OS, Python version, Node version)
- Relevant error messages

Do not include API keys or personal data.

## License

Contributions are licensed under the project's MIT license.
