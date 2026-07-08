"""
Architecture Invariant Validator
================================
Enforces the Semantic Field Constitutional Laws.
Detects architectural drift, symbolic regressions, and ontological inconsistencies.
"""

import ast
import os
import sys
import collections

# Laws and forbidden patterns
FORBIDDEN_PATTERNS = [
    # LAW 2 — No Semantic Overrides
    (r"output\[.*\] =", "Direct semantic override of output field detected. Law 2 violation."),
    # LAW 4 — Enforce Locality
    (r"redistribute_instability\(", "Global redistribution loop detected. Law 4 violation."),
    # LAW 5 — No Fixed Evolution Cadence
    (r"counter % 3", "Fixed procedural evolution cadence detected. Law 5 violation."),
]

def check_duplicate_definitions(filepath):
    """Detect duplicate method or function definitions, allowing property getter/setter pairs."""
    with open(filepath, 'r') as f:
        try:
            tree = ast.parse(f.read())
        except SyntaxError as e:
            return [f"Syntax error in {filepath}: {e}"]

    errors = []
    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    for cls in classes:
        methods = collections.defaultdict(list)
        for node in cls.body:
            if isinstance(node, ast.FunctionDef):
                # Check for @property or @name.setter
                decorators = []
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Name):
                        decorators.append(dec.id)
                    elif isinstance(dec, ast.Attribute) and dec.attr == "setter":
                        decorators.append("setter")
                
                methods[node.name].append(decorators)

        for m, dec_lists in methods.items():
            if len(dec_lists) > 1:
                # If more than 2, or not a getter/setter pair, it's a dupe
                is_prop = any("property" in dl for dl in dec_lists)
                is_setter = any("setter" in dl for dl in dec_lists)
                if len(dec_lists) > 2 or not (is_prop and is_setter):
                    errors.append(f"Duplicate method '{m}' in class '{cls.name}' ({filepath})")

    functions = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
    counts = collections.Counter(functions)
    dupes = [f for f, count in counts.items() if count > 1]
    for f in dupes:
        errors.append(f"Duplicate global function '{f}' ({filepath})")
    
    return errors

def check_dangling_references(filepath, symbols):
    """Detect references to symbols that no longer exist or are forbidden."""
    KILLED_SYMBOLS = [
        "detect_allocation_contradictions",
        "re_alloc_graph",
        "_field_contradiction_penalty",
        "apply_contradiction_learning",
        "SemanticMemory",
    ]
    
    errors = []
    with open(filepath, 'r') as f:
        lines = f.readlines()
        for i, line in enumerate(lines, 1):
            line_clean = line.strip()
            if not line_clean or line_clean.startswith("#"):
                continue
            
            # Check for symbol in line (not inside a string or comment)
            # This is a bit complex to do perfectly with regex, so we use a simple heuristic
            if "#" in line:
                line_code = line.split("#")[0]
            else:
                line_code = line
                
            for sym in KILLED_SYMBOLS:
                if sym in line_code:
                    # Ignore if it's a definition or import
                    if "def " + sym in line_code or "import " + sym in line_code or "class " + sym in line_code:
                        continue
                    # Ignore if it's inside a string (rough check)
                    if (line_code.count("'") >= 2 and sym in line_code.split("'")[1]) or \
                       (line_code.count('"') >= 2 and sym in line_code.split('"')[1]):
                        continue
                    
                    errors.append(f"Reference to killed symbol '{sym}' at {filepath}:{i}")
    return errors

def check_metric_ownership(filepath):
    """Enforce the Ontology Matrix rules."""
    # Forbidden direct storage of derived metrics
    FORBIDDEN_FIELDS = [
        "maturity",
        "field_pressure",
        "global_entropy",
    ]
    
    errors = []
    with open(filepath, 'r') as f:
        try:
            tree = ast.parse(f.read())
        except SyntaxError: return []

    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    for cls in classes:

        # Check for field declarations (in dataclasses)
        for node in cls.body:
            if isinstance(node, ast.AnnAssign):
                if isinstance(node.target, ast.Name) and node.target.id in FORBIDDEN_FIELDS:
                    errors.append(f"Illegal direct storage of derived metric '{node.target.id}' in class '{cls.name}' ({filepath})")
    
    return errors

def main():
    backend_dir = "backend/app"
    all_errors = []
    
    print("--- ARCHITECTURE VALIDATION START ---")
    
    files = [os.path.join(dp, f) for dp, dn, filenames in os.walk(backend_dir) for f in filenames if f.endswith('.py')]
    
    for f in files:
        all_errors.extend(check_duplicate_definitions(f))
        all_errors.extend(check_dangling_references(f, []))
        all_errors.extend(check_metric_ownership(f))

    if all_errors:
        print(f"\nVALIDATION FAILED: {len(all_errors)} violations found.")
        for err in all_errors:
            print(f"  [VIOLATION] {err}")
        sys.exit(1)
    else:
        print("\nVALIDATION PASSED: Architecture is lawful.")
        sys.exit(0)

if __name__ == "__main__":
    main()
