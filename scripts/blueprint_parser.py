"""ARC 02 — Blueprint Graph Intelligence & AST Parser

Parses Epic Games' native S-expression Blueprint Graph DSL (from BlueprintTools.read_graph_dsl)
into a structured Abstract Syntax Tree (AST), extracting:
- Event and function declarations
- Function/action calls and target categories
- Variable bindings, reads, and writes
- Control flow branching (if, elif, else, while, for, switch)
- Multi-exec latent task continuations
- Cyclomatic complexity and graph metrics
- Compact token-budgeted summaries for Codex context

STRICT SAFETY RESTRICTION: Read-only inspection only. Never calls write_graph_dsl.
"""
import re
from typing import Any, Dict, List, Optional, Set, Tuple, Union


def tokenize_dsl(dsl_text: str, strict=False) -> List[str]:
    """Tokenize comments outside strings, preserving Epic escape semantics."""
    tokens = []
    i = 0
    while i < len(dsl_text):
        ch = dsl_text[i]
        if ch.isspace():
            i += 1
        elif ch == ';':
            end = dsl_text.find('\n', i)
            i = len(dsl_text) if end < 0 else end
        elif ch in '()':
            tokens.append(ch)
            i += 1
        elif ch == '"':
            start = i
            i += 1
            while i < len(dsl_text) and dsl_text[i] != '"':
                i += 2 if dsl_text[i] == chr(92) else 1
            if i >= len(dsl_text):
                if strict: raise ValueError('Unterminated DSL string')
            else: i += 1
            tokens.append(dsl_text[start:i])
        else:
            start = i
            while i < len(dsl_text) and not dsl_text[i].isspace() and dsl_text[i] not in '();':
                i += 1
            tokens.append(dsl_text[start:i])
    return tokens


def parse_sexpr(tokens: List[str], strict=False) -> List[Any]:
    """Converts a token stream into nested Python lists."""
    stack: List[List[Any]] = [[]]
    for token in tokens:
        if token == '(':
            new_list: List[Any] = []
            stack[-1].append(new_list)
            stack.append(new_list)
        elif token == ')':
            if len(stack) > 1:
                stack.pop()
            elif strict: raise ValueError('Unexpected closing parenthesis')
        else:
            # Parse primitive values
            val: Any = token
            if token.startswith('"') and token.endswith('"'):
                val = token[1:-1].replace(chr(92) + chr(34), chr(34)).replace(chr(92) * 2, chr(92))
            elif token.lower() == 'true':
                val = True
            elif token.lower() == 'false':
                val = False
            else:
                try:
                    if '.' in token:
                        val = float(token)
                    else:
                        val = int(token)
                except ValueError:
                    val = token
            stack[-1].append(val)

    if strict and len(stack) != 1: raise ValueError("Unclosed parenthesis")
    return stack[0]


class BlueprintAST:
    def __init__(self):
        self.events: List[Dict[str, Any]] = []
        self.functions: List[Dict[str, Any]] = []
        self.all_calls: List[str] = []
        self.variables_read: Set[str] = set()
        self.variables_written: Set[str] = set()
        self.branch_count: int = 0
        self.total_nodes: int = 0
        self.unsupported: List[str] = []

    @property
    def cyclomatic_complexity(self) -> int:
        return 1 + self.branch_count

    def to_dict(self) -> Dict[str, Any]:
        return {
            'metrics': {
                'total_nodes': self.total_nodes,
                'event_count': len(self.events),
                'function_count': len(self.functions),
                'call_count': len(self.all_calls),
                'unique_calls': sorted(list(set(self.all_calls))),
                'variables_read': sorted(list(self.variables_read)),
                'variables_written': sorted(list(self.variables_written)),
                'branch_count': self.branch_count,
                'cyclomatic_complexity': self.cyclomatic_complexity,
            },
            'events': self.events,
            'functions': self.functions,
            'unsupported_constructs': self.unsupported,
        }


