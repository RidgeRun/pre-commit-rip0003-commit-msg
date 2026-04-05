# RIP 3 Git Hooks

Use these hooks with `pre-commit` to enforce RIP 3 Commit Messages
rules used by RidgeRun engineers

## 1) Add to your `.pre-commit-config.yaml`

```yaml
repos:
  - repo: <hook-repo-url>
    rev: <tag-or-commit>
    hooks:
      - id: rip0003-commit-msg
```

## 2) Install hook types

```bash
pre-commit install --hook-type commit-msg
```
