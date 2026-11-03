# First GitHub publication

The publishable project is the `incident-lab` directory containing this README and `pyproject.toml`. Parent portfolio plans, CVs, profile drafts, local environments, and working artifacts do not belong in this repository.

## Local checks

Follow [Contributing](../CONTRIBUTING.md), run offline [saved-score replay](reproducibility.md), and inspect [verification status](verification.md). The first public version intentionally includes the model's failures and labels its eight cases as development data. Fixing these failures should be a visible next change rather than an undocumented rewrite of the reference run.

Before the first commit, inspect the file list and content for credentials or machine-specific paths. `.gitignore` excludes local environments, working artifacts, model directories, keys, and build outputs. Curated synthetic traces in `examples/` are intentionally included. Git ignore rules do not remove files already tracked.

## Create the remote when ready

Create an empty GitHub repository named `incident-lab` under `NourMedjedel`. Do not pre-create another README, license, or `.gitignore`, since these already exist locally. Then, from the project root:

```bash
git init -b main
git add .
git status --short
git diff --cached --stat
git commit -m "Initial incident investigation lab"
git remote add origin https://github.com/NourMedjedel/incident-lab.git
git push -u origin main
```

Confirm the GitHub Actions checks after the push. The repository's clone URL in the README becomes available once this remote exists; the audit uses a temporary local clone to verify the same file layout before publication.

Suggested description: `Evidence-traced incident investigation with LangGraph, local LLMs, and reproducible baseline comparisons.` Suggested topics: `python`, `langgraph`, `agents`, `ollama`, `evaluation`, `incident-management`, `rag`.

Avoid a passing-CI badge until the remote checks actually pass. A short terminal recording or screenshot of the demo can be added after publication, using synthetic data and measured results.
