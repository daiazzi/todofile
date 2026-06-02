from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path


NO_PROJECT = "(no project)"


@dataclass(slots=True)
class Task:
    hash: str
    tag: str | None
    description: str
    done: bool
    project: str
    parent_hash: str | None = None
    start: date | None = None
    end: date | None = None
    created: datetime | None = None
    completed: datetime | None = None


@dataclass(slots=True)
class Note:
    content: str
    hash: str | None = None


@dataclass(slots=True)
class Project:
    name: str
    tasks: list[Task] = field(default_factory=list)
    notes: list[Note] = field(default_factory=list)


@dataclass(slots=True)
class ParsedDocument:
    path: Path | None
    projects: list[Project] = field(default_factory=list)
    tasks_by_hash: dict[str, Task] = field(default_factory=dict)
    children: dict[str, list[Task]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    title: str | None = None

    def children_of(self, parent_hash: str) -> list[Task]:
        return self.children.get(parent_hash, [])

    def all_tasks(self) -> list[Task]:
        return list(self.tasks_by_hash.values())


@dataclass(slots=True)
class TaskMetadata:
    hash: str
    start: date | None = None
    end: date | None = None
    created: datetime | None = None
    completed: datetime | None = None
    extra: dict = field(default_factory=dict)


@dataclass(slots=True)
class Config:
    port: int | None = None
    colors: dict[str, str] = field(default_factory=dict)
    theme: str = "light"
    default_duration: int = 0
    show_dates: bool = False
    show_gantt: bool = False
    show_calendar: bool = False
    show_weekends: bool = False
    text_size: str = "big"
    auto_refresh: bool = True
    extra: dict = field(default_factory=dict)
