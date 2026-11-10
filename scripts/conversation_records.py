#!/usr/bin/env python3
"""Explicit conversation records and local checkpoints. Python 3.10+, stdlib only.

This tool records only its own invocations; it is not a chat exporter or tool-call
interceptor. All Git additions use exact files. It never pushes or switches Git
branches. See docs/workflow/CONVERSATIONS.md for the workflow and limitations.
"""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import uuid


CONFIG = ".um-records.local.json"
REGISTRY = "conversations/registry.json"
MARKER = ".record-repository.json"
PURPOSE = "um-conversation-records"
ID_RE = re.compile(r"[0-9]{4}")
SLUG_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
TOKEN_RE = re.compile(r"(?:sk-(?:proj-)?[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})")
PRIVATE_RE = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----")
PRIVATE_BLOCK_RE = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----[\s\S]*?(?:-----END (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----|$)")
QUOTED_ASSIGNMENT_RE = re.compile(r"(?i)((?:api[_-]?key|access[_-]?token|authorization|password|passwd|secret|token)[\"']?\s*[:=]\s*)([\"'])([^\r\n]*?)\2")
FLAG_SECRET_RE = re.compile(r"(?i)(--(?:api-key|api_key|access-token|access_token|password|passwd|secret|token)\s+)(?:\"[^\"]*\"|'[^']*'|[^\s]+)")
ASSIGNMENT_RE = re.compile(
    r"(?i)((?:api[_-]?key|access[_-]?token|authorization|password|passwd|secret|token)"
    r"[\"']?\s*[:=]\s*[\"']?)([^\s\"',;}]{8,})"
)
BEARER_RE = re.compile(r"(?i)(Bearer\s+)[A-Za-z0-9._~+/-]{8,}")
PLACEHOLDERS = {"[REDACTED]", "REDACTED", "placeholder", "<redacted>", "<secret>"}
MAX_TEXT_BYTES = 10 * 1024 * 1024


class RecordError(RuntimeError):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def redact_text(value):
    value = PRIVATE_BLOCK_RE.sub("[REDACTED PRIVATE KEY]", value)
    value = TOKEN_RE.sub("[REDACTED]", value)
    value = BEARER_RE.sub(r"\1[REDACTED]", value)
    value = FLAG_SECRET_RE.sub(r"\1[REDACTED]", value)
    value = QUOTED_ASSIGNMENT_RE.sub(lambda m: m[1] + m[2] + (m[3] if m[3] in PLACEHOLDERS else "[REDACTED]") + m[2], value)
    return ASSIGNMENT_RE.sub(lambda m: m[1] + (m[2] if m[2] in PLACEHOLDERS else "[REDACTED]"), value)


def redact(value):
    if isinstance(value, dict):
        return {k: ("[REDACTED]" if k.lower() in {"password", "passwd", "secret", "token", "api_key", "access_token", "authorization", "openai_api_key", "anthropic_api_key", "aws_secret_access_key", "aws_session_token"} else redact(v)) for k, v in value.items()}
    if isinstance(value, list):
        result = []
        previous_sensitive_flag = False
        flags = {"--api-key", "--api_key", "--access-token", "--access_token", "--password", "--passwd", "--secret", "--token", "--authorization"}
        for item in value:
            result.append("[REDACTED]" if previous_sensitive_flag else redact(item))
            previous_sensitive_flag = isinstance(item, str) and item.lower() in flags
        return result
    return redact_text(value) if isinstance(value, str) else value


def json_text(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def read_json(path):
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise RecordError(f"Cannot read valid JSON: {path}: {type(exc).__name__}") from exc


def atomic_text(path, text):
    if path.is_symlink():
        raise RecordError(f"Refusing symbolic link: {path}")
    temp = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    try:
        with temp.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def git(repo, *args, ok=(0,), binary=False, input_bytes=None):
    result = subprocess.run(["git", "--literal-pathspecs", "-C", str(repo), *args], capture_output=True, input=input_bytes)
    if result.returncode not in ok:
        detail = result.stderr.decode("utf-8", "replace").strip()
        raise RecordError(redact_text(f"Git failed ({result.returncode}): {detail}"))
    return result.stdout if binary else result.stdout.decode("utf-8", "strict").strip()


def root_at(path):
    path = path.expanduser().resolve()
    actual = Path(git(path, "rev-parse", "--show-toplevel")).resolve()
    if actual != path:
        raise RecordError("--repo must name the exact Git root, not a parent or subdirectory")
    return actual


def safe_relative(root, value, must_exist=False):
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise RecordError("Paths must be nonempty relative paths using / separators")
    parts = PurePosixPath(value)
    if parts.is_absolute() or any(p in {"..", ".git"} for p in parts.parts) or ":" in value or any(c in value for c in "*?[]"):
        raise RecordError(f"Unsafe or nonliteral path: {value}")
    if parts.as_posix() != value or value in {".", ""}:
        raise RecordError(f"Path must be canonical and explicit: {value}")
    target = root.joinpath(*parts.parts)
    # Reject links and Windows junctions even when they happen to point inward.
    current = root
    for part in parts.parts:
        current = current / part
        if current.is_symlink() or (hasattr(current, "is_junction") and current.is_junction()):
            raise RecordError(f"Refusing a linked path: {value}")
    if not target.resolve().is_relative_to(root.resolve()):
        raise RecordError(f"Path escapes repository: {value}")
    if must_exist and not target.exists():
        raise RecordError(f"Missing path: {value}")
    return target


@contextmanager
def lock(path):
    try:
        handle = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise RecordError(f"Another operation or interrupted lock exists: {path}; inspect it before removing it") from exc
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            stream.write(json_text({"pid": os.getpid(), "started_utc": now()}))
        yield
    finally:
        path.unlink()


def staged(repo):
    return set(filter(None, git(repo, "diff", "--cached", "--name-only", "-z").split("\x00")))


def ensure_identity(repo):
    git(repo, "var", "GIT_AUTHOR_IDENT")
    git(repo, "var", "GIT_COMMITTER_IDENT")


def ignored(repo, relative):
    return relative in ignored_paths(repo, [relative])


def ignored_paths(repo, paths):
    # check-ignore accepts literal file names, not Git pathspec magic.
    proc = subprocess.run(["git", "-C", str(repo), "check-ignore", "--no-index", "--stdin", "-z"], capture_output=True, input=b"".join(path.encode("utf-8") + b"\0" for path in paths))
    if proc.returncode not in (0, 1):
        raise RecordError("git check-ignore failed: " + redact_text(proc.stderr.decode("utf-8", "replace").strip()))
    return set(filter(None, proc.stdout.decode("utf-8").split("\x00")))


def commit_exact(repo, paths, message):
    paths = list(dict.fromkeys(paths))
    if staged(repo) - set(paths):
        raise RecordError("Unrelated staged changes exist; preserve and resolve them before this operation")
    for path in paths:
        safe_relative(repo, path, must_exist=True)
    excluded = ignored_paths(repo, paths)
    if excluded:
        raise RecordError(f"Required records/files are ignored: {sorted(excluded)}; correct the ignore rules first")
    ensure_identity(repo)
    # NUL-delimited stdin avoids Windows' command-line length limit without
    # widening the explicit file list or interpreting pathspec metacharacters.
    git(repo, "add", "--pathspec-from-file=-", "--pathspec-file-nul", input_bytes=b"".join(path.encode("utf-8") + b"\0" for path in paths))
    if not staged(repo):
        return git(repo, "rev-parse", "HEAD")
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "HEAD")


def registry(repo):
    path = safe_relative(repo, REGISTRY)
    value = read_json(path) if path.exists() else {"schema_version": 1, "conversations": []}
    if not isinstance(value, dict) or set(value) != {"schema_version", "conversations"} or value["schema_version"] != 1 or not isinstance(value["conversations"], list):
        raise RecordError("Unsupported registry schema")
    seen = set()
    rows = {}
    fields = {"id", "slug", "title", "kind", "parent_id", "directory", "created_utc", "start_commit", "background", "platform_id", "status"}
    for row in value["conversations"]:
        if not isinstance(row, dict) or set(row) != fields:
            raise RecordError("Invalid conversation fields in registry")
        if any(not isinstance(row[key], str) for key in fields - {"parent_id", "platform_id"}) or any(row[key] is not None and not isinstance(row[key], str) for key in ("parent_id", "platform_id")):
            raise RecordError("Invalid conversation field types")
        if not ID_RE.fullmatch(row["id"]) or row["id"] in seen or not SLUG_RE.fullmatch(row["slug"]):
            raise RecordError("Duplicate or invalid stable identifier")
        seen.add(row["id"])
        rows[row["id"]] = row
    for row in rows.values():
        if row["kind"] == "main" and row["parent_id"] is None:
            expected = f"conversations/{row['id']}_{row['slug']}"
        elif row["kind"] == "branch" and row["parent_id"] in rows and rows[row["parent_id"]]["kind"] == "main":
            parent = rows[row["parent_id"]]
            expected = f"conversations/{parent['id']}_{parent['slug']}/branches/{row['id']}_{row['slug']}"
        else:
            raise RecordError("A branch must name an existing main conversation; parentage is never inferred")
        if row["directory"] != expected:
            raise RecordError("Directory does not match the registered immutable identity")
        safe_relative(repo, expected)
    return value


def conversation(repo, identifier):
    entries = registry(repo)["conversations"]
    matches = [entry for entry in entries if entry["id"] == identifier]
    if len(matches) != 1:
        raise RecordError("Conversation is not registered; supply its exact stable ID")
    return matches[0]


def index_text(value):
    def cell(text):
        return str(text).replace("|", "\\|").replace("\n", " ")
    lines = ["# Conversation index", "", "Generated from `registry.json` by `register` or `index`. IDs and directories remain stable when titles change.", "", "| ID | Title | Parent | Directory | Status |", "|---|---|---|---|---|"]
    for row in value["conversations"]:
        directory = row["directory"].removeprefix("conversations/")
        lines.append(f"| {row['id']} | {cell(row['title'])} | {row['parent_id'] or '—'} | [{directory}]({directory}/README.md) | {cell(row['status'])} |")
    lines.extend(["", "Only explicitly registered conversations are listed. Local numbers are not platform chat IDs.", ""])
    return "\n".join(lines)


def config(repo):
    path = safe_relative(repo, CONFIG, must_exist=True)
    if not ignored(repo, CONFIG):
        raise RecordError(f"{CONFIG} must be ignored before storing machine-specific paths")
    if git(repo, "ls-files", "--", CONFIG):
        raise RecordError(f"{CONFIG} is tracked despite ignore rules; do not publish it")
    value = read_json(path)
    if not isinstance(value, dict) or value.get("schema_version") != 1 or not isinstance(value.get("records_root"), str):
        raise RecordError("Invalid local configuration")
    return value


def verify_local(repo, local):
    local = local.expanduser().resolve()
    if local.is_relative_to(repo) or repo.is_relative_to(local):
        raise RecordError("Local records must be in a separate directory outside the project tree")
    if not (local / ".git").is_dir() or (local / ".git").is_symlink() or root_at(local) != local:
        raise RecordError("Local records must be an independent ordinary Git repository")
    ancestor_git = subprocess.run(["git", "-C", str(local.parent), "rev-parse", "--show-toplevel"], capture_output=True)
    if ancestor_git.returncode == 0:
        raise RecordError("Local records cannot be nested inside another Git repository")
    if git(local, "remote"):
        raise RecordError("Local records repository has a remote; refuse to write or upload")
    marker = read_json(local / MARKER)
    if not isinstance(marker, dict) or marker.get("schema_version") != 1 or marker.get("purpose") != PURPOSE:
        raise RecordError("Existing repository is not marked for conversation records; no automatic adoption")
    return local


def local_for(repo):
    return verify_local(repo, Path(config(repo)["records_root"]))


def local_ready(local):
    if staged(local):
        raise RecordError("Local records repository has staged changes; preserve and resolve them first")
    ensure_identity(local)


def write_action(repo, local, entry, task, action, result, files=None, failure=None, verification=None, artifacts=None, extra=None):
    relative = entry["directory"] + "/actions.jsonl"
    target = safe_relative(local, relative)
    if ignored(local, relative):
        raise RecordError("actions.jsonl is ignored; correct local ignore rules before logging")
    target.parent.mkdir(parents=True, exist_ok=True)
    event = redact({"schema_version": 1, "timestamp_utc": now(), "conversation_id": entry["id"], "task": task, "action": action, "files": files or [], "result": result, "failure_reason": failure, "verification": verification or [], "artifacts": artifacts or [], "source_commit": git(repo, "rev-parse", "HEAD"), "details": extra or {}})
    # Validate all existing records before appending; never silently repair a torn line.
    if target.exists():
        content = target.read_text(encoding="utf-8")
        if content and not content.endswith("\n"):
            raise RecordError("Existing actions.jsonl ends with an incomplete line; preserve it and repair explicitly")
        for line in content.splitlines():
            json.loads(line)
    with target.open("a", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")
        stream.flush()
        os.fsync(stream.fileno())
    return relative


def init_command(repo, args):
    if not ignored(repo, CONFIG) or not ignored(repo, ".um-records.lock"):
        raise RecordError("Add /.um-records.local.json and /.um-records.lock to the project ignore rules first")
    local = Path(args.records_root).expanduser().resolve()
    if local.is_relative_to(repo) or repo.is_relative_to(local):
        raise RecordError("Local records must be outside the project tree")
    ancestor = local.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    inside = subprocess.run(["git", "-C", str(ancestor), "rev-parse", "--show-toplevel"], capture_output=True)
    if inside.returncode == 0:
        raise RecordError("Refusing to initialize local records inside any existing ancestor Git repository")
    ensure_identity(ancestor)
    local.parent.mkdir(parents=True, exist_ok=True)
    # A sibling lock covers the initial existence check and git init as well as
    # later reuse. Different source worktrees cannot both initialize this root.
    with lock(repo / ".um-records.lock"), lock(local.parent / ("." + local.name + ".init.lock")):
        existing = local.exists() and any(local.iterdir())
        if existing:
            verify_local(repo, local)
        else:
            local.mkdir(parents=True, exist_ok=True)
        with lock(local / ".records.lock"):
            if not existing:
                git(local, "init")
                ensure_identity(local)
                (local / MARKER).write_text(json_text({"schema_version": 1, "purpose": PURPOSE, "created_utc": now()}), encoding="utf-8")
                (local / ".gitignore").write_text(".records.lock\n__pycache__/\n*.py[cod]\n.venv/\nvenv/\n.pytest_cache/\n", encoding="utf-8")
                (local / ".gitattributes").write_text("* -text\n", encoding="utf-8")
                (local / "README.md").write_text("# Local conversation records\n\nIndependent local Git repository; no remote and no uploads.\n`conversations/` mirrors registered main conversations and branches.\n`actions.jsonl` and `runs/` are intentionally tracked. Cache and runtime environments are excluded.\nThis repository is not a full chat export or a backup of every project file.\n", encoding="utf-8")
                commit_exact(local, [MARKER, ".gitignore", ".gitattributes", "README.md"], "Initialize local conversation records")
            verify_local(repo, local)
            path = safe_relative(repo, CONFIG)
            value = config(repo) if path.exists() else {"schema_version": 1, "records_root": str(local), "current_conversation": None}
            if Path(value["records_root"]).resolve() != local:
                raise RecordError("Existing configuration points elsewhere; refusing to replace it")
            atomic_text(path, json_text(value))
    return {"records_root": str(local), "configuration": str(path), "local_commit": git(local, "rev-parse", "HEAD"), "remotes": []}


def register_command(repo, args, local):
    value = registry(repo)
    if not ID_RE.fullmatch(args.id) or not SLUG_RE.fullmatch(args.slug):
        raise RecordError("Use a four-digit stable ID and a lowercase ASCII slug separated with hyphens")
    if any(row["id"] == args.id for row in value["conversations"]):
        raise RecordError("Stable ID is already registered; use bind to resume it")
    if not args.title.strip() or not args.background.strip():
        raise RecordError("Title and inherited/task background are required")
    if args.kind == "main":
        if args.parent is not None:
            raise RecordError("Main conversations cannot have a parent")
        directory = f"conversations/{args.id}_{args.slug}"
    else:
        if args.parent is None:
            raise RecordError("Branch registration requires the explicit parent main conversation ID")
        parent = conversation(repo, args.parent)
        if parent["kind"] != "main":
            raise RecordError("Parent must be a main conversation")
        directory = f"{parent['directory']}/branches/{args.id}_{args.slug}"
    target = safe_relative(repo, directory)
    if target.exists() or safe_relative(local, directory).exists():
        raise RecordError("Conversation directory already exists; refusing to overwrite or infer ownership")
    entry = {"id": args.id, "slug": args.slug, "title": args.title, "kind": args.kind, "parent_id": args.parent, "directory": directory, "created_utc": now(), "start_commit": git(repo, "rev-parse", "HEAD"), "background": args.background, "platform_id": args.platform_id, "status": "active"}
    for text in (args.title, args.background, args.platform_id or ""):
        reject_secret(text)
    target.mkdir(parents=True)
    (target / "artifacts").mkdir()
    if args.kind == "main":
        (target / "branches").mkdir()
        (target / "branches" / ".gitkeep").write_text("", encoding="utf-8")
    parent_description = args.parent if args.parent else "None; explicitly registered as a main conversation"
    platform_description = args.platform_id if args.platform_id else "Unavailable; this binding uses a stable local number, not a fabricated platform ID"
    readme = f"# {args.title}\n\n- Stable local ID: `{args.id}`\n- Kind: `{args.kind}`\n- Parent main conversation: {parent_description}\n- Created (UTC): {entry['created_utc']}\n- Starting Git commit: `{entry['start_commit']}`\n- Platform chat ID: {platform_description}\n\n## Inherited/task background\n\n{args.background}\n\n## Continuation\n\nRead [STATUS.md](STATUS.md) and [DECISIONS.md](DECISIONS.md).\nStore conversation-specific shareable outputs in `artifacts/`; link shared code and data without duplicating them.\nThe conversation directory does not select a Git branch. Keep its path unchanged when renaming the chat.\n"
    (target / "README.md").write_text(readme, encoding="utf-8", newline="\n")
    (target / "STATUS.md").write_text(f"# Status — {args.id}\n\nRegistered {entry['created_utc']}. Status: active.\n\nVerified: the directory was registered against `{entry['start_commit']}`.\nNo research execution or result is asserted by registration.\n\nTask background: {args.background}\n\nNext: inspect current Git changes and the relevant project status, perform the first bounded task, then replace this initial status with verified/unverified/failed work and exact reproduction commands.\n\nResume from the repository root:\n\n```powershell\npython -X utf8 scripts/conversation_records.py bind --conversation {args.id}\npython -X utf8 scripts/conversation_records.py status --conversation {args.id}\n```\n", encoding="utf-8", newline="\n")
    (target / "DECISIONS.md").write_text(f"# Decisions — {args.id}\n\n## {entry['created_utc']} — Registration\n\nRegistered as `{args.kind}` with parent `{args.parent or 'none'}` based on explicit input.\nInherited/task background: {args.background}\nNo historical conversation or parent-child relationship was inferred from research files.\n", encoding="utf-8", newline="\n")
    (target / "artifacts" / ".gitkeep").write_text("", encoding="utf-8")
    value["conversations"].append(entry)
    registry_path = safe_relative(repo, REGISTRY)
    atomic_text(registry_path, json_text(value))
    atomic_text(safe_relative(repo, "conversations/INDEX.md"), index_text(value))
    path = write_action(repo, local, entry, args.title, "register", "registered", files=[directory, REGISTRY, "conversations/INDEX.md"], verification=["Explicit parent validated; starting commit read from Git"], extra={"kind": args.kind, "parent_id": args.parent, "start_commit": entry["start_commit"]})
    local_commit = commit_exact(local, [path], f"Register conversation {args.id}")
    return {"conversation": entry, "local_commit": local_commit, "main_commit_created": False}


def reject_secret(text):
    if PRIVATE_RE.search(text) or TOKEN_RE.search(text) or redact_text(text) != text:
        raise RecordError("Potential sensitive content detected; inspect and redact it locally before proceeding (content not printed)")


def checkpoint_file(repo, relative):
    path = safe_relative(repo, relative, must_exist=True)
    if not path.is_file():
        raise RecordError(f"Checkpoint paths must name individual files: {relative}")
    parts = set(PurePosixPath(relative).parts)
    excluded = {".venv", "venv", "env", "__pycache__", ".pytest_cache", ".cache", "node_modules", ".git", "runs"}
    if parts & excluded or path.name.lower().startswith(".env") or path.name in {CONFIG, ".um-records.lock", "actions.jsonl"} or path.suffix.lower() in {".key", ".pem", ".p12", ".pfx", ".log", ".pyc", ".pyo"}:
        raise RecordError(f"File is excluded from shareable checkpoints: {relative}")
    if ignored(repo, relative):
        raise RecordError(f"File is ignored: {relative}")
    if path.stat().st_size > MAX_TEXT_BYTES:
        raise RecordError(f"Large files need separate explicit publication review: {relative}")
    try:
        content = path.read_text(encoding="utf-8-sig")
    except UnicodeError as exc:
        raise RecordError(f"Binary/non-UTF-8 files need separate explicit publication review: {relative}") from exc
    if "\x00" in content:
        raise RecordError(f"Binary files need separate explicit publication review: {relative}")
    reject_secret(content)
    return path


def checkpoint_command(repo, args, local):
    entry = conversation(repo, args.conversation)
    branch = git(repo, "symbolic-ref", "--quiet", "--short", "HEAD", ok=(0, 1))
    if not branch or branch in {"main", "master"}:
        raise RecordError("Checkpoint requires an independent named work branch, not main/master or detached HEAD")
    if staged(repo) - set(args.path):
        raise RecordError("Unrelated staged changes exist; checkpoint will not include or unstage them")
    for relative in args.path:
        checkpoint_file(repo, relative)
    reject_secret(args.message)
    before = git(repo, "rev-parse", "HEAD")
    after = commit_exact(repo, args.path, args.message)
    event_path = write_action(repo, local, entry, args.message, "checkpoint", "committed" if after != before else "no_changes", files=args.path, verification=["Explicit UTF-8 files reviewed by guard; no unrelated staged files", "No push performed"], extra={"before_commit": before, "checkpoint_commit": after, "git_branch": branch, "remaining_status": git(repo, "status", "--porcelain=v1", "--untracked-files=all")})
    local_commit = commit_exact(local, [event_path], f"Record checkpoint for {entry['id']}")
    return {"checkpoint_commit": after, "created_commit": after != before, "local_commit": local_commit, "pushed": False}


def record_run_command(repo, args, local):
    entry = conversation(repo, args.conversation)
    source = read_json(Path(args.manifest).expanduser().resolve())
    required = {"schema_version", "run_id", "task", "source_commit", "source_dirty", "config_files", "data_files", "untracked_files", "seed", "seed_reason", "metrics", "validation", "artifacts", "command", "environment", "exit_code"}
    if not isinstance(source, dict) or not required.issubset(source) or set(source) - required - {"failure_reason"} or source["schema_version"] != 1:
        raise RecordError("Run manifest must use the exact documented schema_version 1 fields")
    if not isinstance(source["run_id"], str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", source["run_id"]):
        raise RecordError("Invalid run_id")
    if source["source_commit"] != git(repo, "rev-parse", "HEAD"):
        raise RecordError("Run registration requires the current source commit; historic runs stay in their existing archives")
    if type(source["source_dirty"]) is not bool or type(source["exit_code"]) is not int:
        raise RecordError("source_dirty must be boolean; exit_code must be integer")
    for key in ("config_files", "data_files", "untracked_files", "artifacts", "command"):
        if not isinstance(source[key], list) or any(not isinstance(v, str) for v in source[key]):
            raise RecordError(f"{key} must be a list of strings")
    if not isinstance(source["metrics"], dict) or not isinstance(source["environment"], dict):
        raise RecordError("metrics and environment must be objects")
    if not isinstance(source["task"], str) or not source["task"].strip() or not isinstance(source["seed_reason"], str) or (source["seed"] is not None and type(source["seed"]) is not int):
        raise RecordError("task and seed_reason must be strings; seed must be integer or null")
    if source.get("failure_reason") is not None and not isinstance(source["failure_reason"], str):
        raise RecordError("failure_reason must be a string or null")
    if source["seed"] is None and not source["seed_reason"]:
        raise RecordError("A null seed requires a reason")
    patch = git(repo, "diff", "--no-ext-diff", "--binary", "HEAD", binary=True)
    untracked = set(filter(None, git(repo, "ls-files", "--others", "--exclude-standard", "-z").split("\x00")))
    if set(source["untracked_files"]) != untracked:
        raise RecordError("untracked_files must explicitly enumerate every current untracked nonignored file; commit or classify them first")
    dirty = bool(patch or untracked)
    if source["source_dirty"] != dirty:
        raise RecordError("source_dirty does not match the current working tree")
    relative = f"{entry['directory']}/runs/{source['run_id']}"
    target = safe_relative(local, relative)
    if target.exists():
        raise RecordError("Run ID already exists; runs are immutable")
    inputs = {"config_files": {}, "data_files": {}, "untracked_files": {}}
    snapshots = {}
    for category in inputs:
        for relative_input in source[category]:
            path = safe_relative(repo, relative_input, must_exist=True)
            if not path.is_file():
                raise RecordError("Run inputs must be explicit regular files")
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            inputs[category][relative_input] = {"sha256": digest, "bytes": path.stat().st_size}
            if category != "data_files":
                checkpoint_file(repo, relative_input)
                snapshots[f"{category}/{relative_input}"] = path.read_bytes()
    try:
        patch_text = patch.decode("utf-8")
    except UnicodeError as exc:
        raise RecordError("Dirty patch is not UTF-8; commit exact source first") from exc
    if "GIT binary patch" in patch_text:
        raise RecordError("Binary dirty files cannot be safely archived by this helper; commit reviewed source first")
    clean_patch = redact_text(patch_text)
    if PRIVATE_RE.search(clean_patch):
        raise RecordError("Private-key material in dirty source; do not archive it")
    stored_patch = patch if clean_patch == patch_text else clean_patch.encode("utf-8")
    failure_reason = source.get("failure_reason")
    if source["exit_code"] != 0 and not failure_reason:
        failure_reason = "The caller reported a nonzero exit code but did not provide its cause; inspect supplied validation and artifacts."
    manifest = redact(dict(source, failure_reason=failure_reason, registered_utc=now(), conversation_id=entry["id"], observed_input_files=inputs, dirty_patch_sha256=hashlib.sha256(patch).hexdigest() if patch else None, stored_patch_sha256=hashlib.sha256(stored_patch).hexdigest() if patch else None, stored_patch_redacted=clean_patch != patch_text, registration_note="Post-run registration verifies the current files, not that they were used during the earlier command. The caller supplies run outcomes and must preserve runtime evidence."))
    output_paths = [relative + "/manifest.json"]
    if patch:
        output_paths.append(relative + "/dirty.patch")
    output_paths.extend(relative + "/" + name for name in snapshots)
    for path in output_paths:
        if ignored(local, path):
            raise RecordError(f"Run record would be ignored: {path}")
    target.mkdir(parents=True)
    (target / "manifest.json").write_text(json_text(manifest), encoding="utf-8")
    if patch:
        (target / "dirty.patch").write_bytes(stored_patch)
    for name, content in snapshots.items():
        output = safe_relative(target, name)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(content)
    event = write_action(repo, local, entry, source["task"], "record-run", "registered_failure" if source["exit_code"] != 0 else "registered", files=source["config_files"] + source["data_files"] + source["untracked_files"], failure=failure_reason, verification=["Current commit, dirty state and input SHA-256 captured; supplied outcomes are not independently rerun"], artifacts=[relative + "/manifest.json"], extra={"run_id": source["run_id"], "exit_code": source["exit_code"]})
    output_paths.append(event)
    local_commit = commit_exact(local, output_paths, f"Record run {source['run_id']} for {entry['id']}")
    return {"run_directory": str(target), "local_commit": local_commit, "executed_experiment": False}


def status_command(repo, args):
    value = registry(repo)
    local = local_for(repo)
    cfg = config(repo)
    identifier = args.conversation or cfg.get("current_conversation")
    entry = conversation(repo, identifier) if identifier else None
    issues = []
    if not (repo / REGISTRY).exists():
        issues.append("No conversation registry exists")
    index = safe_relative(repo, "conversations/INDEX.md")
    if not index.exists() or index.read_text(encoding="utf-8") != index_text(value):
        issues.append("INDEX.md is absent or differs from registry; run index")
    for row in value["conversations"]:
        for name in ("README.md", "STATUS.md", "DECISIONS.md", "artifacts/.gitkeep"):
            if not safe_relative(repo, row["directory"] + "/" + name).is_file():
                issues.append(f"Missing conversation file: {row['directory']}/{name}")
        if row["kind"] == "main" and not safe_relative(repo, row["directory"] + "/branches/.gitkeep").is_file():
            issues.append(f"Missing main-conversation branch directory marker: {row['directory']}/branches/.gitkeep")
        relative = row["directory"] + "/actions.jsonl"
        action_file = safe_relative(local, relative)
        if ignored(local, relative):
            issues.append(f"Local action log is ignored: {relative}")
        if not action_file.is_file():
            issues.append(f"Missing local action log: {relative}")
        else:
            tracked = git(local, "ls-files", "-z", "--", relative).split("\x00")
            if relative not in tracked:
                issues.append(f"Local action log is not tracked: {relative}")
            try:
                content = action_file.read_text(encoding="utf-8")
                if not content.endswith("\n"):
                    raise ValueError("Missing final newline")
                for line in content.splitlines():
                    event = json.loads(line)
                    if event["conversation_id"] != row["id"]:
                        raise ValueError("Conversation mismatch")
            except (ValueError, KeyError):
                issues.append(f"Invalid local JSONL log: {relative}")
        runs_path = safe_relative(local, row["directory"] + "/runs")
        if runs_path.exists():
            for run_file in runs_path.rglob("*"):
                if run_file.is_file():
                    run_relative = run_file.relative_to(local).as_posix()
                    safe_relative(local, run_relative, must_exist=True)
                    if ignored(local, run_relative):
                        issues.append(f"Run evidence is ignored: {run_relative}")
                    elif run_relative not in git(local, "ls-files", "-z", "--", run_relative).split("\x00"):
                        issues.append(f"Run evidence is not tracked: {run_relative}")
    branch = git(repo, "symbolic-ref", "--quiet", "--short", "HEAD", ok=(0, 1))
    upstream = git(repo, "rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}", ok=(0, 128))
    sync = {"evidence": "cached local tracking refs only; no network verification", "upstream": upstream or None, "state": "no_upstream", "ahead": None, "behind": None}
    if upstream:
        ahead, behind = git(repo, "rev-list", "--left-right", "--count", "HEAD...@{upstream}").split()
        sync.update(ahead=int(ahead), behind=int(behind), state="equal_cached_refs" if ahead == behind == "0" else "different_cached_refs")
    local_status = git(local, "status", "--porcelain=v1", "--untracked-files=all")
    if local_status:
        issues.append("Local records repository contains uncommitted work")
    result = {"repo": str(repo), "branch": branch or None, "source_commit": git(repo, "rev-parse", "HEAD"), "bound_conversation": cfg.get("current_conversation"), "requested_conversation": identifier, "conversation": entry, "project_status": git(repo, "status", "--porcelain=v1", "--untracked-files=all"), "records_root": str(local), "local_commit": git(local, "rev-parse", "HEAD"), "local_status": local_status, "local_remotes": [], "sync": sync, "issues": issues, "ok": not issues}
    return result


def build_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1], help="Exact main project Git root; defaults to this script's repository")
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="Initialize or reuse the marked local-only records repository")
    init.add_argument("--records-root", required=True)
    reg = sub.add_parser("register", help="Register an explicitly identified main conversation or branch")
    reg.add_argument("--id", required=True)
    reg.add_argument("--slug", required=True)
    reg.add_argument("--title", required=True)
    reg.add_argument("--kind", choices=("main", "branch"), required=True)
    reg.add_argument("--parent")
    reg.add_argument("--background", required=True)
    reg.add_argument("--platform-id")
    bind = sub.add_parser("bind", help="Bind this worktree's local configuration to an existing conversation")
    bind.add_argument("--conversation", required=True)
    log = sub.add_parser("log", help="Append and locally commit one explicit observable action")
    log.add_argument("--conversation", required=True)
    log.add_argument("--task", required=True)
    log.add_argument("--action", required=True)
    log.add_argument("--result", required=True)
    log.add_argument("--file", action="append", default=[])
    log.add_argument("--failure")
    log.add_argument("--verification", action="append", default=[])
    log.add_argument("--artifact", action="append", default=[])
    checkpoint = sub.add_parser("checkpoint", help="Commit only explicitly reviewed text files on the current work branch")
    checkpoint.add_argument("--conversation", required=True)
    checkpoint.add_argument("--message", required=True)
    checkpoint.add_argument("--path", action="append", required=True)
    status = sub.add_parser("status", help="Check records, binding and cached Git synchronization state")
    status.add_argument("--conversation")
    run = sub.add_parser("record-run", help="Register supplied experiment evidence without running the experiment")
    run.add_argument("--conversation", required=True)
    run.add_argument("--manifest", required=True)
    sub.add_parser("index", help="Rebuild INDEX.md from the exact registry (does not rename directories)")
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        repo = root_at(args.repo)
        if args.command == "init":
            result = init_command(repo, args)
        elif args.command == "status":
            result = status_command(repo, args)
        else:
            local = local_for(repo)
            with lock(repo / ".um-records.lock"), lock(local / ".records.lock"):
                local_ready(local)
                if args.command == "register":
                    result = register_command(repo, args, local)
                elif args.command == "bind":
                    entry = conversation(repo, args.conversation)
                    value = config(repo)
                    value["current_conversation"] = entry["id"]
                    atomic_text(repo / CONFIG, json_text(value))
                    event = write_action(repo, local, entry, "Resume conversation", "bind", "bound", verification=["Exact registered ID selected; no Git branch switched"])
                    result = {"conversation": entry, "local_commit": commit_exact(local, [event], f"Bind conversation {entry['id']}")}
                elif args.command == "log":
                    entry = conversation(repo, args.conversation)
                    event = write_action(repo, local, entry, args.task, args.action, args.result, args.file, args.failure, args.verification, args.artifact)
                    result = {"log": str(local / event), "local_commit": commit_exact(local, [event], f"Log action for {entry['id']}")}
                elif args.command == "checkpoint":
                    result = checkpoint_command(repo, args, local)
                elif args.command == "record-run":
                    result = record_run_command(repo, args, local)
                else:
                    value = registry(repo)
                    atomic_text(safe_relative(repo, "conversations/INDEX.md"), index_text(value))
                    result = {"index": "conversations/INDEX.md", "entries": len(value["conversations"])}
        print(json_text(result), end="")
        return 1 if result.get("ok") is False else 0
    except (RecordError, OSError, ValueError) as exc:
        print(json_text({"ok": False, "error": redact_text(str(exc)), "recovery": "Inspect current Git and record files; no reset, clean, force-push or automatic deletion was performed."}), file=sys.stderr, end="")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
