"""
Architecture Invariant Validator
 ================================
 Detects architectural drift: duplicate metric definitions, dangling
 references to removed modules, and illegal direct storage of derived
 metrics. Runs as part of the local validation quick gate and CI.

 Note: an earlier version of this file declared a ``FORBIDDEN_PATTERNS``
 table purporting to enforce "Semantic Field Constitutional Laws" (no
 ``output[...] =`` assignment, no ``redistribute_instability(`` call, no
 ``counter % 3``). That table was never invoked by ``main()`` and the
 patterns match legitimate code in the semantic engine
 (``semantic_pipeline.py``, ``topology_state.py``), so enforcing them
 as-is would false-positive. The dead constant has been removed rather
 than wired in to avoid breaking the gate; if those laws are real
 product invariants, they need scoped pattern definitions (e.g.
 restricted to specific modules/classes), not repo-wide regex bans.
"""

import ast
import collections
import os
import re
import sys


def check_duplicate_definitions(filepath):
    """Detect duplicate method or function definitions, allowing property getter/setter pairs."""
    with open(filepath) as f:
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
    for func_name in dupes:
        errors.append(f"Duplicate global function '{func_name}' ({filepath})")

    return errors


def check_dangling_references(filepath):
    """Detect references to symbols that no longer exist or are forbidden."""
    KILLED_SYMBOLS = [
        "detect_allocation_contradictions",
        "re_alloc_graph",
        "_field_contradiction_penalty",
        "apply_contradiction_learning",
        "SemanticMemory",
    ]

    errors = []
    with open(filepath) as f:
        lines = f.readlines()
        for i, line in enumerate(lines, 1):
            line_clean = line.strip()
            if not line_clean or line_clean.startswith("#"):
                continue

            # Check for symbol in line (not inside a string or comment)
            # This is a bit complex to do perfectly with regex, so we use a simple heuristic
            line_code = line.split("#")[0] if "#" in line else line

            for sym in KILLED_SYMBOLS:
                # Use word-boundary regex so a function with the killed
                # symbol as a parameter (``def foo(detect_allocation_contradictions):``)
                # or as a substring of an unrelated name is NOT
                # incorrectly flagged. The previous implementation did
                # a raw ``"def " + sym in line_code`` substring check
                # which misclassified parameter and attribute references.
                if not re.search(r"\b" + re.escape(sym) + r"\b", line_code):
                    continue
                # Definition sites are NOT references — ``def sym(``,
                # ``class sym:``, ``from X import sym``,
                # ``import X.sym``, ``import sym``. All of these
                # legitimately re-introduce the symbol.
                is_definition = bool(
                    re.search(r"\bdef\s+" + re.escape(sym) + r"\s*\(", line_code)
                    or re.search(r"\bclass\s+" + re.escape(sym) + r"\b", line_code)
                    or re.search(r"\bfrom\s+\S+\s+import\s+.*\b" + re.escape(sym) + r"\b", line_code)
                    or re.search(r"\bimport\s+\S*\." + re.escape(sym) + r"\b", line_code)
                    or re.search(r"\bimport\s+" + re.escape(sym) + r"\b", line_code),
                )
                if is_definition:
                    continue
                # Ignore if it's inside a string (rough check)
                if (line_code.count("'") >= 2 and sym in line_code.split("'")[1]) or (
                    line_code.count('"') >= 2 and sym in line_code.split('"')[1]
                ):
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
    with open(filepath) as f:
        try:
            tree = ast.parse(f.read())
        except SyntaxError:
            return []

    classes = [n for n in tree.body if isinstance(n, ast.ClassDef)]
    for cls in classes:
        # Check for field declarations (in dataclasses)
        for node in cls.body:
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id in FORBIDDEN_FIELDS:
                errors.append(
                    f"Illegal direct storage of derived metric '{node.target.id}' in class '{cls.name}' ({filepath})",
                )

    return errors


def check_forbidden_patterns(_filepath: str) -> list[str]:
    """No-op placeholder retained for backward compat.

    The ``FORBIDDEN_PATTERNS`` table has been removed (see module
    docstring). Returns an empty list so ``main()``'s call site stays
    stable if a future, properly-scoped law check is added here.
    """
    return []


def main():
    # Resolve against this script's location so the gate does not
    # silently pass with zero files scanned when invoked from a
    # different working directory (D-007).
    backend_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backend", "app")
    all_errors = []

    print("--- ARCHITECTURE VALIDATION START ---")  # noqa: T201

    files = [os.path.join(dp, f) for dp, dn, filenames in os.walk(backend_dir) for f in filenames if f.endswith(".py")]
    if not files:
        print(f"ERROR: no .py files found under {backend_dir}", file=sys.stderr)  # noqa: T201
        sys.exit(2)

    for f in files:
        all_errors.extend(check_duplicate_definitions(f))
        all_errors.extend(check_dangling_references(f))
        all_errors.extend(check_metric_ownership(f))
        all_errors.extend(check_forbidden_patterns(f))

    if all_errors:
        print(f"\nVALIDATION FAILED: {len(all_errors)} violations found.")  # noqa: T201
        for err in all_errors:
            print(f"  [VIOLATION] {err}")  # noqa: T201
        sys.exit(1)
    else:
        print(f"\nVALIDATION PASSED: Architecture is lawful ({len(files)} files scanned).")  # noqa: T201
        sys.exit(0)


if __name__ == "__main__":
    main()
