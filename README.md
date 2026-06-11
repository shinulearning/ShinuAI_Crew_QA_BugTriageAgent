# ShinuAI Crew — QA Bug Triage Agent

Lightweight agent for triaging QA bug reports and assisting automated bug classification.

## Files
- `QABugTriageCrew.py` — main script in this repository
- `requirement.txt` — Python dependencies

## Requirements
- Python 3.8+
- Install dependencies:

```bash
pip install -r requirement.txt
```

## Environment
Create a `.env` file from `.env_Sample` and set the required variables.

```bash
copy .env_Sample .env
# then edit .env and fill values
```

Common variables:
- `OPENAI_API_KEY` — API key for language model access
- `GITHUB_TOKEN` — (optional) token for GitHub API operations

## Usage
Run the main script:

```bash
python QABugTriageCrew.py
```

## Contributing
Feel free to open issues or PRs in the repository.

## License
Use as you like. Add a license file if needed.
