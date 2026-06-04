"""
CRIT Protocol Orchestrator
===========================
A Map-Reduce pipeline for code analysis using Gemini 2.5 Pro.

Architecture:
  1. AST Parsing   — Extracts structural elements from a code sample.
  2. Map Phase     — Each element is independently scored for quality criteria.
  3. Reduce Phase  — Scores are aggregated into a final verdict.

All LLM calls go through google-genai wrapped with instructor for
structured Pydantic output validation.
"""

from __future__ import annotations

import ast
import asyncio
import logging
import os
import sys
import textwrap
from enum import Enum
from typing import Optional

import nest_asyncio
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# ── Environment ──────────────────────────────────────────────────────────────

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY or GEMINI_API_KEY == "your_api_key_here":
    print(
        "⚠️  GEMINI_API_KEY is not set or still contains the placeholder.\n"
        "    Please update .env with a valid key before running this script."
    )
    sys.exit(1)

# ── Constants ────────────────────────────────────────────────────────────────

TARGET_MODEL = "gemini-2.5-pro"

# ── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("crit")

# ── Pydantic Schemas ─────────────────────────────────────────────────────────


class Severity(str, Enum):
    """Quality severity level for a single criterion."""

    EXCELLENT = "excellent"
    GOOD = "good"
    FAIR = "fair"
    POOR = "poor"
    CRITICAL = "critical"


class CriterionScore(BaseModel):
    """Score for one quality criterion on one code element."""

    criterion: str = Field(description="Name of the quality criterion evaluated")
    severity: Severity = Field(description="Severity level of the finding")
    score: float = Field(ge=0.0, le=10.0, description="Numeric score 0-10")
    rationale: str = Field(description="Brief rationale for the assigned score")


class ElementAnalysis(BaseModel):
    """Map-phase result: analysis of a single AST element."""

    element_name: str = Field(description="Name of the code element analyzed")
    element_type: str = Field(description="Type of element (function, class, etc.)")
    scores: list[CriterionScore] = Field(
        description="Quality scores across all criteria"
    )
    summary: str = Field(description="One-sentence summary of this element's quality")


class FinalVerdict(BaseModel):
    """Reduce-phase result: aggregated verdict across all elements."""

    overall_score: float = Field(
        ge=0.0, le=10.0, description="Aggregate quality score"
    )
    grade: str = Field(description="Letter grade (A-F)")
    top_strengths: list[str] = Field(description="Top strengths identified")
    top_weaknesses: list[str] = Field(description="Top weaknesses identified")
    recommendation: str = Field(
        description="Actionable recommendation for improvement"
    )
    element_count: int = Field(description="Number of elements analyzed")


# ── AST Parsing Phase ────────────────────────────────────────────────────────

SAMPLE_CODE = textwrap.dedent('''\
    """Module: user_service — Manages user CRUD operations."""

    from dataclasses import dataclass, field
    from typing import Optional
    import hashlib


    @dataclass
    class User:
        """Represents a registered user."""
        user_id: int
        username: str
        email: str
        password_hash: str = field(repr=False)
        is_active: bool = True

        def verify_password(self, raw_password: str) -> bool:
            """Check a plaintext password against the stored hash."""
            return self.password_hash == hashlib.sha256(
                raw_password.encode()
            ).hexdigest()


    class UserService:
        """In-memory user store with basic CRUD."""

        def __init__(self) -> None:
            self._users: dict[int, User] = {}
            self._next_id: int = 1

        def create_user(
            self,
            username: str,
            email: str,
            password: str,
        ) -> User:
            """Create a new user and return it."""
            pw_hash = hashlib.sha256(password.encode()).hexdigest()
            user = User(
                user_id=self._next_id,
                username=username,
                email=email,
                password_hash=pw_hash,
            )
            self._users[self._next_id] = user
            self._next_id += 1
            return user

        def get_user(self, user_id: int) -> Optional[User]:
            """Retrieve a user by ID, or None if not found."""
            return self._users.get(user_id)

        def delete_user(self, user_id: int) -> bool:
            """Delete a user by ID. Returns True if deleted."""
            if user_id in self._users:
                del self._users[user_id]
                return True
            return False
''')

QUALITY_CRITERIA = [
    "Readability & Naming",
    "Error Handling & Robustness",
    "Security Practices",
    "Performance & Efficiency",
    "Documentation & Typing",
]


