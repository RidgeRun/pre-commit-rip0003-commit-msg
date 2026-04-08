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
      - id: rip0003-mainline-pre-push
```

## 2) Install hook types

```bash
pre-commit install --hook-type commit-msg --hook-type pre-push
```

## 3) Run the mainline push check in CI

```bash
pre-commit run --hook-stage pre-push rip0003-mainline-pre-push \
  --from-ref <old-sha> \
  --to-ref <new-sha> \
  --remote-branch refs/heads/main \
  --local-branch refs/heads/main \
  --remote-name origin \
  --remote-url <remote-url>
```

The `rip0003-mainline-pre-push` hook validates every new commit in the
provided push range, but only when the pushed branch is `main`, `master`,
or `develop`.
