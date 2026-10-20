"""Persistent storage for the two operator-selected navigation goals."""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import tempfile
from typing import Any


@dataclass(frozen=True)
class StoredGoal:
    x: float
    y: float
    yaw: float

    def as_dict(self) -> dict[str, float]:
        return {"x": self.x, "y": self.y, "yaw": self.yaw}


def default_goal_file() -> str:
    """Keep runtime data inside this workspace when launched from its root."""
    return str(Path.cwd() / "runtime" / "decision_goals.json")


def _goal_from_value(value: Any, name: str) -> StoredGoal:
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be an object with x, y and yaw")
    try:
        goal = StoredGoal(float(value["x"]), float(value["y"]), float(value["yaw"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain numeric x, y and yaw") from exc
    if not all(math.isfinite(v) for v in (goal.x, goal.y, goal.yaw)):
        raise ValueError(f"{name} contains a non-finite value")
    return goal


def load_goal_history(path: str) -> tuple[StoredGoal | None, StoredGoal | None]:
    """Load up to two recorded goals, allowing an incomplete first run."""
    file_path = Path(path).expanduser()
    try:
        with file_path.open(encoding="utf-8") as stream:
            data = json.load(stream)
    except FileNotFoundError as exc:
        raise ValueError(f"goal file does not exist: {file_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"goal file is not valid JSON: {file_path}") from exc
    if not isinstance(data, dict):
        raise ValueError("goal file root must be an object")
    frame_id = data.get("frame_id", "map")
    if frame_id != "map":
        raise ValueError(f"goal file frame_id must be 'map', got {frame_id!r}")
    one = data.get("point_one")
    two = data.get("point_two")
    if one is None and two is not None:
        raise ValueError("point_two cannot be set while point_one is empty")
    return (
        _goal_from_value(one, "point_one") if one is not None else None,
        _goal_from_value(two, "point_two") if two is not None else None,
    )


def load_goals(path: str) -> tuple[StoredGoal, StoredGoal]:
    """Load and validate both goals required for decision mode."""
    one, two = load_goal_history(path)
    if one is None or two is None:
        raise ValueError("goal file must contain both point_one and point_two")
    return one, two


def append_latest(
    history: list[StoredGoal | None], goal: StoredGoal
) -> tuple[list[StoredGoal | None], str]:
    """Append a goal while retaining only the latest two in chronological order."""
    if len(history) != 2:
        raise ValueError("exactly two goal slots are required")
    if history[0] is None:
        return [goal, history[1]], "point_one"
    if history[1] is None:
        return [history[0], goal], "point_two"
    return [history[1], goal], "point_two (oldest point moved to point_one)"


def save_goals(path: str, goals: list[StoredGoal | None]) -> None:
    """Atomically save the current one- or two-goal history."""
    if len(goals) != 2:
        raise ValueError("exactly two goal slots are required")
    file_path = Path(path).expanduser()
    file_path.parent.mkdir(parents=True, exist_ok=True)
    data: dict[str, Any] = {"version": 1, "frame_id": "map"}
    for name, goal in zip(("point_one", "point_two"), goals):
        data[name] = goal.as_dict() if goal is not None else None

    fd, temp_name = tempfile.mkstemp(prefix=f".{file_path.name}.", dir=file_path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, file_path)
    except Exception:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise
