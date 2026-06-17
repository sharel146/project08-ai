"""Test the self-improvement sandbox system."""

import subprocess
from pathlib import Path

from sunny.tools.self_improve import ImprovementOutcome, SelfImprover


def _init_repo(repo_path: Path):
    """Initialize a git repo with signing disabled."""
    subprocess.run(["git", "init"], cwd=repo_path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=repo_path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, capture_output=True)
    subprocess.run(["git", "config", "commit.gpgsign", "false"], cwd=repo_path, capture_output=True)


def test_list_files_finds_tracked_files(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    test_file = repo / "test.py"
    test_file.write_text("print('hello')")
    subprocess.run(["git", "add", "test.py"], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True)

    improver = SelfImprover(repo, "echo ok")
    files = improver.list_files()
    assert "test.py" in files


def test_read_file_opens_tracked_file(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    test_file = repo / "test.py"
    test_file.write_text("x = 42")
    subprocess.run(["git", "add", "test.py"], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True)

    improver = SelfImprover(repo, "echo ok")
    content = improver.read_file("test.py")
    assert content == "x = 42"


def test_validate_change_runs_tests_in_sandbox(tmp_path):
    """Changes are validated in a sandbox without touching the live tree."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    # Create initial commit so HEAD exists
    (repo / "README.md").write_text("# test")
    subprocess.run(["git", "add", "README.md"], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True)

    # Create a file and a passing test
    target = repo / "source.py"
    target.write_text("value = 1")
    test_file = repo / "test.py"
    test_file.write_text("from source import value\nassert value == 1")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "add files"], cwd=repo, capture_output=True)

    improver = SelfImprover(repo, "python test.py")

    # Propose a change that breaks the test
    outcome = improver.validate_change("source.py", "value = 2")
    assert outcome.ok is False
    assert outcome.stage == "tests_failed"
    assert "assert value == 1" in outcome.detail

    # Verify the live tree was NOT modified
    assert target.read_text() == "value = 1"


def test_validate_change_passes_on_good_change(tmp_path):
    """A change that passes tests returns validated."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    # Create initial commit so HEAD exists
    (repo / "README.md").write_text("# test")
    subprocess.run(["git", "add", "README.md"], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True)

    # Create a file and test that checks for either 1 or 2
    target = repo / "source.py"
    target.write_text("value = 1")
    test_file = repo / "test.py"
    test_file.write_text("from source import value\nassert value in (1, 2)")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "add files"], cwd=repo, capture_output=True)

    improver = SelfImprover(repo, "python test.py")

    # Propose a change that still passes
    outcome = improver.validate_change("source.py", "value = 2")
    assert outcome.ok is True
    assert outcome.stage == "validated"

    # Live tree still unchanged
    assert target.read_text() == "value = 1"


def test_apply_change_writes_to_live_tree(tmp_path):
    """After validation passes, apply_change writes to the real tree."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _init_repo(repo)

    target = repo / "source.py"
    target.write_text("value = 1")
    subprocess.run(["git", "add", "."], cwd=repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=repo, capture_output=True)

    improver = SelfImprover(repo, "echo ok")
    new_content = "value = 2"

    outcome = improver.apply_change("source.py", new_content)
    assert outcome.ok is True
    assert outcome.stage == "applied"
    assert target.read_text() == new_content


def test_upgrade_channel_lights_on_tools(tmp_path):
    """Self-improvement tools light the 'upgrade' channel."""
    from types import SimpleNamespace
    from sunny.brain import Brain
    from sunny.memory import Store
    from sunny.tools.devices import DeviceRegistry

    brain = Brain(
        SimpleNamespace(model="m", effort="high", anthropic_api_key="k"),
        Store(tmp_path / "t.db"),
        SimpleNamespace(push=lambda *a, **k: None),
        DeviceRegistry.with_demo_devices(),
        SimpleNamespace(),
        client=object(),
    )

    assert not brain.is_active("upgrade")

    brain._run_tool("list_my_files", {})
    assert brain.is_active("upgrade")
