"""
Structure Analysis Engine
===========================
Pre-extraction structure reasoning that analyzes the DOM before any
value extraction happens.

This is the FIRST step in the new pipeline, before any values are touched.

Core principle: Understand structure first, extract values second.
"""

from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set
from collections import defaultdict
import re

from bs4 import BeautifulSoup, Tag, NavigableString

from app.semantic_ir import SemanticToken, SemanticRecord, SemanticType, Span, DatasetIR


@dataclass
class DOMRegion:
    """A region of the DOM with structural metadata."""
    selector: str  # CSS-like path
    tag: str
    depth: int
    text_content: str
    child_count: int
    sibling_index: int
    css_classes: List[str] = field(default_factory=list)
    children: List["DOMRegion"] = field(default_factory=list)
    is_repeated: bool = False
    repetition_count: int = 0


@dataclass
class ContainerCandidate:
    """A candidate data container identified by structural analysis."""
    selector: str
    tag: str
    sample_count: int  # How many similar siblings
    avg_child_count: float
    text_density: float  # Ratio of text to markup
    depth: int
    score: float  # Overall container likelihood score
    children: List["ContainerCandidate"] = field(default_factory=list)


def analyze_dom_structure(html: str) -> List[DOMRegion]:
    """Analyze the DOM to identify structural regions.

    Returns a tree of DOMRegion objects with structural metadata.
    """
    soup = BeautifulSoup(html, "html.parser")
    regions: List[DOMRegion] = []
    _walk_tree(soup, regions, depth=0, selector="")
    return regions


def _walk_tree(node, regions: List[DOMRegion], depth: int, selector: str):
    """Recursively walk the DOM tree, collecting regions."""
    if not hasattr(node, "name") or not node.name:
        return

    # Skip non-semantic tags
    if node.name in {"script", "style", "meta", "link", "noscript", "iframe"}:
        return

    tag = node.name
    css_classes = node.get("class", []) if hasattr(node, "get") else []
    children = list(node.children) if hasattr(node, "children") else []

    # Build selector
    class_sel = ".".join(css_classes) if css_classes else ""
    current_sel = f"{selector} > {tag}" if selector else tag
    if class_sel:
        current_sel += f".{class_sel}"

    # In sibling index
    parent = node.parent if hasattr(node, "parent") else None
    sibling_index = 0
    if parent and hasattr(parent, "children"):
        for i, child in enumerate(parent.children):
            if child is node:
                sibling_index = i
                break

    region = DOMRegion(
        selector=current_sel,
        tag=tag,
        depth=depth,
        text_content=node.get_text(strip=True) if hasattr(node, "get_text") else "",
        child_count=len(children),
        sibling_index=sibling_index,
        css_classes=css_classes if isinstance(css_classes, list) else [],
    )

    regions.append(region)

    for child in children:
        if isinstance(child, Tag):
            child_regions = []
            _walk_tree(child, child_regions, depth + 1, current_sel)
            region.children.extend(child_regions)
            regions.extend(child_regions)


def detect_repeated_containers(html: str, min_repetition: int = 3) -> List[ContainerCandidate]:
    """Find repeated container candidates in the DOM.

    Repeated containers with similar structure likely contain data records.
    """
    soup = BeautifulSoup(html, "html.parser")

    # Find all tags that might be containers
    candidates: List[ContainerCandidate] = []
    seen_selectors: Dict[str, int] = defaultdict(int)

    for tag in ["div", "li", "tr", "article", "section", "ul", "ol"]:
        elements = soup.find_all(tag)
        if len(elements) < min_repetition:
            continue

        # Group by class signature
        groups: Dict[str, List] = defaultdict(list)
        for el in elements:
            classes = ".".join(sorted(el.get("class", []))) if hasattr(el, "get") else ""
            groups[classes].append(el)

        for class_sig, group in groups.items():
            if len(group) < min_repetition:
                continue

            # Compute structural stats from first few
            samples = group[:5]
            child_counts = []
            text_densities = []
            for sample in samples:
                child_count = len(list(sample.children)) if hasattr(sample, "children") else 0
                child_counts.append(child_count)
                text = sample.get_text(strip=True) if hasattr(sample, "get_text") else ""
                html_len = len(str(sample)) if hasattr(sample, "__str__") else 1
                text_densities.append(len(text) / max(html_len, 1))

            candidate = ContainerCandidate(
                selector=f"{tag}.{class_sig}" if class_sig else tag,
                tag=tag,
                sample_count=len(group),
                avg_child_count=sum(child_counts) / len(child_counts),
                text_density=sum(text_densities) / len(text_densities),
                depth=_get_depth(group[0]),
                score=0.5,
            )
            candidates.append(candidate)

    # Score candidates
    for c in candidates:
        score = 0.0
        score += min(c.sample_count / 20, 1.0) * 0.3  # More repetitions = better
        score += min(c.avg_child_count / 5, 1.0) * 0.3  # More children = richer structure
        score += (1.0 - abs(c.text_density - 0.3) / 0.3) * 0.2  # Goldilocks text density
        score += (1.0 - min(c.depth / 10, 1.0)) * 0.2  # Shallow depth = better
        c.score = min(score, 1.0)

    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates


def _get_depth(element) -> int:
    """Compute DOM depth of an element."""
    depth = 0
    parent = element.parent if hasattr(element, "parent") else None
    while parent and hasattr(parent, "name") and parent.name:
        depth += 1
        parent = parent.parent if hasattr(parent, "parent") else None
    return depth


def extract_structural_signature(html_snippet: str) -> Dict:
    """Extract a structural signature from an HTML snippet.

    Returns metadata about the structure WITHOUT extracting any values.
    """
    soup = BeautifulSoup(html_snippet, "html.parser")
    containers = detect_repeated_containers(html_snippet)

    # Count tag frequencies
    tags: Dict[str, int] = defaultdict(int)
    for tag in soup.find_all(True):
        if tag.name not in {"script", "style", "meta"}:
            tags[tag.name] += 1

    return {
        "top_containers": [(c.selector, c.score, c.sample_count) for c in containers[:3]],
        "tag_distribution": dict(sorted(tags.items(), key=lambda x: -x[1])[:10]),
        "total_tags": sum(tags.values()),
        "structure_type": "cards" if any(c.tag in {"div", "article", "section"} for c in containers[:3])
                         else "table" if any(c.tag == "tr" for c in containers[:3])
                         else "list" if any(c.tag in {"li", "ul", "ol"} for c in containers[:3])
                         else "mixed",
    }
