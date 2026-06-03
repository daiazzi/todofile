# tsk

Local-first task manager for dev/data projects. Your `TODO.md` stays the
single human-edited, gittable source of truth; the manager adds dates and a
Gantt/Calendar view backed by a sidecar YAML file.

```bash
$ touch TODO.md
$ tsk init
$ tsk up
tsk: serving path/to/TODO.md
tsk: open http://127.0.0.1:42117

$ tsk down
tsk: stopped daemon (pid 12345)
```

The web UI opens in your default browser (or paste the URL into the VS Code
Simple Browser). `tsk down` stops the server. 

Run `tsk serve` to start the server in foreground. `Ctrl-C` stops the server.

Use `--file`/`-f` to specify a different TODO file.

`todofile` is an alias for `tsk`.

## What it does

- Parses your `TODO.md` and shows tasks in a list + a Gantt timeline +
  a month calendar.
- Lets you click-and-set start/end dates inline. Dates persist to
  `./<dir-of-todo>/.<filename>.dir/tasks.yaml` — your `TODO.md` is **not**
  rewritten for dates.
- Stamps a stable 5-char hash into each task on first sight, so dates
  survive edits to the task text.
- Filters by project (multi-select chips).
- Toggles between Gantt and Calendar views.
- Light/dark theme toggle.
- Per-tag colours from `config.yaml`.

The markdown is the source of truth for: which tasks exist, hierarchy,
project, tag, description, done state. The yaml owns dates and timestamps.

## TODO.md format

```markdown
# Project title              <-- shown in the UI header

## backend                   <-- starts a project

### Notes                    <-- optional ideas/decisions for this project
- Chose PostgreSQL for persistence.
- Open question: caching layer?

- [ ] api(a4f9c): Build the parser
  Continued description on indented lines.
  - A bullet inside the description (no checkbox).
  - [ ] (b3d8a): A subtask
- [x] (c1d2e): Completed

## frontend
- [ ] ui: Design the layout      <-- unstamped; gets a hash on next run
```

- H1 (`#`) is the document title — shown in the UI header.
- H2 (`##`) headings are projects. Tasks belong to the most recent one.
- `### Notes` under a project holds project notes: plain `-` or `*` bullets
  (not checkboxes). Each bullet starts a note; everything until the next bullet
  at the same indent is markdown shown in a collapsible panel in the UI.
- A task is `- [ ]` (or `- [x]`, `*`, mixed) followed by an optional `tag`,
  `(hash)`, `:`, then the description.
- The hash is mandatory in the canonical form; unstamped tasks are accepted
  and stamped on the next `tsk` or `tsk init` run.
- Tag is an optional free-form category.
- Subtasks are indented deeper than their parent. Max 2 levels.
- Continuation lines (non-checkbox content under a task) become part of its
  description.

Full grammar: `tsk help format`.

## Install

```bash
# clone, then in the repo:
pixi install
pixi run tsk --help
```

The CLI is exposed as `tsk` inside the pixi environment.

## CLI

`<path>` is optional on every command. When omitted, `tsk` looks in the
current directory for an initialized `.<name>.dir/` sidecar; if exactly one
exists it is used. Otherwise it falls back to `./TODO.md`, then errors.

| Command | What it does |
|---|---|
| `tsk [path]` | Auto-init, start the web UI in foreground, open the browser. Ctrl-C to stop. |
| `tsk up [path]` | Start the server detached (background). Writes pid/url into the sidecar. |
| `tsk down [path]` | Stop the daemon for that TODO. |
| `tsk init [path]` | Create the sidecar dir, copy `agent.md`, stamp hashes. Creates the file if missing (parent dir must exist). Defaults to `./TODO.md`. |
| `tsk add [path] -d "<desc>" [-t tag] [-p parent_hash] [-P project] [-s YYYY-MM-DD] [-e YYYY-MM-DD] [--duration N]` | Add a task to the markdown. |
| `tsk remove <hash> [path]` | Remove a task (and its subtasks). |
| `tsk config [flags]` | Set per-project preferences in `config.yaml`. See below. |
| `tsk help format` | Print the TODO.md format spec. |

