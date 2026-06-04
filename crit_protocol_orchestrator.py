import asyncio
import json
import mistune
import os
from dotenv import load_dotenv
import instructor
import google.genai as genai
from google.genai import types as genai_types
from typing import List, Dict, Any, Optional, Set
from enum import Enum
from pydantic import BaseModel, Field, model_validator, field_validator, ValidationInfo, computed_field

# ==========================================
# API KEY INITIALIZATION FOR LOCAL ENV
# ==========================================
load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if not GEMINI_API_KEY or GEMINI_API_KEY == "your_api_key_here":
    print("\n[⚠️] GEMINI_API_KEY not found or still a placeholder. Please add it to your .env file.")
    exit(1)

# ==========================================
# 0. ARCHITECTURE & SCHEMAS
# ==========================================

TARGET_MODEL = "gemini-2.5-pro"

class SeverityTier(str, Enum):
    CF = "CF"
    MW = "MW"
    mW = "mW"
    OB = "OB"
    ST = "ST"

class ClaimTag(str, Enum):
    VERIFIED = "VERIFIED"
    INFERRED = "INFERRED"
    HYPOTHESIS = "HYPOTHESIS"
    UNKNOWN = "UNKNOWN"

class VerdictState(str, Enum):
    ACCEPT = "Accept"
    MINOR_REVISION = "Minor Revision Required"
    MAJOR_REVISION = "Major Revision Required"
    REJECT_RESUBMIT = "Reject with Resubmit"
    REJECT = "Reject"

class EvidenceRegistry(BaseModel):
    ref_id: str = Field(..., pattern=r'^EV-\d{2,4}$')
    analytical_rationale: str = Field(..., description="Chain-of-thought: Why does this claim exist and what is its strict structural boundary?")
    artifact_location: str = Field(..., description="Explicit bounding box, line number, or header.")
    claim_parsed: str = Field(..., min_length=5)
    tag_status: ClaimTag

class StructuralFinding(BaseModel):
    finding_id: str = Field(..., pattern=r'^(CF|MW|mW|OB|ST)-\d{2,4}$')
    severity: SeverityTier
    diagnostic_rationale: str = Field(..., description="Chain-of-thought: Step-by-step justification mapping the evidence to the chosen severity.")
    evidence_refs: List[str] = Field(..., description="Must exactly match available EV- or EC- IDs.")
    description: str
    remediation_protocol: Optional[str] = Field(None, description="Must follow Solution Preference Framework.")

    @field_validator('evidence_refs')
    @classmethod
    def validate_evidence_lineage(cls, v: List[str], info: ValidationInfo) -> List[str]:
        context = info.context
        if not context or 'valid_ids' not in context:
            return v
        valid_ids: Set[str] = context['valid_ids']
        invalid_refs = [ref for ref in v if ref not in valid_ids]
        if invalid_refs:
            raise ValueError(
                f"CRIT Lineage Broken! The following evidence references do not exist in the "
                f"EvidenceRegistry: {invalid_refs}. Allowed valid IDs are: {list(valid_ids)}. "
                f"Correct your output and only reference existing IDs."
            )
        return v

    @model_validator(mode='after')
    def validate_remediation(self):
        if self.severity in [SeverityTier.CF, SeverityTier.MW] and not self.remediation_protocol:
            raise ValueError(f"{self.severity.value} requires a strict remediation protocol.")
        return self

