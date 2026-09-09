import subprocess
import sys


def test_module_help():
    result = subprocess.run(
        [sys.executable, "-m", "freqhopper", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert "squelch" in result.stdout.lower()
    assert "--demo" in result.stdout
