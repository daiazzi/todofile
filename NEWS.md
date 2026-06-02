# todofile

## Unreleased

- refactor!: change `tsk init` defaults to light theme, big text, no date columns, and no automatic task dates (`default_duration: 0`).
- refactor!(CLI): `path` is now a `--file`/`-f` option on all commands instead of a positional argument.
- feat(CLI): `tsk init` writes a `.gitignore` in the sidecar directory to exclude `daemon.pid`, `daemon.url`, and `daemon.log`.
- feat(UI): browser tab title now shows `todofile - <project title>` using the H1 from the TODO file.
- refactor!(CLI): remove deprecated `tsk task add` / `tsk task remove` commands.
- refactor!(CLI): make option description and argument in cli tsk add
- feat: support 3 levels of nested tasks (root → subtask → sub-subtask); deeper bullets in the markdown are flattened with a warning.

## 0.2.0 (2026-05-29)

- refactor!: rename package to `todofile`.
- feat: add auto-refresh on TODO edits.
- refactor!(CLI): make add and remove task first class commands.
  Use `tsk add/remove` instead of `tsk task add/remove`.
- feat: add annotate command to add a note.
- feat: add hash to notes so that they can be removed with the `tsk remove` command.
- feat: Make the pop up window's content (task) editable.
- feat: Make notes clickable with popup window like tasks.
- feat: Default tags DOCS, ENV, REFACTOR, FEAT, FIX, PERF, TESTS.
- feat(CLI): add `tsk restart` command (down + up).
- feat(UI): allow `Esc` to close task/note popup.
- fix: ensure blank line after markdown headings on write.
- feat(CLI): `tsk init` accepts `tsk config` flags.
- feat(UI): align horizontally tasks in task panel with gantt visualisation.
- feat(UI): make gantt/calendar panel toggle on/off and add tsk config --show-calendar/--no-show-calendar option.
- feat(CLI): allow default duration to be 0 - that means that there is not default dates.
- feat: allow 0 duration tasks (no automatic dates).

## 0.1.0 (2026-05-28)

- Initial release.