Date flags for `add`: pass at most two of `--start-date`, `--end-date`,
`--duration` (days, inclusive). The third is derived.

### `tsk config` flags

All flags can be combined in one call. Resolves the TODO file from cwd.

| Flag | Effect |
|---|---|
| `--dark-mode` / `--light-mode` | Set the UI theme. |
| `--tag-col TAG:color` | Set a tag's colour. Repeatable; or pass `TAG1:c1,TAG2:c2` to set several in one flag. `color` accepts a palette name (`red`, `green`, `blue`, …) or a `#rrggbb` hex. |
| `--show-gantt` / `--no-show-gantt` | Default visibility of the Gantt column in the UI. |
| `--show-calendar` / `--no-show-calendar` | Default visibility of the Calendar column in the UI. |
| `--show-weekends` / `--no-show-weekends` | Default visibility of the weekends in the Gantt column in the UI. |
| `--show-dates` / `--no-show-dates` | Default visibility of the start/end columns in the UI. |
| `--default-duration <N>` | Length (days) of the auto-set start/end on new tasks; `0` disables automatic dates. |
| `--text-size <small\|medium\|big>` | UI text size. |
| `--list-colors` | Print the colour palette with swatches and exit. |

Examples:
```bash
tsk config --dark-mode
tsk config --tag-col FEAT:blue --tag-col FIX:red
tsk config --no-show-dates --text-size big --default-duration 5 --show-gantt --show-calendar --show-weekends
tsk config --list-colors
```

Editing `config.yaml` through `tsk config` rewrites the file via YAML
serialisation, which drops any comments. Edit the file by hand to keep
them.

## Sidecar files

For `/path/to/myTODO.md` the manager uses:

```bash
/path/to/.myTODO.md.dir/
    tasks.yaml      # dates + timestamps, one row per hash
    config.yaml     # port, theme, tag colours
    agent.md        # instructions for coding assistants editing TODO.md
    daemon.pid      # only while detached (written by `tsk up`)
    daemon.url
    daemon.log
    .gitignore     # contains daemon.pid, daemon.url, daemon.log
```

`config.yaml` shape:

```yaml
port: 47209
theme: light
text_size: big
show_dates: false
show_gantt: false
show_calendar: false
show_weekends: false
auto_refresh: true
default_duration: 0
colors:
  default: '#8c8c8c'
  FIX: '#ff0000'
  FEAT: '#0080ff'
  REFACTOR: '#ffbf00'
  PERF: '#ff33ff'
  TESTS: '#269900'
  DOCS: '#663300'
  ENV: '#999900'
  MISC: '#339999'
  DEADLINE: '#ffff00'
```

Add `*/.*.dir/` to your `.gitignore` if you don't want to commit the
metadata, or commit it if you do — both are valid workflows.

## Agents

`tsk init` drops a `agent.md` into the sidecar. Point your coding assistant
at it (the file documents the TODO.md format, what edits are safe, and
recommends `tsk add/remove` for non-trivial changes).

## Development

This project uses [pixi](https://pixi.sh) for environment and dependency
management. Do not call `pip` or `conda` directly.

```bash
# add a runtime dependency from PyPI
pixi add --pypi <pkg>

# add a dev-only dependency
pixi add --feature dev <pkg>

# run tests
pixi run pytest

# run the CLI in development
pixi run tsk <path/to/TODO.md>

# enter the env interactively
pixi shell
```

The package layout:

```
src/todofile/
    models.py          # dataclasses
    parser.py          # TODO.md → ParsedDocument
    writer.py          # mutate TODO.md (stamp, add, remove)
    store.py           # tasks.yaml + config.yaml + agent.md
    daemon.py          # detached server lifecycle (tsk up/down)
    cli.py             # rich-click commands
    server.py          # Starlette app
    static/            # HTML + CSS + JS + agent.md template
tests/                 # pytest suite
docs/                  # requirements, technical design, specifications, tasks
```

Read [docs/requirements.md](docs/requirements.md) before contributing.

## Status

v1 — single TODO file per server invocation, no archive, no live file
watching. See [docs/requirements.md §11](docs/requirements.md) for deferred
nice-to-haves.
