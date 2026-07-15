# Contributing to Matrix Bridge

We welcome contributions! Here's how to get started.

## Development Setup

```bash
git clone https://github.com/Bwallace16/matrix-bridge.git
cd matrix-bridge

# Backend
cd backend
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt

# Frontend
cd ../dashboard
npm install
```

## Making Changes

1. Create a feature branch: `git checkout -b feature/your-feature`
2. Make your changes
3. Write/update tests
4. Commit: `git commit -am 'Add feature'`
5. Push: `git push origin feature/your-feature`
6. Open a Pull Request

## Code Style

- **Python**: PEP 8 (use `black` for formatting)
- **JavaScript/TypeScript**: Prettier + ESLint
- **Commit messages**: Conventional commits (`feat:`, `fix:`, `docs:`, etc.)

## Testing

```bash
# Backend tests
cd backend
pytest

# Extension tests
cd ../extension
npm test
```

## Questions?

Open an issue or reach out in discussions!