class DimensionalMatrix(BaseModel):
    D01_novelty_dimensions: float = Field(1.0, ge=0.0, le=1.0)
    D02_major_weaknesses_inverse: float = Field(1.0, ge=0.0, le=1.0) 
    D03_inferral_catalogs: float = Field(1.0, ge=0.0, le=1.0)
    D04_schema_completeness: float = Field(1.0, ge=0.0, le=1.0)
    D05_non_matching_elements: float = Field(1.0, ge=0.0, le=1.0)
    D06_threemite_descriptions: float = Field(1.0, ge=0.0, le=1.0)
    D07_schema_complexity: float = Field(1.0, ge=0.0, le=1.0)

    def calculate_pure_score(self, findings: List[StructuralFinding]) -> float:
        """
        Calculates score analytically WITHOUT mutating state fields permanently.
        Ensures idempotency across infinite serialization runs.
        """
        # Read baseline fields safely
        d02 = self.D02_major_weaknesses_inverse
        d04 = self.D04_schema_completeness
        
        # Calculate isolated penalties cleanly
        for f in findings:
            if f.severity == SeverityTier.CF:
                d02 = max(0.0, d02 - 0.50)
            elif f.severity == SeverityTier.MW:
                d02 = max(0.0, d02 - 0.25)
            elif f.severity == SeverityTier.mW:
                d04 = max(0.0, d04 - 0.10)
                
        weights = { 'D01': 0.05, 'D02': 0.25, 'D03': 0.10, 'D04': 0.30, 'D05': 0.10, 'D06': 0.10, 'D07': 0.10 }
        
        score = (
            self.D01_novelty_dimensions * weights['D01'] +
            d02 * weights['D02'] +
            self.D03_inferral_catalogs * weights['D03'] +
            d04 * weights['D04'] +
            self.D05_non_matching_elements * weights['D05'] +
            self.D06_threemite_descriptions * weights['D06'] +
            self.D07_schema_complexity * weights['D07']
        )
        return round(score, 4)

class EvaluationReport(BaseModel):
    report_id: str = "REP-LIVE-001"
    evidence_registry: List[EvidenceRegistry]
    structural_findings: List[StructuralFinding]
    scoring_matrix: DimensionalMatrix = Field(default_factory=DimensionalMatrix)
    
    @computed_field
    @property
    def composite_score(self) -> float:
        return self.scoring_matrix.calculate_pure_score(self.structural_findings)

    @computed_field
    @property
    def final_verdict(self) -> VerdictState:
        has_cf = any(f.severity == SeverityTier.CF for f in self.structural_findings)
        has_mw = any(f.severity == SeverityTier.MW for f in self.structural_findings)
        score = self.composite_score
        
        if has_cf: return VerdictState.REJECT_RESUBMIT
        elif has_mw and score >= 0.75: return VerdictState.MAJOR_REVISION
        if score >= 0.90: return VerdictState.ACCEPT
        elif 0.75 <= score < 0.90: return VerdictState.MINOR_REVISION
        elif 0.60 <= score < 0.75: return VerdictState.MAJOR_REVISION
        elif 0.40 <= score < 0.60: return VerdictState.REJECT_RESUBMIT
        else: return VerdictState.REJECT

# ── Batch wrappers (GENAI_STRUCTURED_OUTPUTS requires top-level object) ──────
class EvidenceRegistryBatch(BaseModel):
    """Container so Gemini structured outputs gets an object root, not a bare array."""
    items: List[EvidenceRegistry] = Field(default_factory=list)

class StructuralFindingBatch(BaseModel):
    """Container so Gemini structured outputs gets an object root, not a bare array."""
    items: List[StructuralFinding] = Field(default_factory=list)

# ==========================================
# 1. PROMPTS & INSTRUCTOR CLIENT
# ==========================================
PURE_EMPIRICIST_PROMPT = """You are the Pure Empiricist AI. Your sole function is to execute the "Analytical Verification" pass of the CRIT v1.0.0 protocol. You operate strictly on the provided Abstract Syntax Tree (AST) representing a technical document.

Mandate: Zero External Assumptions
1. You possess zero domain knowledge outside of the provided text.
2. If an idea, variable, or rule is not explicitly defined in the provided AST, it does not exist as a fact.
3. Conversational filler or non-technical prose must be ignored entirely (do not map it).

Claim Tagging Rules:
VERIFIED: The claim includes explicit, hardcoded parameters, thresholds, or mathematical bounds.
INFERRED: The claim relies on adjacent logic but lacks explicit boundaries.
HYPOTHESIS: The claim states a capability (e.g., "it scales") but provides zero mechanism or proof.
UNKNOWN: The claim references external systems, unstated definitions, or undefined acronyms.

Instruction: Extract all structural claims from the AST into the EvidenceRegistry schema. You MUST write your analytical_rationale BEFORE extracting the claim."""

