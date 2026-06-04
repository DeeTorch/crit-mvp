# CRIT TUI Integration Plan

This implementation plan details the strategy to integrate a rich Terminal User Interface (TUI) using the `textual` framework into the CRIT Protocol Orchestrator.

## User Review Required

> [!IMPORTANT]
> The TUI will be implemented in a dedicated file [tui.py](file:///C:/Users/Golde/Documents/antigravity/modest-goodall/tui.py) to keep UI layout and styling decoupled from core business logic:
> 1. **Layout**: Uses a Horizontal layout split into 3 vertical panels:
>    - **Left Column**: A `DirectoryTree` widget to browse files and a "Run Audit" button.
>    - **Middle Column**: A scrollable `Markdown` widget to render the audit summary, score, grade, and structured findings.
>    - **Right Column**: A custom `CodeInspector` widget using `rich.syntax.Syntax` to display the selected Python file's source code with full syntax highlighting.
> 2. **Async Integration**: Implements Textual's background thread worker model (`@work(thread=True)`) to trigger the Map-Reduce pipeline when the button is pressed. This ensures the UI remains fully responsive and does not freeze during API calls.
> 3. **CLI Hook**: Integrates a `--gui` flag into `crit_orchestrator.py` which silences stdout logging and invokes `CritTUI().run()`.

## Proposed Changes

### TUI Layout & Integration

---

#### [NEW] [tui.py](file:///C:/Users/Golde/Documents/antigravity/modest-goodall/tui.py)
* Create the `CritTUI` app class.
* Implement layout components, directory tree selection logic, file syntax highlighters, and background worker logic.

#### [MODIFY] [crit_orchestrator.py](file:///C:/Users/Golde/Documents/antigravity/modest-goodall/crit_orchestrator.py)
* Add a `--gui` CLI flag.
* If `--gui` is set, suppress normal console logging and launch `CritTUI().run()`.

#### [MODIFY] [requirements.txt](file:///C:/Users/Golde/Documents/antigravity/modest-goodall/requirements.txt)
* Add `textual` as a required dependency.

#### [MODIFY] [pyproject.toml](file:///C:/Users/Golde/Documents/antigravity/modest-goodall/pyproject.toml)
* Add `textual` to the project's dependencies.

---

## Verification Plan

### Automated & Manual Testing
- Add `textual` to requirements and verify dependencies install correctly.
- Run `crit-audit --gui` or `python crit_orchestrator.py --gui`.
- Select `valid_test.py` from the browser, verify that it highlights correctly in the Code Inspector, and run the audit. Verify results render beautifully in markdown format in the middle panel.
