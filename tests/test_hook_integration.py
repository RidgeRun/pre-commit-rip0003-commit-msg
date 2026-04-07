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
    "gitlint",
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
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        repo = Path(temp_dir.name)
        self.run_cmd(["git", "init", "-b", "main"], cwd=repo)
        self.run_cmd(["git", "config", "user.name", "Test User"], cwd=repo)
        self.run_cmd(["git", "config", "user.email", "test@example.com"], cwd=repo)

        (repo / "README.md").write_text("seed\n")
        self.run_cmd(["git", "add", "README.md"], cwd=repo)
        self.run_cmd(["git", "commit", "-m", "Seed repository"], cwd=repo)

        config = (
            "repos:\n"
            f"  - repo: {self.hook_repo_root}\n"
            f"    rev: {self.hook_rev}\n"
            "    hooks:\n"
            "      - id: rip0003-commit-msg\n"
        )
        (repo / ".pre-commit-config.yaml").write_text(config)
        self.run_cmd(
            ["pre-commit", "install", "--hook-type", "commit-msg"],
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

    def test_main_branch_commit_with_merge_prefix_passes(self):
        repo = self.make_consumer_repo()
        self.stage_change(repo)

        result = self.git_commit(repo, VALID_MAIN_MESSAGE)

        self.assert_passes(result)

    def test_main_branch_commit_without_merge_prefix_fails(self):
        repo = self.make_consumer_repo()
        self.stage_change(repo)

        result = self.git_commit(repo, VALID_REGULAR_MESSAGE)

        self.assert_fails_with(
            result,
            "Merge commits must start with 'feat: ' or 'fix: '",
        )

    def test_main_branch_commit_accepts_valid_breaking_change_footer(self):
        repo = self.make_consumer_repo()
        self.stage_change(repo)

        result = self.git_commit(repo, VALID_BREAKING_MESSAGE)

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
