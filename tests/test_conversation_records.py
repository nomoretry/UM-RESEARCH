"""Real Git integration tests; all mutable repositories live in temporary folders.

Run with: python -m unittest discover -s tests -p test_conversation_records.py -v
No research model, network, real conversation, or user Git identity is exercised.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "conversation_records.py"


class ConversationRecordsTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="um-records-test-")
        self.addCleanup(self.temporary.cleanup)
        self.base = Path(self.temporary.name)
        self.repo = self.base / "研究 source"
        self.local = self.base / "独立 records"
        self.repo.mkdir()
        self.env = os.environ.copy()
        self.env.update({
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "GIT_AUTHOR_NAME": "Records Integration Test",
            "GIT_AUTHOR_EMAIL": "records-test@example.invalid",
            "GIT_COMMITTER_NAME": "Records Integration Test",
            "GIT_COMMITTER_EMAIL": "records-test@example.invalid",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": str(self.base / "empty-global-config"),
            "GIT_TERMINAL_PROMPT": "0",
        })
        (self.base / "empty-global-config").write_text("", encoding="utf-8")
        self.git(self.repo, "init", "--initial-branch=codex/test")
        self.git(self.repo, "config", "core.autocrlf", "false")
        self.write(".gitignore", "/.um-records.local.json\n/.um-records.lock\n")
        self.write("source.py", "value = 1\n")
        self.git(self.repo, "add", "--", ".gitignore", "source.py")
        self.git(self.repo, "commit", "-m", "Synthetic fixture baseline")
        self.initial_commit = self.git(self.repo, "rev-parse", "HEAD")

    def git(self, repo, *args):
        result = subprocess.run(
            ["git", "--literal-pathspecs", "-C", str(repo), *args],
            env=self.env, capture_output=True, encoding="utf-8", errors="strict",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout.strip()

    def invoke(self, *args, success=True):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--repo", str(self.repo), *map(str, args)],
            cwd=self.base, env=self.env, capture_output=True,
            encoding="utf-8", errors="strict",
        )
        if success:
            self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
            return json.loads(result.stdout)
        self.assertNotEqual(result.returncode, 0, result.stdout)
        return result

    def write(self, relative, text):
        path = self.repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8", newline="\n")
        return path

    def initialize(self):
        return self.invoke("init", "--records-root", self.local)

    def register_main(self, commit=True):
        self.initialize()
        result = self.invoke(
            "register", "--id", "0001", "--slug", "research", "--kind", "main",
            "--title", "Local test title", "--background", "Synthetic test background",
        )
        self.entry = result["conversation"]
        if commit:
            paths = [
                "conversations/registry.json", "conversations/INDEX.md",
                self.entry["directory"] + "/README.md",
                self.entry["directory"] + "/STATUS.md",
                self.entry["directory"] + "/DECISIONS.md",
                self.entry["directory"] + "/artifacts/.gitkeep",
                self.entry["directory"] + "/branches/.gitkeep",
            ]
            self.git(self.repo, "add", "--", *paths)
            self.git(self.repo, "commit", "-m", "Synthetic registered fixture")
        return result

    def events(self, entry=None):
        entry = entry or self.entry
        path = self.local / entry["directory"] / "actions.jsonl"
        return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    def checkpoint(self, *paths, success=True):
        args = ["checkpoint", "--conversation", "0001", "--message", "Reviewed test change"]
        for path in paths:
            args.extend(["--path", path])
        return self.invoke(*args, success=success)

    def run_manifest(self, **changes):
        source = {
            "schema_version": 1,
            "run_id": "synthetic_run",
            "task": "Record an already observed synthetic command",
            "source_commit": self.git(self.repo, "rev-parse", "HEAD"),
            "source_dirty": False,
            "config_files": [], "data_files": [], "untracked_files": [],
            "seed": None, "seed_reason": "Deterministic synthetic fixture",
            "metrics": {"checks": 1}, "validation": ["Caller supplied test evidence"],
            "artifacts": [], "command": ["synthetic-command"],
            "environment": {"kind": "unit-test"}, "exit_code": 0,
        }
        source.update(changes)
        path = self.base / "run-manifest.json"
        path.write_text(json.dumps(source), encoding="utf-8")
        return path

    def test_main_registration_has_local_identity_and_real_start_commit(self):
        result = self.register_main(commit=False)
        entry = result["conversation"]
        self.assertEqual(entry["directory"], "conversations/0001_research")
        self.assertIsNone(entry["platform_id"])
        self.assertIsNone(entry["parent_id"])
        self.assertEqual(entry["start_commit"], self.initial_commit)
        self.assertTrue(entry["created_utc"])
        self.assertEqual(entry["background"], "Synthetic test background")
        for relative in ("README.md", "STATUS.md", "DECISIONS.md", "artifacts/.gitkeep"):
            self.assertTrue((self.repo / entry["directory"] / relative).is_file())
        self.assertFalse(result["main_commit_created"])
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD"), self.initial_commit)
        self.assertIn("0001_research/README.md", (self.repo / "conversations/INDEX.md").read_text(encoding="utf-8"))

    def test_branch_requires_explicit_main_and_records_source(self):
        self.register_main()
        before = self.git(self.repo, "rev-parse", "HEAD")
        args = ["register", "--id", "0002", "--slug", "extension", "--kind", "branch",
                "--title", "Branch test", "--background", "Inherited explicit task"]
        self.invoke(*args, success=False)
        self.assertFalse((self.repo / "conversations/0001_research/branches/0002_extension").exists())
        entry = self.invoke(*args, "--parent", "0001")["conversation"]
        self.assertEqual(entry["parent_id"], "0001")
        self.assertEqual(entry["directory"], "conversations/0001_research/branches/0002_extension")
        self.assertEqual(entry["start_commit"], before)
        self.assertEqual(entry["background"], "Inherited explicit task")
        self.assertEqual(self.events(entry)[0]["details"]["parent_id"], "0001")
        self.invoke("register", "--id", "0003", "--slug", "nested", "--kind", "branch",
                    "--title", "Invalid deeper parent", "--background", "Test", "--parent", "0002", success=False)

    def test_binding_resumes_exact_id_without_switching_branch(self):
        self.register_main()
        before = self.git(self.repo, "symbolic-ref", "--short", "HEAD")
        self.invoke("bind", "--conversation", "0001")
        value = json.loads((self.repo / ".um-records.local.json").read_text(encoding="utf-8"))
        self.assertEqual(value["current_conversation"], "0001")
        self.assertEqual(self.git(self.repo, "symbolic-ref", "--short", "HEAD"), before)
        self.assertEqual(self.git(self.repo, "ls-files", "--", ".um-records.local.json"), "")
        self.invoke("bind", "--conversation", "1", success=False)
        self.assertEqual(self.events()[-1]["action"], "bind")

    def test_log_appends_commits_and_redacts_sensitive_parameters(self):
        self.register_main()
        credential = "ghp_" + "x" * 30
        self.invoke("log", "--conversation", "0001", "--task", "Observed failure",
                    "--action", "test", "--result", "failed", "--failure", "Synthetic exit 9",
                    "--file", "source.py", "--verification", "Observed exit code",
                    "--artifact", "local/test.txt", "--verification", "token=" + credential)
        events = self.events()
        self.assertEqual(len(events), 2)
        event = events[-1]
        self.assertEqual(event["failure_reason"], "Synthetic exit 9")
        self.assertEqual(event["files"], ["source.py"])
        self.assertEqual(event["artifacts"], ["local/test.txt"])
        self.assertIn("timestamp_utc", event)
        relative = self.entry["directory"] + "/actions.jsonl"
        committed = self.git(self.local, "show", "HEAD:" + relative)
        self.assertNotIn(credential, committed)
        self.assertIn("[REDACTED]", committed)
        self.assertEqual(self.git(self.local, "status", "--porcelain"), "")
        self.assertEqual(self.git(self.local, "remote"), "")

    def test_private_key_log_redacts_the_complete_block(self):
        self.register_main()
        private = "-----BEGIN " + "PRIVATE KEY-----\nsynthetic-sensitive-content\n-----END " + "PRIVATE KEY-----"
        self.invoke("log", "--conversation", "0001", "--task", "test",
                    "--action", "observe", "--result", private)
        self.assertNotIn("synthetic-sensitive-content", json.dumps(self.events()))
        self.assertIn("[REDACTED PRIVATE KEY]", json.dumps(self.events()))
        self.assertNotIn("BEGIN PRIVATE KEY", json.dumps(self.events()))

    def test_checkpoint_commits_only_unicode_space_file_and_preserves_other_work(self):
        self.register_main()
        self.write("共享 代码.py", "answer = 42\n")
        self.write("unrelated.txt", "Do not include\n")
        result = self.checkpoint("共享 代码.py")
        self.assertTrue(result["created_commit"])
        self.assertFalse(result["pushed"])
        names = self.git(self.repo, "-c", "core.quotePath=false", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD")
        self.assertEqual(names, "共享 代码.py")
        self.assertEqual((self.repo / "unrelated.txt").read_text(encoding="utf-8"), "Do not include\n")
        self.assertEqual(self.git(self.repo, "ls-files", "--", "unrelated.txt"), "")
        self.assertEqual(self.events()[-1]["details"]["checkpoint_commit"], result["checkpoint_commit"])

    def test_checkpoint_rejects_unrelated_staging_without_unstaging(self):
        self.register_main()
        self.write("wanted.py", "x = 1\n")
        self.write("unrelated.txt", "Preserve staging\n")
        self.git(self.repo, "add", "--", "unrelated.txt")
        before = self.git(self.repo, "rev-parse", "HEAD")
        self.checkpoint("wanted.py", success=False)
        self.assertEqual(self.git(self.repo, "diff", "--cached", "--name-only"), "unrelated.txt")
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD"), before)

    def test_checkpoint_rejects_main_and_master(self):
        self.register_main()
        self.write("wanted.py", "x = 1\n")
        before = self.git(self.repo, "rev-parse", "HEAD")
        for branch in ("main", "master"):
            with self.subTest(branch=branch):
                self.git(self.repo, "branch", "-m", branch)
                self.checkpoint("wanted.py", success=False)
                self.assertEqual(self.git(self.repo, "rev-parse", "HEAD"), before)

    def test_checkpoint_rejects_directory_traversal_secret_and_local_config(self):
        self.register_main()
        self.write("folder/child.py", "x = 1\n")
        self.write(".env", "ordinary-looking text\n")
        self.write("credential.txt", "api_" + "key=" + "s" * 30 + "\n")
        (self.base / "outside.txt").write_text("outside", encoding="utf-8")
        before = self.git(self.repo, "rev-parse", "HEAD")
        for path in ("folder", "../outside.txt", ".env", "credential.txt", ".um-records.local.json"):
            with self.subTest(path=path):
                self.checkpoint(path, success=False)
                self.assertEqual(self.git(self.repo, "rev-parse", "HEAD"), before)
                self.assertEqual(self.git(self.repo, "diff", "--cached", "--name-only"), "")

    def test_status_no_upstream_does_not_claim_remote_sync(self):
        self.register_main()
        self.invoke("bind", "--conversation", "0001")
        status = self.invoke("status", "--conversation", "0001")
        self.assertTrue(status["ok"])
        self.assertEqual(status["sync"]["state"], "no_upstream")
        self.assertIsNone(status["sync"]["upstream"])
        self.assertIn("no network verification", status["sync"]["evidence"])
        self.assertEqual(status["local_status"], "")
        self.assertEqual(status["local_remotes"], [])

    def test_existing_nonempty_record_root_is_not_initialized_or_overwritten(self):
        self.local.mkdir()
        sentinel = self.local / "precious.txt"
        sentinel.write_bytes(b"preserve exact bytes\r\n")
        self.invoke("init", "--records-root", self.local, success=False)
        self.assertEqual(sentinel.read_bytes(), b"preserve exact bytes\r\n")
        self.assertFalse((self.local / ".git").exists())
        self.assertFalse((self.repo / ".um-records.local.json").exists())

    def test_remote_on_record_repo_blocks_writes(self):
        self.register_main()
        before = self.git(self.local, "rev-parse", "HEAD")
        self.git(self.local, "remote", "add", "test-remote", "https://example.invalid/forbidden.git")
        self.invoke("log", "--conversation", "0001", "--task", "test",
                    "--action", "observe", "--result", "done", success=False)
        self.assertEqual(self.git(self.local, "rev-parse", "HEAD"), before)
        self.assertEqual(len(self.events()), 1)

    def test_tracked_machine_configuration_is_rejected_despite_ignore_rule(self):
        self.register_main()
        self.git(self.repo, "add", "--force", "--", ".um-records.local.json")
        self.git(self.repo, "commit", "-m", "Synthetic unsafe tracking fixture")
        self.invoke("status", "--conversation", "0001", success=False)

    def test_duplicate_registration_preserves_existing_documents(self):
        self.register_main()
        status = self.repo / self.entry["directory"] / "STATUS.md"
        status.write_bytes(b"preserved status\r\n")
        before = self.git(self.local, "rev-parse", "HEAD")
        self.invoke("register", "--id", "0001", "--slug", "different", "--kind", "main",
                    "--title", "Another title", "--background", "Another task", success=False)
        self.assertEqual(status.read_bytes(), b"preserved status\r\n")
        self.assertEqual(self.git(self.local, "rev-parse", "HEAD"), before)
        self.assertFalse((self.repo / "conversations/0001_different").exists())

    def test_ignored_action_log_blocks_append_instead_of_silently_omitting_it(self):
        self.register_main()
        ignore = self.local / ".gitignore"
        ignore.write_text(ignore.read_text(encoding="utf-8") + "*.jsonl\n", encoding="utf-8")
        before = (self.local / self.entry["directory"] / "actions.jsonl").read_bytes()
        self.invoke("log", "--conversation", "0001", "--task", "test",
                    "--action", "observe", "--result", "done", success=False)
        self.assertEqual((self.local / self.entry["directory"] / "actions.jsonl").read_bytes(), before)

    def test_dirty_failed_run_records_exact_source_snapshots_and_hashes(self):
        self.register_main()
        config_bytes = b'\xef\xbb\xbf{\r\n  "value": 7\r\n}\r\n'
        (self.repo / "run config.json").write_bytes(config_bytes)
        self.write("data.csv", "time,value\n0,1\n")
        self.git(self.repo, "add", "--", "run config.json", "data.csv")
        self.git(self.repo, "commit", "-m", "Synthetic inputs")
        self.write("source.py", "value = 2\n")
        untracked_bytes = b'# exact source\r\nvalue = 3\r\n'
        (self.repo / "new source.py").write_bytes(untracked_bytes)
        stderr = self.base / "observed-stderr.txt"
        stderr.write_text("Synthetic observed failure", encoding="utf-8")
        manifest = self.run_manifest(
            source_dirty=True, config_files=["run config.json"], data_files=["data.csv"],
            untracked_files=["new source.py"], exit_code=7,
            validation=["Synthetic failure; no solver was run"], artifacts=[str(stderr)],
        )
        result = self.invoke("record-run", "--conversation", "0001", "--manifest", manifest)
        self.assertFalse(result["executed_experiment"])
        run = Path(result["run_directory"])
        saved = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(saved["exit_code"], 7)
        self.assertTrue(saved["source_dirty"])
        self.assertEqual(saved["source_commit"], self.git(self.repo, "rev-parse", "HEAD"))
        self.assertEqual(saved["seed_reason"], "Deterministic synthetic fixture")
        self.assertEqual(saved["metrics"], {"checks": 1})
        self.assertEqual(saved["artifacts"], [str(stderr)])
        self.assertIn("not that they were used", saved["registration_note"])
        self.assertEqual((run / "config_files/run config.json").read_bytes(), config_bytes)
        self.assertEqual((run / "untracked_files/new source.py").read_bytes(), untracked_bytes)
        self.assertEqual(saved["observed_input_files"]["config_files"]["run config.json"]["sha256"], hashlib.sha256(config_bytes).hexdigest())
        self.assertEqual(saved["dirty_patch_sha256"], hashlib.sha256((run / "dirty.patch").read_bytes()).hexdigest())
        self.assertFalse(saved["stored_patch_redacted"])
        self.assertEqual(self.git(self.local, "status", "--porcelain"), "")
        self.assertEqual(self.events()[-1]["details"]["exit_code"], 7)
        self.invoke("record-run", "--conversation", "0001", "--manifest", manifest, success=False)

    def test_run_command_secret_argument_is_redacted(self):
        self.register_main()
        sensitive = "EXAMPLE_FAKE_VALUE_123"
        manifest = self.run_manifest(command=["python", "run.py", "--password", sensitive])
        result = self.invoke("record-run", "--conversation", "0001", "--manifest", manifest)
        content = (Path(result["run_directory"]) / "manifest.json").read_text(encoding="utf-8")
        self.assertNotIn(sensitive, content)
        self.assertIn("[REDACTED]", content)

    def test_status_detects_ignored_run_evidence(self):
        self.register_main()
        manifest = self.run_manifest()
        self.invoke("record-run", "--conversation", "0001", "--manifest", manifest)
        ignore = self.local / ".gitignore"
        ignore.write_text(ignore.read_text(encoding="utf-8") + "**/runs/**\n", encoding="utf-8")
        self.git(self.local, "add", "--", ".gitignore")
        self.git(self.local, "commit", "-m", "Synthetic bad ignore fixture")
        result = self.invoke("status", "--conversation", "0001", success=False)
        status = json.loads(result.stdout)
        self.assertFalse(status["ok"])
        self.assertTrue(any("ignored" in issue and "runs/" in issue for issue in status["issues"]))

    def test_unicode_run_snapshot_is_reported_as_tracked(self):
        self.register_main()
        relative = "配置 文件.json"
        content = b'\xef\xbb\xbf{"value": 7}\r\n'
        (self.repo / relative).write_bytes(content)
        self.git(self.repo, "add", "--", relative)
        self.git(self.repo, "commit", "-m", "Synthetic Unicode input")
        manifest = self.run_manifest(config_files=[relative])
        result = self.invoke("record-run", "--conversation", "0001", "--manifest", manifest)
        self.assertEqual((Path(result["run_directory"]) / "config_files" / relative).read_bytes(), content)
        status = self.invoke("status", "--conversation", "0001")
        self.assertTrue(status["ok"])
        self.assertEqual(status["issues"], [])

    def test_local_git_blobs_preserve_bytes_with_autocrlf_enabled(self):
        self.register_main()
        self.git(self.local, "config", "core.autocrlf", "true")
        relative = "原始 配置.json"
        original = b'\xef\xbb\xbf{\r\n  "value": 7\r\n}\r\n'
        (self.repo / relative).write_bytes(original)
        self.git(self.repo, "add", "--", relative)
        self.git(self.repo, "commit", "-m", "Synthetic exact-byte input")
        manifest = self.run_manifest(config_files=[relative])
        result = self.invoke("record-run", "--conversation", "0001", "--manifest", manifest)
        snapshot = Path(result["run_directory"]) / "config_files" / relative
        self.assertEqual(snapshot.read_bytes(), original)
        relative_snapshot = snapshot.relative_to(self.local).as_posix()
        blob = subprocess.run(
            ["git", "-C", str(self.local), "show", "HEAD:" + relative_snapshot],
            env=self.env, capture_output=True,
        )
        self.assertEqual(blob.returncode, 0, blob.stderr)
        self.assertEqual(blob.stdout, original)
        self.assertEqual(hashlib.sha256(blob.stdout).hexdigest(), hashlib.sha256(original).hexdigest())
        self.assertEqual(self.git(self.local, "show", "HEAD:.gitattributes"), "* -text")
        log_relative = self.entry["directory"] + "/actions.jsonl"
        log_blob = subprocess.run(
            ["git", "-C", str(self.local), "show", "HEAD:" + log_relative],
            env=self.env, capture_output=True,
        )
        self.assertEqual(log_blob.returncode, 0, log_blob.stderr)
        parsed = [json.loads(line) for line in log_blob.stdout.decode("utf-8").splitlines()]
        self.assertEqual(parsed, self.events())
        self.assertEqual(parsed[-1]["action"], "record-run")
        self.assertEqual(self.git(self.local, "status", "--porcelain"), "")

    def test_commit_exact_long_path_list_uses_stdin(self):
        specification = importlib.util.spec_from_file_location("records_under_test", SCRIPT)
        module = importlib.util.module_from_spec(specification)
        specification.loader.exec_module(module)
        directory = "payload-" + "x" * 112
        paths = []
        for number in range(250):
            relative = f"{directory}/file-{number:04d}-reviewed-source.txt"
            self.write(relative, f"synthetic value {number}\n")
            paths.append(relative)
        self.assertGreater(sum(len(path) + 1 for path in paths), 32767)
        with patch.dict(os.environ, self.env):
            commit = module.commit_exact(self.repo, paths, "Synthetic long path-list checkpoint")
        self.assertEqual(commit, self.git(self.repo, "rev-parse", "HEAD"))
        changed = self.git(self.repo, "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD").splitlines()
        self.assertEqual(set(changed), set(paths))
        self.assertEqual(self.git(self.repo, "status", "--porcelain"), "")
        exclude = self.repo / ".git/info/exclude"
        exclude.write_text(exclude.read_text(encoding="utf-8") + paths[0] + "\n", encoding="utf-8")
        self.write(paths[0], "Changed but now excluded by explicit local policy\n")
        with patch.dict(os.environ, self.env):
            with self.assertRaises(module.RecordError):
                module.commit_exact(self.repo, paths, "Must reject one excluded file")
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD"), commit)
        self.assertEqual(self.git(self.repo, "diff", "--cached", "--name-only"), "")

    def test_run_rejects_false_commit_dirty_state_and_incomplete_untracked_list(self):
        self.register_main()
        self.write("new.py", "value = 3\n")
        for overrides in (
            {"source_commit": "0" * 40, "source_dirty": True, "untracked_files": ["new.py"]},
            {"source_dirty": False, "untracked_files": ["new.py"]},
            {"source_dirty": True, "untracked_files": []},
        ):
            with self.subTest(overrides=overrides):
                manifest = self.run_manifest(**overrides)
                self.invoke("record-run", "--conversation", "0001", "--manifest", manifest, success=False)
                self.assertFalse((self.local / self.entry["directory"] / "runs/synthetic_run").exists())


if __name__ == "__main__":
    unittest.main()
