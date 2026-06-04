from __future__ import annotations

import asyncio
import os
from typing import Optional

from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import (
    Button,
    DirectoryTree,
    Footer,
    Header,
    Markdown,
    Static,
)
from textual.binding import Binding
from rich.syntax import Syntax

from crit_orchestrator import (
    run_pipeline_on_elements,
    parse_ast_elements,
    CritConfig,
    ASTParsingError,
)

class CodeInspector(Static):
    """A widget to display code with syntax highlighting."""
    
    def update_code(self, code: str, filename: str) -> None:
        syntax = Syntax(code, "python", theme="monokai", line_numbers=True)
        self.update(syntax)

class CritTUI(App):
    """A Terminal User Interface for CRIT."""

    CSS = """
    Screen {
        background: $surface;
    }

    #left-pane {
        width: 30;
        height: 100%;
        border-right: tall $primary;
    }

    #middle-pane {
        width: 2fr;
        height: 100%;
        border-right: tall $primary;
        padding: 1;
    }

    #right-pane {
        width: 3fr;
        height: 100%;
        padding: 1;
    }

    DirectoryTree {
        height: 1fr;
    }

    #run-btn {
        width: 100%;
        margin-top: 1;
    }

    Markdown {
        background: $surface;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True),
        Binding("r", "run_audit", "Run Audit", show=True),
    ]

    def __init__(self):
        super().__init__()
        self.selected_file: Optional[str] = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Horizontal():
            with Vertical(id="left-pane"):
                yield DirectoryTree(".")
                yield Button("Run Audit", variant="primary", id="run-btn")
            with Vertical(id="middle-pane"):
                yield Markdown("# CRIT Audit Results\nSelect a file and press 'Run Audit'")
            with Vertical(id="right-pane"):
                yield CodeInspector(id="code-view")
        yield Footer()

    def on_directory_tree_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        """Handle file selection in the tree."""
        self.selected_file = str(event.path)
        if self.selected_file.endswith(".py"):
            try:
                with open(self.selected_file, "r", encoding="utf-8") as f:
                    content = f.read()
                self.query_one("#code-view", CodeInspector).update_code(content, self.selected_file)
            except Exception as e:
                self.notify(f"Error reading file: {e}", severity="error")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "run-btn":
            self.action_run_audit()

    @work(thread=True)
    async def action_run_audit(self) -> None:
        """Run the audit pipeline in a background thread."""
        if not self.selected_file or not self.selected_file.endswith(".py"):
            self.notify("Please select a valid .py file first.", severity="warning")
            return

        self.notify(f"🚀 Starting audit for {os.path.basename(self.selected_file)}...")
        
        md_view = self.query_one(Markdown)
        md_view.update("# ⏳ Auditing...\nPlease wait for the Map-Reduce pipeline.")

        try:
            with open(self.selected_file, "r", encoding="utf-8") as f:
                source_code = f.read()

            config = CritConfig.load_from_file()
            elements = parse_ast_elements(source_code, self.selected_file)
            
            # Since we are in a thread, we might need a local event loop or use asyncio correctly
            # Textual's @work(thread=True) handles the thread, but the pipeline is async
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            verdict, analyses = loop.run_until_complete(
                run_pipeline_on_elements(elements, self.selected_file, config)
            )
            loop.close()

            # Format results as Markdown
            report = f"# Audit Results: {verdict.grade} ({verdict.overall_score:.1f}/10)\n\n"
            report += f"**Recommendation:** {verdict.recommendation}\n\n"
            
            report += "## Strengths\n"
            for s in verdict.top_strengths:
                report += f"- {s}\n"
                
            report += "\n## Weaknesses\n"
            for w in verdict.top_weaknesses:
                report += f"- {w}\n"
                
            report += "\n## Detailed Findings\n"
            for a in analyses:
                report += f"### `{a.element_name}` ({a.element_type})\n"
                report += f"{a.summary}\n\n"
                
                # Render Validated SAST Findings
                tp_findings = [f for f in a.validated_sast_findings if f.is_true_positive]
                if tp_findings:
                    report += "#### 🛡️ [SAST+AI] Confirmed Vulnerabilities\n"
                    for f in tp_findings:
                        report += f"- **{f.rule_id}**: {f.message} (Line {f.line})\n"
                        report += f"  - *Validation:* {f.validation_rationale}\n"
                    report += "\n"

                for s in a.scores:
                    report += f"- **{s.criterion}**: {s.score} ({s.severity.value}) - {s.rationale}\n"
                report += "\n"

            md_view.update(report)
            self.notify("✅ Audit complete!", severity="information")

        except ASTParsingError as e:
            md_view.update(f"# ❌ AST Error\n{e.message}\nLine: {e.line}")
            self.notify("AST Parsing Failed", severity="error")
        except Exception as e:
            md_view.update(f"# ❌ Error\n{str(e)}")
            self.notify(f"Pipeline Failed: {e}", severity="error")

if __name__ == "__main__":
    app = CritTUI()
    app.run()
