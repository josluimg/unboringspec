"""Where the previous version of a spec comes from.

- Snapshots (default): every render stores the analysed spec in .unboring/<feature>/history/,
  one snapshot per distinct version of the documents. Re-rendering an unchanged spec keeps
  comparing against the version before it, not against itself.
- Git (--since <ref>): the spec folder as it was at that commit. If a snapshot of that exact
  version exists, its analysis (including the agent's) is used; otherwise it is analysed offline.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from .adapters import get_adapter
from .insights import heuristic_insights
from .ir import SpecIR

KEEP = 20  # snapshots per feature


class BaselineError(RuntimeError):
    pass


def documents_hash(documents: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(documents, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def _when(name: str) -> str:
    try:
        return datetime.strptime(name.split("-")[0], "%Y%m%dT%H%M%S%f").strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return name


class History:
    def __init__(self, workdir: Path):
        self.dir = workdir / "history"

    def snapshots(self) -> list[Path]:
        return sorted(p for p in self.dir.glob("*") if (p / "ir.json").is_file()) if self.dir.is_dir() else []

    @staticmethod
    def load(snapshot: Path) -> SpecIR:
        return SpecIR.model_validate_json((snapshot / "ir.json").read_text(encoding="utf-8"))

    @staticmethod
    def _write(snapshot: Path, ir: SpecIR) -> None:
        snapshot.mkdir(parents=True, exist_ok=True)
        data = ir.model_dump(mode="json", exclude={"changes", "follow_up"})
        (snapshot / "ir.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def find(self, doc_hash: str) -> Path | None:
        return next((s for s in reversed(self.snapshots()) if s.name.endswith(doc_hash)), None)

    def record(self, ir: SpecIR) -> tuple[SpecIR, str] | None:
        """Store this version and return (previous version, label), or None on the first render."""
        doc_hash = documents_hash(ir.documents)
        snaps = self.snapshots()
        if snaps and snaps[-1].name.endswith(doc_hash):
            # Same documents as last time: refresh the analysis, compare with the version before.
            self._write(snaps[-1], ir)
            previous = snaps[-2] if len(snaps) > 1 else None
        else:
            previous = snaps[-1] if snaps else None
            # Microseconds keep the order right even for two renders within one second.
            self._write(self.dir / f"{datetime.now():%Y%m%dT%H%M%S%f}-{doc_hash}", ir)
        for old in self.snapshots()[:-KEEP]:
            shutil.rmtree(old, ignore_errors=True)
        if previous is None:
            return None
        return self.load(previous), f"the previous version (rendered {_when(previous.name)})"


def _git(args: list[str], cwd: Path) -> str:
    try:
        out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
    except FileNotFoundError as e:
        raise BaselineError("git is not installed; drop --since to compare with the previous render.") from e
    except subprocess.CalledProcessError as e:
        raise BaselineError(e.stderr.strip() or f"git {' '.join(args)} failed") from e
    return out.stdout


def git_baseline(spec: Path, ref: str, history: History, adapter: str | None = None) -> tuple[SpecIR, str]:
    """The spec folder as it was at `ref`, analysed (from a matching snapshot when there is one)."""
    spec = spec.resolve()
    root = Path(_git(["rev-parse", "--show-toplevel"], spec).strip())
    rel = spec.relative_to(root)
    short = _git(["rev-parse", "--short", f"{ref}^{{commit}}"], root).strip()
    files = [f for f in _git(["ls-tree", "-r", "--name-only", ref, "--", rel.as_posix()], root).splitlines() if f]
    if not files:
        raise BaselineError(f"{rel} does not exist at {ref}.")
    with tempfile.TemporaryDirectory(prefix="unboring-since-") as tmp:
        for f in files:
            target = Path(tmp) / f
            target.parent.mkdir(parents=True, exist_ok=True)
            blob = subprocess.run(["git", "show", f"{ref}:{f}"], cwd=root, capture_output=True, check=True).stdout
            target.write_bytes(blob)
        folder = Path(tmp) / rel  # same relative path, so adapters detect it the same way
        ir = get_adapter(folder, adapter).load(folder)
    label = f"{ref} ({short})"
    snapshot = history.find(documents_hash(ir.documents))
    if snapshot is not None:
        return history.load(snapshot), label
    return heuristic_insights(ir), label
