# CRIT Protocol Orchestrator (MVP)

A Map-Reduce pipeline for parsing, analyzing, and verifying structured documents and source code using Gemini models via the `google-genai` SDK and the `instructor` library for structured Pydantic validation.

## Protocol Overview

The **CRIT (Code/Content Review Inquisitor Protocol)** consists of a multi-stage Map-Reduce orchestration process:
1. **AST Parsing / Chunking**: Input files are parsed into abstract representation nodes (Markdown AST or Python AST) and divided into logical, zero-leak chunks.
2. **Map Pass (The Pure Empiricist / Evaluator)**: Concurrent async calls are spun up for each chunk. The model extracts individual evidence registries or scores each node element against pre-defined criteria (e.g. Security, Robustness, Readability).
3. **Reduce Pass (The Structural Inquisitor / Aggregator)**: Mapped evidence logs and per-element scores are compiled and synthesized to generate structural findings, calculate an overall composite score, and produce a final verdict.
4. **Validation Graph**: Final Pydantic validation guarantees schema compliance, cross-reference lineage, and computed verdict state integrity.

## Prerequisites

1. **Python 3.10+**
2. **Google Gemini API Key**: A valid key with access to `gemini-2.5-pro`.
3. **Local Environment Variables**:
   Create a `.env` file in the root directory:
   ```env
   GEMINI_API_KEY=your_actual_gemini_api_key_here
   ```

## Installation

Set up a virtual environment and install dependencies:
```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

*Note: The environment requires `instructor`, `google-genai`, `mistune`, `pydantic`, `python-dotenv`, `nest-asyncio`, and `jsonref`.*

## Running the Orchestrators

### 1. Main Content Pipeline (Markdown Spec Evaluator)
Runs the Markdown AST parser to find structural flaws and inconsistencies:
```powershell
$env:PYTHONUTF8=1
.\venv\Scripts\python.exe crit_protocol_orchestrator.py
```

### 2. Secondary Code Quality Pipeline (Python Source Evaluator)
Parses Python source code to evaluate elements (classes, functions) for code quality and security:
```powershell
$env:PYTHONUTF8=1
.\venv\Scripts\python.exe crit_orchestrator.py
```