def parse_ast_elements(source: str) -> list[dict]:
    """Parse Python source code and extract structural elements."""
    log.info("🌳 AST Parsing Phase — parsing source code")
    tree = ast.parse(source)

    elements: list[dict] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            methods = [
                n.name
                for n in ast.walk(node)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
            elements.append(
                {
                    "name": node.name,
                    "type": "class",
                    "line": node.lineno,
                    "methods": methods,
                    "source": ast.get_source_segment(source, node) or "",
                }
            )
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Skip methods already captured inside classes
            if any(
                node.name in el.get("methods", [])
                for el in elements
                if el["type"] == "class"
            ):
                continue
            elements.append(
                {
                    "name": node.name,
                    "type": "function",
                    "line": node.lineno,
                    "methods": [],
                    "source": ast.get_source_segment(source, node) or "",
                }
            )

    log.info(
        "   Found %d top-level element(s): %s",
        len(elements),
        ", ".join(f'{e["type"]}:{e["name"]}' for e in elements),
    )
    return elements


# ── LLM Client Setup ────────────────────────────────────────────────────────


def _build_client():
    """Build the instructor-wrapped async Gemini client."""
    import google.genai as genai
    import instructor

    raw_client = genai.Client(api_key=GEMINI_API_KEY)
    wrapped = instructor.from_genai(
        client=raw_client,
        mode=instructor.Mode.GENAI_STRUCTURED_OUTPUTS,
        use_async=True,
    )
    log.info("🔗 Instructor client initialized (model=%s, mode=GENAI_STRUCTURED_OUTPUTS)", TARGET_MODEL)
    return wrapped


# ── Map Phase ────────────────────────────────────────────────────────────────


async def map_analyze_element(
    client, element: dict, criteria: list[str]
) -> ElementAnalysis:
    """Score a single code element against all quality criteria."""
    log.info("   📐 Mapping element: %s (%s)", element["name"], element["type"])

    prompt = textwrap.dedent(f"""\
        You are a senior code reviewer. Analyze the following Python code element
        and score it on each criterion from 0 (terrible) to 10 (perfect).

        ## Element
        - Name: {element['name']}
        - Type: {element['type']}

        ```python
        {element['source']}
        ```

        ## Criteria to evaluate
        {', '.join(criteria)}

        Return a structured analysis with scores for EACH criterion listed above.
    """)

    result: ElementAnalysis = await client.chat.completions.create(
        model=TARGET_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_model=ElementAnalysis,
    )
    log.info(
        "   ✅ %s scored — avg %.1f/10",
        result.element_name,
        sum(s.score for s in result.scores) / max(len(result.scores), 1),
    )
    return result


async def map_phase(client, elements: list[dict]) -> list[ElementAnalysis]:
    """Run Map phase: analyze all elements concurrently."""
    log.info("🗺️  Map Phase — launching %d concurrent analyses", len(elements))
    tasks = [
        map_analyze_element(client, el, QUALITY_CRITERIA) for el in elements
    ]
    results = await asyncio.gather(*tasks)
    log.info("🗺️  Map Phase complete — %d elements analyzed", len(results))
    return list(results)


# ── Reduce Phase ─────────────────────────────────────────────────────────────


async def reduce_phase(
    client, analyses: list[ElementAnalysis]
) -> FinalVerdict:
    """Run Reduce phase: aggregate element analyses into a final verdict."""
    log.info("📊 Reduce Phase — aggregating %d element analyses", len(analyses))

    # Build a summary table for the LLM
    summary_lines: list[str] = []
    for a in analyses:
        scores_str = ", ".join(
            f"{s.criterion}: {s.score}/{s.severity.value}" for s in a.scores
        )
        summary_lines.append(f"- **{a.element_name}** ({a.element_type}): {scores_str}")

    prompt = textwrap.dedent(f"""\
        You are a senior engineering lead. Given the per-element quality analyses
        below, produce a final aggregate verdict for the entire codebase.

        ## Element Analyses
        {chr(10).join(summary_lines)}

        Provide:
        1. An overall numeric score (0-10).
        2. A letter grade (A-F).
        3. Top strengths and weaknesses.
        4. A single actionable recommendation.
        5. The total element count.
    """)

    verdict: FinalVerdict = await client.chat.completions.create(
        model=TARGET_MODEL,
        messages=[{"role": "user", "content": prompt}],
        response_model=FinalVerdict,
    )
    log.info(
        "📊 Reduce Phase complete — overall score: %.1f/10, grade: %s",
        verdict.overall_score,
        verdict.grade,
    )
    return verdict


# ── Main Pipeline ────────────────────────────────────────────────────────────


async def run_pipeline() -> FinalVerdict:
    """Execute the full CRIT pipeline: Parse → Map → Reduce."""
    log.info("=" * 60)
    log.info("🚀 CRIT Protocol Orchestrator — Starting Pipeline")
    log.info("   Model:  %s", TARGET_MODEL)
    log.info("=" * 60)

    # Phase 1 — AST Parsing
    elements = parse_ast_elements(SAMPLE_CODE)

    # Phase 2 — Build client
    client = _build_client()

    # Phase 3 — Map
    analyses = await map_phase(client, elements)

    # Phase 4 — Reduce
    verdict = await reduce_phase(client, analyses)

    # ── Report ───────────────────────────────────────────────────────────
    log.info("=" * 60)
    log.info("🏁 CRIT Final Report")
    log.info("=" * 60)
    log.info("   Overall Score : %.1f / 10", verdict.overall_score)
    log.info("   Grade         : %s", verdict.grade)
    log.info("   Elements      : %d", verdict.element_count)
    log.info("   Strengths     :")
    for s in verdict.top_strengths:
        log.info("     • %s", s)
    log.info("   Weaknesses    :")
    for w in verdict.top_weaknesses:
        log.info("     • %s", w)
    log.info("   Recommendation: %s", verdict.recommendation)
    log.info("=" * 60)

    return verdict


def main():
    """Entry point — apply nest_asyncio and run the pipeline."""
    nest_asyncio.apply()
    verdict = asyncio.run(run_pipeline())
    # Final Pydantic validation proof
    log.info("✅ Pydantic validation passed — verdict model dump:")
    for k, v in verdict.model_dump().items():
        log.info("   %s: %s", k, v)


if __name__ == "__main__":
    main()