STRUCTURAL_INQUISITOR_PROMPT = """You are the Structural Inquisitor. Your function is to process the EvidenceRegistry logs to generate actionable StructuralFinding objects.

Mandate: The Solution Preference Framework
When generating a remediation_protocol for a CRITICAL_FLAW (CF) or MAJOR_WEAKNESS (MW), you MUST NOT write natural language advice. You must strictly follow the Solution Preference Framework:
1. Formal/Mathematical Specification: Propose bounded parameters.
2. Strongly-Typed Enums: Propose explicit states.
3. Declarative Constraints: Propose fixed rules.

Severity Tier Rules:
CF: A missing variable, unbound threshold, or logical contradiction that prevents the system from being mathematically modeled or safely compiled.
MW: Ambiguity that requires human assumption to implement.
mW: Poor structural formatting or isolated undefined terms that do not break core logic.

Instruction: Analyze the evidence. You MUST write your diagnostic_rationale explaining why the severity was chosen BEFORE assigning the severity or finding_id. Every finding MUST cross-reference an explicit EV- ID. DO NOT invent EV- IDs that are not present in the payload."""

client = instructor.from_genai(
    genai.Client(api_key=GEMINI_API_KEY),
    mode=instructor.Mode.GENAI_STRUCTURED_OUTPUTS,
    use_async=True,
)

# ==========================================
# 2. DETERMINISTIC PARSER & CHUNKING
# ==========================================
class MarkdownASTParser:
    def __init__(self):
        self.parser = mistune.create_markdown(renderer=None, plugins=['table', 'url', 'task_lists'])
        self.node_counter = 1

    def _generate_node_id(self) -> str:
        node_id = f"N-{self.node_counter:02d}"
        self.node_counter += 1
        return node_id

    def _extract_text(self, block: Dict[str, Any]) -> str:
        # mistune 3.x uses 'raw' for text content; mistune 2.x used 'text'
        if 'raw' in block: return block['raw']
        if 'text' in block: return block['text']
        if 'children' in block and isinstance(block['children'], list):
            return "".join(self._extract_text(child) for child in block['children'])
        return ""

    def parse_to_nodes(self, markdown_text: str) -> List[Dict[str, Any]]:
        raw_ast = self.parser(markdown_text)
        flat_nodes = []
        header_stack = [] 

        for block in raw_ast:
            block_type = block.get('type')
            
            # Simple line tracking (mistune structure may vary slightly, defaulting to block order tracking)
            location_str = f"Block type: {block_type}"
            
            if block_type == 'heading':
                node_type = "HEADER"
                level = block.get('attrs', {}).get('level', 1)
                content = self._extract_text(block)
                node_id = self._generate_node_id()

                while header_stack and header_stack[-1]['level'] >= level:
                    header_stack.pop()
                current_parent = header_stack[-1]['node_id'] if header_stack else None
                header_stack.append({'node_id': node_id, 'level': level})

            elif block_type == 'block_code':
                node_type = "CONSTRAINT" if "constraint" in block.get('attrs', {}).get('info', block.get('info', '')).lower() else "CODE_BLOCK"
                # mistune 3.x uses 'raw' for code content
                content = (block.get('raw') or block.get('text', '')).strip()
                node_id = self._generate_node_id()
                current_parent = header_stack[-1]['node_id'] if header_stack else None

            elif block_type in ['paragraph', 'list', 'block_quote']:
                node_type = block_type.upper()
                content = self._extract_text(block).strip()
                if not content: continue
                node_id = self._generate_node_id()
                current_parent = header_stack[-1]['node_id'] if header_stack else None
            else:
                continue

            flat_nodes.append({
                "node_id": node_id, "parent_id": current_parent,
                "node_type": node_type, "artifact_location": location_str, "content": content
            })
        return flat_nodes

def chunk_ast_by_headers(ast_nodes: List[Dict[str, Any]], target_level: int = 2) -> List[List[Dict[str, Any]]]:
    chunks: List[List[Dict[str, Any]]] = []
    current_chunk: List[Dict[str, Any]] = []

    for node in ast_nodes:
        is_header = node.get("node_type") == "HEADER"
        if is_header:
            if node.get("parent_id") is None or len(chunks) == 0:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = [node]
                continue
        current_chunk.append(node)
        
    if current_chunk:
        chunks.append(current_chunk)
    return chunks

