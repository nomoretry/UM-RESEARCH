"""Real Git regression for Windows paths containing Chinese characters."""
from pathlib import Path
import subprocess

from um_charging.__main__ import checked_output


def test_local_git_output_path_with_chinese_characters(tmp_path):
    run_repository = tmp_path / "研究运行记录"
    subprocess.run(["git", "init", str(run_repository)], check=True, capture_output=True, encoding="utf-8")
    source = Path(__file__).resolve().parents[1]
    output = run_repository / "new_run" / "artifacts"
    assert checked_output(output, source) == output.resolve()
    assert not output.exists()  # Validation must not create or overwrite a run.
