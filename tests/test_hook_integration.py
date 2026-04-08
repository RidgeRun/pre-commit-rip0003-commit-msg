import subprocess
import tempfile
import unittest
from pathlib import Path
import shutil


REPO_ROOT = Path(__file__).resolve().parents[1]
HOOK_SNAPSHOT_ITEMS = [
    ".gitlint",
    ".pre-commit-hooks.yaml",
    "README.md",
    "bin",
    "gitlint/__init__.py",
    "gitlint/rip0003.py",
]
VALID_REGULAR_MESSAGE = (
    "Avoid unnecessary map copies with rvalues\n\n"
    "Implement overloads that preserve move semantics.\n"
)
VALID_MAIN_MESSAGE = (
    "feat: Add map rvalue overloads\n\n"
    "Implement overloads that preserve move semantics.\n"
)
VALID_BREAKING_MESSAGE = (
    "fix: Rename project API with RR namespace\n\n"
    "Append RR prefixes to avoid collisions.\n\n"
    "BREAKING CHANGE: clients will need to migrate to the newer API naming.\n"
)
MAINLINE_BRANCHES = ("main", "develop", "master")


class HookIntegrationTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls):
        cls.hook_repo_tmp = tempfile.TemporaryDirectory()
        cls.hook_repo_root = Path(cls.hook_repo_tmp.name) / "rip0003-commit-msg"
        cls.hook_repo_root.mkdir()

        for item in HOOK_SNAPSHOT_ITEMS:
            src = REPO_ROOT / item
            dst = cls.hook_repo_root / item
            dst.parent.mkdir(parents=True, exist_ok=True)
            if src.is_dir():
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)

        cls.run_cmd(
            ["git", "init", "-b", "main"],
            cwd=cls.hook_repo_root,
        )
        cls.run_cmd(
            ["git", "config", "user.name", "Test User"],
            cwd=cls.hook_repo_root,
        )
        cls.run_cmd(
            ["git", "config", "user.email", "test@example.com"],
            cwd=cls.hook_repo_root,
        )
        cls.run_cmd(["git", "add", "."], cwd=cls.hook_repo_root)
        cls.run_cmd(
            ["git", "commit", "-m", "Snapshot hook repo"],
            cwd=cls.hook_repo_root,
        )
        cls.hook_rev = cls.run_cmd(
            ["git", "rev-parse", "HEAD"],
            cwd=cls.hook_repo_root,
        ).stdout.strip()

    @classmethod
    def tearDownClass(cls):
        cls.hook_repo_tmp.cleanup()

    @staticmethod
    def combined_output(result: subprocess.CompletedProcess[str]) -> str:
        return result.stdout + result.stderr

    @staticmethod
    def run_cmd(
        cmd: list[str],
        *,
        cwd: Path,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            cmd,
            cwd=cwd,
            text=True,
            capture_output=True,
            check=check,
        )

    def make_consumer_repo(self) -> Path:
        return self.make_configured_consumer_repo(
            hook_ids=("rip0003-commit-msg",),
            install_hook_types=("commit-msg",),
        )

    def make_pre_push_repo(self, *, seed_message: str = "Seed repository") -> Path:
        return self.make_configured_consumer_repo(
            hook_ids=("rip0003-mainline-pre-push",),
            install_hook_types=("pre-push",),
            seed_message=seed_message,
        )

    def make_configured_consumer_repo(
        self,
        *,
        hook_ids: tuple[str, ...],
        install_hook_types: tuple[str, ...],
        seed_message: str = "Seed repository",
    ) -> Path:
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        repo = Path(temp_dir.name)
        self.run_cmd(["git", "init", "-b", "main"], cwd=repo)
        self.run_cmd(["git", "config", "user.name", "Test User"], cwd=repo)
        self.run_cmd(["git", "config", "user.email", "test@example.com"], cwd=repo)

        (repo / "README.md").write_text("seed\n")
        self.run_cmd(["git", "add", "README.md"], cwd=repo)
        self.run_cmd(["git", "commit", "-m", seed_message], cwd=repo)

        config_lines = [
            "repos:",
            f"  - repo: {self.hook_repo_root}",
            f"    rev: {self.hook_rev}",
            "    hooks:",
        ]
        config_lines.extend(f"      - id: {hook_id}" for hook_id in hook_ids)
        config = "\n".join(config_lines) + "\n"
        (repo / ".pre-commit-config.yaml").write_text(config)

        for hook_type in install_hook_types:
            self.run_cmd(
                ["pre-commit", "install", "--hook-type", hook_type],
                cwd=repo,
            )

        return repo

    def stage_change(
        self,
        repo: Path,
        *,
        path: str = "README.md",
        content: str = "change\n",
    ) -> None:
        target = repo / path
        if target.exists():
            current = target.read_text()
            target.write_text(current + content)
        else:
            target.write_text(content)
        self.run_cmd(["git", "add", path], cwd=repo)

    def git_commit(self, repo: Path, message: str) -> subprocess.CompletedProcess[str]:
        message_path = repo / "commit-message.txt"
        message_path.write_text(message)
        return self.run_cmd(
            ["git", "commit", "-F", str(message_path)],
            cwd=repo,
            check=False,
        )

    def git_merge(
        self,
        repo: Path,
        branch: str,
        message: str,
    ) -> subprocess.CompletedProcess[str]:
        message_path = repo / "merge-message.txt"
        message_path.write_text(message)
        return self.run_cmd(
            ["git", "merge", "--no-ff", "-F", str(message_path), branch],
            cwd=repo,
            check=False,
        )

    def git_allow_empty_commit(
        self,
        repo: Path,
        message: str,
    ) -> subprocess.CompletedProcess[str]:
        message_path = repo / "empty-commit-message.txt"
        message_path.write_text(message)
        return self.run_cmd(
            ["git", "commit", "--allow-empty", "-F", str(message_path)],
            cwd=repo,
            check=False,
        )

    def run_pre_push(
        self,
        repo: Path,
        *,
        remote_branch: str,
        local_branch: str,
        from_ref: str | None = None,
        to_ref: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        cmd = [
            "pre-commit",
            "run",
            "--hook-stage",
            "pre-push",
            "rip0003-mainline-pre-push",
            "--remote-name",
            "origin",
            "--remote-url",
            "git@example.com:repo.git",
            "--remote-branch",
            remote_branch,
            "--local-branch",
            local_branch,
        ]
        if from_ref is not None and to_ref is not None:
            cmd.extend(["--from-ref", from_ref, "--to-ref", to_ref])

        return self.run_cmd(cmd, cwd=repo, check=False)

    def create_feature_branch_commit(
        self,
        repo: Path,
        *,
        branch: str = "feature",
        message: str = VALID_REGULAR_MESSAGE,
    ) -> None:
        self.run_cmd(["git", "checkout", "-b", branch], cwd=repo)
        self.stage_change(repo, content="feature change\n")
        result = self.git_commit(repo, message)
        self.assertEqual(0, result.returncode, msg=self.combined_output(result))
        self.run_cmd(["git", "checkout", "main"], cwd=repo)

    def create_branch_commit(
        self,
        repo: Path,
        *,
        branch: str,
        start_point: str,
        message: str = VALID_REGULAR_MESSAGE,
        content: str = "branch change\n",
    ) -> None:
        self.run_cmd(["git", "checkout", "-b", branch, start_point], cwd=repo)
        self.stage_change(repo, content=content)
        result = self.git_commit(repo, message)
        self.assertEqual(0, result.returncode, msg=self.combined_output(result))

    def checkout_mainline_branch(self, repo: Path, branch: str) -> None:
        if branch == "main":
            self.run_cmd(["git", "checkout", "main"], cwd=repo)
            return

        self.run_cmd(["git", "checkout", "-b", branch], cwd=repo)

    def commit_on_mainline_branch(
        self,
        branch: str,
        message: str,
    ) -> subprocess.CompletedProcess[str]:
        repo = self.make_consumer_repo()
        self.checkout_mainline_branch(repo, branch)
        self.stage_change(repo)
        return self.git_commit(repo, message)

    def assert_passes(self, result: subprocess.CompletedProcess[str]) -> None:
        self.assertEqual(0, result.returncode, msg=self.combined_output(result))

    def assert_fails_with(
        self,
        result: subprocess.CompletedProcess[str],
        expected_text: str,
    ) -> None:
        self.assertNotEqual(0, result.returncode)
        self.assertIn(expected_text, self.combined_output(result))

    def test_feature_branch_regular_commit_passes(self):
        repo = self.make_consumer_repo()
        self.run_cmd(["git", "checkout", "-b", "feature"], cwd=repo)
        self.stage_change(repo)

        result = self.git_commit(repo, VALID_REGULAR_MESSAGE)

        self.assert_passes(result)

    def test_feature_branch_commit_rejects_conventional_prefix(self):
        repo = self.make_consumer_repo()
        self.run_cmd(["git", "checkout", "-b", "feature"], cwd=repo)
        self.stage_change(repo)

        result = self.git_commit(repo, VALID_MAIN_MESSAGE)

        self.assert_fails_with(
            result,
            "Regular commits must not start with 'feat: ' or 'fix: '",
        )

    def test_feature_branch_commit_rejects_lowercase_title(self):
        repo = self.make_consumer_repo()
        self.run_cmd(["git", "checkout", "-b", "feature"], cwd=repo)
        self.stage_change(repo)

        result = self.git_commit(
            repo,
            "avoid unnecessary map copies with rvalues\n\n"
            "Implement overloads that preserve move semantics.\n",
        )

        self.assert_fails_with(result, "Title must start with a capital letter")

    def test_feature_branch_commit_rejects_title_with_trailing_period(self):
        repo = self.make_consumer_repo()
        self.run_cmd(["git", "checkout", "-b", "feature"], cwd=repo)
        self.stage_change(repo)

        result = self.git_commit(
            repo,
            "Avoid unnecessary map copies with rvalues.\n\n"
            "Implement overloads that preserve move semantics.\n",
        )

        self.assert_fails_with(result, "Title has trailing punctuation")

    def test_feature_branch_commit_rejects_title_longer_than_fifty_characters(self):
        repo = self.make_consumer_repo()
        self.run_cmd(["git", "checkout", "-b", "feature"], cwd=repo)
        self.stage_change(repo)

        result = self.git_commit(
            repo,
            "Avoid unnecessary copies when mapping temporary values by move\n",
        )

        self.assert_fails_with(result, "Title exceeds max length")

    def test_feature_branch_commit_rejects_body_line_longer_than_seventy_two_characters(self):
        repo = self.make_consumer_repo()
        self.run_cmd(["git", "checkout", "-b", "feature"], cwd=repo)
        self.stage_change(repo)

        result = self.git_commit(
            repo,
            "Avoid unnecessary map copies with rvalues\n\n"
            "Implement overloads that preserve move semantics in temporary object paths.\n",
        )

        self.assert_fails_with(result, "Line exceeds max length (75>72)")

    def test_feature_branch_commit_rejects_missing_blank_line_before_body(self):
        repo = self.make_consumer_repo()
        self.run_cmd(["git", "checkout", "-b", "feature"], cwd=repo)
        self.stage_change(repo)

        result = self.git_commit(
            repo,
            "Avoid unnecessary map copies with rvalues\n"
            "Implement overloads that preserve move semantics.\n",
        )

        self.assert_fails_with(result, "Second line is not empty")

    def test_feature_branch_commit_rejects_breaking_change_footer(self):
        repo = self.make_consumer_repo()
        self.run_cmd(["git", "checkout", "-b", "feature"], cwd=repo)
        self.stage_change(repo)

        result = self.git_commit(
            repo,
            "Rename project API with RR namespace\n\n"
            "Append RR prefixes to avoid collisions.\n\n"
            "BREAKING CHANGE: clients must migrate to the newer API naming.\n",
        )

        self.assert_fails_with(
            result,
            "Regular commits must not contain 'BREAKING CHANGE: ...'",
        )

    def test_mainline_branch_commit_with_merge_prefix_passes(self):
        for branch in MAINLINE_BRANCHES:
            with self.subTest(branch=branch):
                result = self.commit_on_mainline_branch(branch, VALID_MAIN_MESSAGE)
                self.assert_passes(result)

    def test_mainline_branch_commit_without_merge_prefix_fails(self):
        for branch in MAINLINE_BRANCHES:
            with self.subTest(branch=branch):
                result = self.commit_on_mainline_branch(
                    branch,
                    VALID_REGULAR_MESSAGE,
                )
                self.assert_fails_with(
                    result,
                    "Merge commits must start with 'feat: ' or 'fix: '",
                )

    def test_mainline_branch_commit_accepts_valid_breaking_change_footer(self):
        for branch in MAINLINE_BRANCHES:
            with self.subTest(branch=branch):
                result = self.commit_on_mainline_branch(
                    branch,
                    VALID_BREAKING_MESSAGE,
                )
                self.assert_passes(result)

    def test_merge_commit_with_merge_prefix_passes(self):
        repo = self.make_consumer_repo()
        self.create_feature_branch_commit(repo)

        result = self.git_merge(repo, "feature", VALID_MAIN_MESSAGE)

        self.assert_passes(result)

    def test_merge_commit_without_required_prefix_fails(self):
        repo = self.make_consumer_repo()
        self.create_feature_branch_commit(repo)

        result = self.git_merge(repo, "feature", VALID_REGULAR_MESSAGE)

        self.assert_fails_with(
            result,
            "Merge commits must start with 'feat: ' or 'fix: '",
        )

    def test_merge_commit_rejects_lowercase_title_after_prefix(self):
        repo = self.make_consumer_repo()
        self.create_feature_branch_commit(repo)

        result = self.git_merge(
            repo,
            "feature",
            "fix: avoid unnecessary map copies\n\n"
            "Implement overloads that preserve move semantics.\n",
        )

        self.assert_fails_with(
            result,
            "must start with a capital letter",
        )

    def test_merge_commit_accepts_valid_breaking_change_footer(self):
        repo = self.make_consumer_repo()
        self.create_feature_branch_commit(repo)

        result = self.git_merge(repo, "feature", VALID_BREAKING_MESSAGE)

        self.assert_passes(result)

    def test_merge_commit_rejects_breaking_change_without_blank_line(self):
        repo = self.make_consumer_repo()
        self.create_feature_branch_commit(repo)

        result = self.git_merge(
            repo,
            "feature",
            "fix: Rename project API with RR namespace\n\n"
            "Append RR prefixes to avoid collisions.\n"
            "BREAKING CHANGE: clients will need to migrate to the newer API naming.\n",
        )

        self.assert_fails_with(result, "must be preceded by a blank line")

    def test_merge_commit_rejects_breaking_change_without_colon_and_space(self):
        repo = self.make_consumer_repo()
        self.create_feature_branch_commit(repo)

        result = self.git_merge(
            repo,
            "feature",
            "fix: Rename project API with RR namespace\n\n"
            "Append RR prefixes to avoid collisions.\n\n"
            "BREAKING CHANGE clients will need to migrate to the newer API naming.\n",
        )

        self.assert_fails_with(
            result,
            "Use exactly 'BREAKING CHANGE: <description>'",
        )

    def test_merge_into_feature_branch_treats_prefixed_title_as_regular_commit(self):
        repo = self.make_consumer_repo()
        self.run_cmd(["git", "checkout", "-b", "feature"], cwd=repo)
        self.run_cmd(["git", "checkout", "-b", "topic"], cwd=repo)
        self.stage_change(repo, content="topic change\n")
        result = self.git_commit(repo, VALID_REGULAR_MESSAGE)
        self.assert_passes(result)
        self.run_cmd(["git", "checkout", "feature"], cwd=repo)

        result = self.git_merge(repo, "topic", VALID_MAIN_MESSAGE)

        self.assert_fails_with(
            result,
            "Regular commits must not start with 'feat: ' or 'fix: '",
        )

    def test_merge_into_feature_branch_treats_regular_title_as_valid(self):
        repo = self.make_consumer_repo()
        self.run_cmd(["git", "checkout", "-b", "feature"], cwd=repo)
        self.run_cmd(["git", "checkout", "-b", "topic"], cwd=repo)
        self.stage_change(repo, content="topic change\n")
        result = self.git_commit(repo, VALID_REGULAR_MESSAGE)
        self.assert_passes(result)
        self.run_cmd(["git", "checkout", "feature"], cwd=repo)

        result = self.git_merge(repo, "topic", VALID_REGULAR_MESSAGE)

        self.assert_passes(result)

    def test_merge_into_feature_branch_rejects_breaking_change_footer_as_regular(self):
        repo = self.make_consumer_repo()
        self.run_cmd(["git", "checkout", "-b", "feature"], cwd=repo)
        self.run_cmd(["git", "checkout", "-b", "topic"], cwd=repo)
        self.stage_change(repo, content="topic change\n")
        result = self.git_commit(repo, VALID_REGULAR_MESSAGE)
        self.assert_passes(result)
        self.run_cmd(["git", "checkout", "feature"], cwd=repo)

        result = self.git_merge(repo, "topic", VALID_BREAKING_MESSAGE)

        self.assert_fails_with(
            result,
            "Regular commits must not contain 'BREAKING CHANGE: ...'",
        )

    def test_pre_push_skips_non_mainline_branch(self):
        repo = self.make_pre_push_repo()
        before_push = self.run_cmd(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
        ).stdout.strip()

        self.run_cmd(["git", "checkout", "-b", "feature"], cwd=repo)
        self.stage_change(repo)
        result = self.git_commit(repo, VALID_REGULAR_MESSAGE)
        self.assert_passes(result)
        after_push = self.run_cmd(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
        ).stdout.strip()

        result = self.run_pre_push(
            repo,
            remote_branch="refs/heads/feature",
            local_branch="refs/heads/feature",
            from_ref=before_push,
            to_ref=after_push,
        )

        self.assert_passes(result)

    def test_pre_push_accepts_valid_mainline_range(self):
        repo = self.make_pre_push_repo()
        before_push = self.run_cmd(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
        ).stdout.strip()

        self.stage_change(repo)
        result = self.git_commit(repo, VALID_MAIN_MESSAGE)
        self.assert_passes(result)
        after_push = self.run_cmd(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
        ).stdout.strip()

        result = self.run_pre_push(
            repo,
            remote_branch="refs/heads/main",
            local_branch="refs/heads/main",
            from_ref=before_push,
            to_ref=after_push,
        )

        self.assert_passes(result)

    def test_pre_push_rejects_invalid_mainline_commit(self):
        repo = self.make_pre_push_repo()
        before_push = self.run_cmd(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
        ).stdout.strip()

        result = self.git_allow_empty_commit(repo, VALID_REGULAR_MESSAGE)
        self.assertEqual(0, result.returncode, msg=self.combined_output(result))
        after_push = self.run_cmd(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
        ).stdout.strip()

        result = self.run_pre_push(
            repo,
            remote_branch="refs/heads/main",
            local_branch="refs/heads/main",
            from_ref=before_push,
            to_ref=after_push,
        )

        self.assert_fails_with(
            result,
            "Merge commits must start with 'feat: ' or 'fix: '",
        )

    def test_pre_push_checks_every_commit_in_mainline_range(self):
        repo = self.make_pre_push_repo()
        before_push = self.run_cmd(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
        ).stdout.strip()

        result = self.git_allow_empty_commit(repo, VALID_MAIN_MESSAGE)
        self.assertEqual(0, result.returncode, msg=self.combined_output(result))
        result = self.git_allow_empty_commit(repo, VALID_REGULAR_MESSAGE)
        self.assertEqual(0, result.returncode, msg=self.combined_output(result))
        after_push = self.run_cmd(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
        ).stdout.strip()

        result = self.run_pre_push(
            repo,
            remote_branch="refs/heads/main",
            local_branch="refs/heads/main",
            from_ref=before_push,
            to_ref=after_push,
        )

        self.assert_fails_with(
            result,
            "Merge commits must start with 'feat: ' or 'fix: '",
        )

    def test_pre_push_initial_mainline_push_uses_local_branch_history(self):
        repo = self.make_pre_push_repo(seed_message=VALID_MAIN_MESSAGE)
        result = self.git_allow_empty_commit(repo, VALID_MAIN_MESSAGE)
        self.assertEqual(0, result.returncode, msg=self.combined_output(result))

        result = self.run_pre_push(
            repo,
            remote_branch="refs/heads/main",
            local_branch="refs/heads/main",
        )

        self.assert_passes(result)