# ==========================================
# 3. ASYNC MAP-REDUCE PIPELINE
# ==========================================
async def process_chunk(chunk_nodes: List[Dict[str, Any]], chunk_index: int) -> List[EvidenceRegistry]:
    print(f"   [⚙️ Worker {chunk_index}] Analyzing {len(chunk_nodes)} nodes...")
    try:
        batch: EvidenceRegistryBatch = await client.chat.completions.create(
            model=TARGET_MODEL,
            response_model=EvidenceRegistryBatch,
            max_retries=3,
            messages=[
                genai_types.Content(
                    role="user",
                    parts=[genai_types.Part.from_text(
                        text=PURE_EMPIRICIST_PROMPT
                        + "\n\nExtract structural claims from this AST chunk:\n"
                        + json.dumps(chunk_nodes)
                    )],
                )
            ],
        )
        print(f"   [⚙️ Worker {chunk_index}] Extracted {len(batch.items)} evidence item(s).")
        return batch.items
    except Exception as e:
        print(f"   [❌ Worker {chunk_index}] Failed validation boundary: {str(e)}")
        return []

async def run_parallel_crit_pipeline(ast_nodes: List[Dict[str, Any]]) -> EvaluationReport:
    print("\n[⚡] Step 1: Executing Semantic AST-Aware Chunking...")
    chunks = chunk_ast_by_headers(ast_nodes)
    print(f" -> Segmented document into {len(chunks)} independent, zero-leak structural chunks.")

    print("\n[⚡] Step 2: Spinning up Asynchronous Map Pass (The Pure Empiricist)...")
    tasks = [process_chunk(chunk, i+1) for i, chunk in enumerate(chunks)]
    completed_slices = await asyncio.gather(*tasks)
    
    master_evidence: List[EvidenceRegistry] = []
    global_ev_counter = 1
    for slice_list in completed_slices:
        for ev in slice_list:
            ev.ref_id = f"EV-{global_ev_counter:02d}"
            global_ev_counter += 1
            master_evidence.append(ev)
            
    print(f" -> Map-Reduce complete. Compiled {len(master_evidence)} validated evidence items.")
    compiled_valid_ids = {ev.ref_id for ev in master_evidence}

    print("\n[⚡] Step 3: Launching Structural Inquisitor Reduction Pass...")
    evidence_payload = [ev.model_dump() for ev in master_evidence]
    
    try:
        finding_batch: StructuralFindingBatch = await client.chat.completions.create(
            model=TARGET_MODEL,
            response_model=StructuralFindingBatch,
            max_retries=3,
            validation_context={"valid_ids": compiled_valid_ids},
            messages=[
                genai_types.Content(
                    role="user",
                    parts=[genai_types.Part.from_text(
                        text=STRUCTURAL_INQUISITOR_PROMPT
                        + "\n\nAnalyze compiled evidence payload:\n"
                        + json.dumps(evidence_payload)
                    )],
                )
            ],
        )
        generated_findings = finding_batch.items
        print(f" -> Inquisitor mapped out {len(generated_findings)} formal structural findings.")
    except Exception as e:
        print(f" -> Inquisitor validation failed completely after retries: {str(e)}")
        generated_findings = []

    print("\n[⚡] Step 4: Stitching Final Evaluation Report Graphs...")
    report = EvaluationReport(evidence_registry=master_evidence, structural_findings=generated_findings)
    return report

# ==========================================
# 4. EDGE CASE EXECUTION
# ==========================================
if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply() # Fixes async execution loops running inside Jupyter/Colab

    synthetic_spec = """# Autonomous Drone Grid Mesh v4.0.0
## Power Distribution & Node Isolation Topology
The edge communication grid will maintain a minimum 99.999% mesh up-time over wireless nodes by executing instant peer-to-peer route failovers.
```constraint
Max_Failover_Attempts = 3
Isolation_State = Enum["ACTIVE", "STANDBY", "ISOLATED"]
```
## Fault Isolation Subsystem
If a node drops below the critical voltage threshold defined in Section 1, the grid automatically applies a permanent bypass connection.
"""
    
    print("\n[🔍] Parsing Raw Markdown Spec into AST...")
    parser = MarkdownASTParser()
    mock_ast_data = parser.parse_to_nodes(synthetic_spec)
    
    final_report = asyncio.run(run_parallel_crit_pipeline(mock_ast_data))
    
    print("\n===========================================")
    print("    🔴 CRIT PIPELINE LIVE TRACE LOGS  ")
    print("===========================================")
    print(f"Final Score: {final_report.composite_score}")
    print(f"Verdict: {final_report.final_verdict.value}")
    print("\nFindings Triggered:")
    for finding in final_report.structural_findings:
        print(f"- [{finding.severity.value}] {finding.description} (Refs: {finding.evidence_refs})")