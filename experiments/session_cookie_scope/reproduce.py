"""Reintroduce the Stage 2 fixture mistake in a disposable test copy.

Run from the repository root: python experiments/session_cookie_scope/reproduce.py
This is a controlled mutation on the current source, not a historical checkout.
The expected four failures are evidence, not a successful regression suite.
"""

from pathlib import Path
import subprocess
import sys
import tempfile


def main():
    root = Path(__file__).resolve().parents[2]
    source = (root / "tests/test_stage3_forum_trace.py").read_text(encoding="utf-8")
    # Keep the six original regression cases; the separate hypothesis matrix
    # intentionally creates fresh clients and is not part of this mutation.
    source = source.split('\n\n@pytest.mark.parametrize(\n    "login_host,request_host",')[0]
    old = 'client.post("/login", data={"username": "student-1", "password": "password"})'
    new = 'client.post("/login", data={"username": "student-1", "password": "password"}, base_url="http://example.com")'
    if source.count(old) != 1:
        raise RuntimeError("Fixture changed; inspect the mutation instead of guessing")
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", suffix=".py",
                                     prefix="test_cookie_probe_", dir=root / "tests",
                                     delete=False) as handle:
        handle.write(source.replace(old, new, 1))
        probe = Path(handle.name)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(probe), "-q", "--tb=short",
             "--disable-warnings"], cwd=root, text=True, capture_output=True,
            encoding="utf-8", errors="replace",
        )
        print(result.stdout)
        print(result.stderr, file=sys.stderr)
        expected = result.returncode == 1 and "4 failed, 2 passed" in result.stdout
        print(f"CONTROLLED_MUTATION_EXPECTED_FAILURES={expected}")
        return 0 if expected else 1
    finally:
        probe.unlink()


if __name__ == "__main__":
    raise SystemExit(main())

