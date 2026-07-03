# todofile

## Tasks

- [x] DOC(1bdcf): update README.md with the changes in version 0.3.0
- [x] FIX(2416f): installation problem due to duplicate `tool.hatch.build.targets.wheel` entry
- [x] FEAT(db33c): create CLI alias `todofile` for `tsk`.
- [x] REFACTOR(8d193): calling tsk or todofile without arguments should return the help message.
- [ ] FEAT(9c74a): add `tsk reset-ids` command to reset the ids of all tasks.
- [ ] FEAT(aae8b): New type of task `deadline` that has only one date and a different representation on the gantt
- [ ] FEAT(8875a): description, date, or subtitle for projects
  This requires some thought because it is not clear how to code it into the md and how to render it in the UI.
  Can be just text after the title that is not marked as a task.
- [ ] FIX: task panel size should be adjustable also when other columns are hidden.
- [ ] REFACTOR(6d662): Replace httpx with niquests.

### Notes
