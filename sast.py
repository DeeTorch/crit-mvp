import ast
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class SASTFinding:
    rule_id: str
    message: str
    line: int
    severity: str
    snippet: str

class SASTScanner(ast.NodeVisitor):
    """Local AST-based scanner for common security patterns."""
    
    def __init__(self, source: str):
        self.source_lines = source.splitlines()
        self.findings: List[SASTFinding] = []
        
    def scan(self) -> List[SASTFinding]:
        try:
            tree = ast.parse("\n".join(self.source_lines))
            self.visit(tree)
        except Exception:
            pass
        return self.findings

    def visit_Call(self, node: ast.Call):
        # SAST-001: Dangerous Functions
        if isinstance(node.func, ast.Name):
            if node.func.id in ["eval", "exec"]:
                self._add_finding("SAST-001", f"Use of dangerous function: {node.func.id}()", node)
        
        # Subprocess shell=True check
        if isinstance(node.func, ast.Attribute) and node.func.attr == "run":
            for keyword in node.keywords:
                if keyword.arg == "shell" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True:
                    self._add_finding("SAST-001", "Subprocess call with shell=True", node)

        # SAST-002: Weak Crypto
        if isinstance(node.func, ast.Attribute) and node.func.attr in ["md5", "sha1"]:
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "hashlib":
                self._add_finding("SAST-002", f"Use of weak hashing algorithm: {node.func.attr}", node)

        # SAST-003: SQL Injection Heuristics
        if isinstance(node.func, ast.Attribute) and node.func.attr == "execute":
            # Check if first arg is an f-string or string formatting
            if node.args:
                arg0 = node.args[0]
                if isinstance(arg0, (ast.JoinedStr, ast.BinOp)):
                    snippet = self.source_lines[node.lineno-1].upper()
                    if any(kw in snippet for kw in ["SELECT", "INSERT", "UPDATE", "DELETE"]):
                        self._add_finding("SAST-003", "Potential SQL injection via string formatting in execute()", node)

        self.generic_visit(node)

    def _add_finding(self, rule_id: str, message: str, node: ast.AST):
        line = node.lineno
        snippet = self.source_lines[line-1].strip()
        self.findings.append(SASTFinding(
            rule_id=rule_id,
            message=message,
            line=line,
            severity="high" if rule_id != "SAST-002" else "medium",
            snippet=snippet
        ))
