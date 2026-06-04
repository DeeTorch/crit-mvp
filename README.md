# CRIT: Code Review & Intelligence Tool (MVP)

CRIT is an enterprise-ready AI-powered code auditing tool that leverages a **Map-Reduce AST parsing pipeline** and **Gemini 2.5 Pro** to provide high-fidelity, structured feedback on Python codebases.

---

## 🚀 Overview

CRIT goes beyond simple pattern matching. It uses a multi-stage pipeline to analyze code:

1.  **AST Parsing Phase**: CRIT parses the target file into an Abstract Syntax Tree (AST) to identify logical elements (classes and functions).
2.  **Map Phase**: Each identified element is isolated and analyzed independently by Gemini. This ensures high-resolution analysis without context dilution.
3.  **Reduce Phase**: A separate LLM call aggregates individual element scores into a cohesive **Final Verdict**, including a letter grade (A-F), top strengths, weaknesses, and a single actionable recommendation.

Integration is powered by `google-genai` and `instructor` for strict Pydantic validation of all AI outputs.

---

## 🛡️ Security & Privacy

CRIT is designed with a "Security-First" mindset for enterprise codebases:

*   **XML Prompt Isolation**: User source code is wrapped in `<source_code_to_analyze>` tags. The system prompt includes a strict mandate to treat tagged content as untrusted data, preventing prompt injection attacks from malicious code comments.
*   **PII Redactor**: Before any report is written to disk, CRIT runs a deterministic **PII Redactor** (`scrub_sensitive_data`). It automatically masks:
    *   Emails
    *   IPv4 Addresses
    *   Secrets in assignments (passwords, API keys, tokens, etc.)
*   **Structured Redaction**: The LLM is instructed to redact sensitive data from its rationales and summaries as well.

---

## 📦 Installation & Pre-commit Integration

The most effective way to use CRIT is as a local quality gate via `pre-commit`.

### 1. Requirements
*   Python 3.10+
*   A valid `GEMINI_API_KEY` in your `.env` file.

### 2. Add to `.pre-commit-config.yaml`
Add the following block to your project's pre-commit configuration:

```yaml
repos:
-   repo: https://github.com/DeeTorch/crit-mvp
    rev: v1.0.0 # Use the latest version
    hooks:
    -   id: crit-audit
        # CRIT only analyzes the specific files being committed
```

---

## ⚙️ Configuration (`crit.yaml`)

You can customize CRIT's behavior by adding a `crit.yaml` file to your project root. This allows you to set custom quality thresholds, change metrics, and inject team standards.

```yaml
# Minimum score (0-10) required to pass the audit
min_pass_score: 7.0

# Quality metrics to evaluate (Map Phase)
evaluation_metrics:
  - Readability & Naming
  - Error Handling & Robustness
  - Security Practices
  - Performance & Efficiency
  - Documentation & Typing

# Team-specific instructions injected into every Map call
custom_instructions: |
  - Favor strict PEP-484 typing.
  - Ensure all exceptions are caught and logged.
  - Do not use 'assert' for runtime validation.
```

---

## 📈 Roadmap

*   **V2 CI/CD Bot**: Automated PR reviews with inline Markdown comments on GitHub.
*   **Context Engine**: Import resolution to analyze cross-file dependencies and prevent breaking changes.