class BlueprintParser:
    def __init__(self):
        pass

    def parse(self, dsl_text: str) -> BlueprintAST:
        ast = BlueprintAST()
        if not dsl_text or not dsl_text.strip():
            return ast

        tokens = tokenize_dsl(dsl_text)
        trees = parse_sexpr(tokens)

        for form in trees:
            if not isinstance(form, list) or not form:
                continue
            head = form[0]
            if head == 'event':
                ast.events.append(self._parse_event(form, ast))
            elif head == 'fn':
                ast.functions.append(self._parse_function(form, ast))
            else:
                # Top level expression
                self._traverse_statement(form, ast)

        return ast

    def _parse_event(self, form: List[Any], ast: BlueprintAST) -> Dict[str, Any]:
        ast.total_nodes += 1
        name = str(form[1]) if len(form) > 1 else 'UnnamedEvent'
        params: List[str] = []
        body_start = 2

        if len(form) > 2 and isinstance(form[2], list):
            params = [str(p) for p in form[2]]
            body_start = 3

        calls: List[str] = []
        reads: Set[str] = set()
        writes: Set[str] = set()

        for stmt in form[body_start:]:
            self._traverse_statement(stmt, ast, calls, reads, writes)

        return {
            'name': name,
            'parameters': params,
            'calls': calls,
            'variables_read': sorted(list(reads)),
            'variables_written': sorted(list(writes)),
            'statement_count': len(form[body_start:]),
        }

    def _parse_function(self, form: List[Any], ast: BlueprintAST) -> Dict[str, Any]:
        ast.total_nodes += 1
        name = str(form[1]) if len(form) > 1 else 'UnnamedFunction'
        params: List[str] = []
        body_start = 2

        if len(form) > 2 and isinstance(form[2], list):
            params = [str(p) for p in form[2]]
            body_start = 3

        calls: List[str] = []
        reads: Set[str] = set()
        writes: Set[str] = set()
        returns: List[Any] = []

        for stmt in form[body_start:]:
            if isinstance(stmt, list) and stmt and stmt[0] == 'return':
                returns.append(stmt[1:] if len(stmt) > 1 else None)
            self._traverse_statement(stmt, ast, calls, reads, writes)

        return {
            'name': name,
            'parameters': params,
            'returns': returns,
            'calls': calls,
            'variables_read': sorted(list(reads)),
            'variables_written': sorted(list(writes)),
            'statement_count': len(form[body_start:]),
        }

    def _traverse_statement(self, stmt: Any, ast: BlueprintAST,
                            calls: Optional[List[str]] = None,
                            reads: Optional[Set[str]] = None,
                            writes: Optional[Set[str]] = None):
        if not isinstance(stmt, list) or not stmt:
            if isinstance(stmt, str) and not stmt.startswith(':'):
                if reads is not None: reads.add(stmt)
                ast.variables_read.add(stmt)
            return

        ast.total_nodes += 1
        head = stmt[0]

        if head == 'bind':
            # (bind var expr) or (bind (a b) expr)
            if len(stmt) > 1:
                target = stmt[1]
                if isinstance(target, list):
                    for t in target:
                        if writes is not None: writes.add(str(t))
                        ast.variables_written.add(str(t))
                elif isinstance(target, str):
                    if writes is not None: writes.add(target)
                    ast.variables_written.add(target)
            for sub in stmt[2:]:
                self._traverse_statement(sub, ast, calls, reads, writes)

        elif head in ('if', 'elif'):
            ast.branch_count += 1
            for sub in stmt[1:]:
                self._traverse_statement(sub, ast, calls, reads, writes)

        elif head in ('for', 'while', 'switch'):
            ast.branch_count += 1
            for sub in stmt[1:]:
                self._traverse_statement(sub, ast, calls, reads, writes)

        elif head == 'else':
            for sub in stmt[1:]:
                self._traverse_statement(sub, ast, calls, reads, writes)

        elif head == 'return':
            for sub in stmt[1:]:
                self._traverse_statement(sub, ast, calls, reads, writes)

        elif isinstance(head, str) and '|' in head:
            # Action / Function / Node Call: e.g. UserInterface|Animation|PlayAnimation
            call_name = head
            if calls is not None: calls.append(call_name)
            ast.all_calls.append(call_name)

            # Check variable getters / setters
            if head.startswith('Variables|') and '|Get' in head:
                var_name = head.split('|Get')[-1]
                if reads is not None: reads.add(var_name)
                ast.variables_read.add(var_name)
            elif head.startswith('Variables|') and '|Set' in head:
                var_name = head.split('|Set')[-1]
                if writes is not None: writes.add(var_name)
                ast.variables_written.add(var_name)

            for arg in stmt[1:]:
                self._traverse_statement(arg, ast, calls, reads, writes)

        elif isinstance(head, str) and head.startswith(':'):
            # Continuation block: (:ExecOut1 ...)
            for sub in stmt[1:]:
                self._traverse_statement(sub, ast, calls, reads, writes)

        else:
            # Generic expression or operator (+, -, select, etc.)
            for sub in stmt[1:]:
                self._traverse_statement(sub, ast, calls, reads, writes)


def summarize_dsl(dsl_text: str, max_calls: int = 10) -> Dict[str, Any]:
    parser = BlueprintParser()
    ast = parser.parse(dsl_text)
    res = ast.to_dict()
    res['summary'] = (
        f"Graph containing {len(ast.events)} events, {len(ast.functions)} functions, "
        f"{len(ast.all_calls)} calls (Cyclomatic Complexity: {ast.cyclomatic_complexity})"
    )
    return res


def format_ast_markdown(ast_dict: Dict[str, Any], title: str = "Blueprint Logic Summary") -> str:
    lines = [f"### {title}"]
    metrics = ast_dict.get('metrics', {})
    lines.append(f"- **Complexity:** Complexity Score: {metrics.get('cyclomatic_complexity', 1)} | Nodes: {metrics.get('total_nodes', 0)} | Branches: {metrics.get('branch_count', 0)}")
    
    events = ast_dict.get('events', [])
    if events:
        lines.append("- **Events Handled:**")
        for ev in events:
            params = f"({', '.join(ev.get('parameters', []))})" if ev.get('parameters') else "()"
            calls = ', '.join([c.split('|')[-1] for c in ev.get('calls', [])[:4]])
            lines.append(f"  - `{ev.get('name')}{params}`: calls [{calls}]")

    funcs = ast_dict.get('functions', [])
    if funcs:
        lines.append("- **Functions Defined:**")
        for fn in funcs:
            params = f"({', '.join(fn.get('parameters', []))})" if fn.get('parameters') else "()"
            calls = ', '.join([c.split('|')[-1] for c in fn.get('calls', [])[:4]])
            lines.append(f"  - `{fn.get('name')}{params}`: calls [{calls}]")

    reads = metrics.get('variables_read', [])
    writes = metrics.get('variables_written', [])
    if reads or writes:
        lines.append(f"- **State Usage:** Reads: `[{', '.join(reads[:6])}]` | Writes: `[{', '.join(writes[:6])}]`")

    return '\n'.join(lines)

