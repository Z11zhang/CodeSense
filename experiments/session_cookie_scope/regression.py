"""Run the Stage 3 regression before/after check.

From the repository root:
    python experiments/session_cookie_scope/regression.py

The before case reintroduces the historical cross-host fixture mistake in a
throwaway test copy. The after case runs the unchanged fixed test module.
"""
from pathlib import Path
import subprocess
import sys
import tempfile


def run_pytest(root, target):
    return subprocess.run(
        [sys.executable, "-m", "pytest", str(target), "-q", "--tb=short",
         "--disable-warnings"],
        cwd=root,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def main():
    root = Path(__file__).resolve().parents[2]
    test_file = root / "tests/test_stage3_forum_trace.py"
    source = test_file.read_text(encoding="utf-8")
    source = source.split('\\n\\n@pytest.mark.parametrize(\\n    "login_host,request_host",')[0]
    old = 'client.post("/login", data={"username": "student-1", "password": "password"})'
    new = 'client.post("/login", data={"username": "student-1", "password": "password"}, base_url="http://example.com")'
    if source.count(old) != 1:
        raise RuntimeError("Fixture changed; inspect the mutation instead of guessing")

    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", suffix=".py", prefix="test_cookie_before_",
        dir=root / "tests", delete=False
    ) as handle:
        handle.write(source.replace(old, new, 1))
        before_file = Path(handle.name)

    try:
        before = run_pytest(root, before_file)
        print("=== BEFORE: restored old cross-host fixture ===")
        print(before.stdout, end="")
        if before.stderr:
            print(before.stderr, file=sys.stderr, end="")
        before_ok = before.returncode == 1 and "4 failed, 2 passed" in before.stdout
        print(f"BEFORE_EXPECTED_FAILURES={before_ok}")
    finally:
        before_file.unlink(missing_ok=True)

    after = run_pytest(root, test_file)
    print("=== AFTER: fixed regression suite ===")
    print(after.stdout, end="")
    if after.stderr:
        print(after.stderr, file=sys.stderr, end="")
    after_ok = after.returncode == 0 and "10 passed" in after.stdout
    print(f"AFTER_EXPECTED_PASS={after_ok}")
    return 0 if before_ok and after_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
