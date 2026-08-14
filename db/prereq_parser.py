"""Best-effort regex parser that turns free-text course-catalog prerequisite /
corequisite sentences (from catalog_scraper/output/*.json) into a small tree of
plain dicts shaped like the course_rule_nodes table.

This is deliberately a heuristic, not a full grammar: catalog prose is not
fully regular ("Math 1215 or 1221 or 2222", "grade of C or better in each of
the following: ...; ... or ..."). Anything we can't confidently resolve to a
known course is kept as a TEXT node (raw source text) rather than dropped, so
a human can review it later instead of silently losing information.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass
class RuleNode:
    node_type: str  # GROUP | COURSE | STANDING | TEXT
    requisite_type: str = "PREREQUISITE"
    rule_operator: str | None = None
    required_course_id: int | None = None
    minimum_grade: str | None = None
    minimum_standing: str | None = None
    text_value: str | None = None
    source_text: str | None = None
    children: list["RuleNode"] = field(default_factory=list)


_REQUISITE_BLOCK_RE = re.compile(
    r"(Prerequisite/Corequisite|Prerequisites?|Co-?requisites?)\s*:\s*"
    r"(.*?)(?=(?:Prerequisites?|Co-?requisites?)\s*:|\(Co-listed|\Z)",
    re.IGNORECASE | re.DOTALL,
)

_GRADE_CLAUSE_RE = re.compile(
    r'grade\s+of\s+"?([A-F][+-]?)"?\s+or\s+better\s+in\s+'
    r"(?:each\s+of\s+(?:the\s+following:?\s*)?)?([^.]+)",
    re.IGNORECASE,
)

_STANDING_RE = re.compile(
    r"(freshman|sophomore|junior|senior|graduate)\s+standing", re.IGNORECASE
)

# Some catalog entries phrase a true corequisite ("must be taken concurrently")
# as "Prerequisite: Accompanied by X" rather than using a "Corequisite:"
# label. Left as PREREQUISITE, a mutual pair of these (each course
# "accompanied by" the other) is an unsatisfiable ordering cycle, so treat
# this phrasing as what it actually means.
_ACCOMPANIED_BY_RE = re.compile(r"\baccompanied\s+by\b", re.IGNORECASE)

_CHAIN_RE = re.compile(r"\s*(?:,|;|or|and)\s+(\d{3,4}[A-Za-z]?)\b", re.IGNORECASE)


def _requisite_type_for_marker(marker: str) -> str:
    lower = marker.lower()
    if "prerequisite" in lower and "corequisite" in lower:
        return "PREREQUISITE_OR_COREQUISITE"
    if "corequisite" in lower or "co-requisite" in lower:
        return "COREQUISITE"
    return "PREREQUISITE"


class RequisiteParser:
    """Matches subject-name mentions against a known (subject_code -> id) map.

    `course_lookup` maps (SUBJECT_CODE, "1215") -> course_id, built from the
    narrow-scope catalog so we only resolve mentions to courses that actually
    exist in `courses.json`.
    """

    def __init__(self, subject_codes: list[str], course_lookup: dict[tuple[str, str], int]):
        # Longest-first so multi-word codes (e.g. "COMP SCI") win over any
        # shorter code that happens to be a prefix.
        ordered = sorted(subject_codes, key=len, reverse=True)
        alternation = "|".join(re.escape(code) for code in ordered)
        self._primary_re = re.compile(
            rf"\b({alternation})\.?\s+(\d{{3,4}}[A-Za-z]?)\b", re.IGNORECASE
        )
        self._course_lookup = course_lookup
        self._known_codes = {code.upper() for code in subject_codes}

    def _find_mentions(self, text: str) -> list[tuple[str, str]]:
        mentions: list[tuple[str, str]] = []
        for m in self._primary_re.finditer(text):
            subject_code = re.sub(r"\s+", " ", m.group(1)).strip().upper()
            if subject_code not in self._known_codes:
                continue
            mentions.append((subject_code, m.group(2).upper()))
            idx = m.end()
            while True:
                chain_m = _CHAIN_RE.match(text, idx)
                if not chain_m:
                    break
                mentions.append((subject_code, chain_m.group(1).upper()))
                idx = chain_m.end()
        return mentions

    def _mentions_to_course_ids(self, mentions: list[tuple[str, str]]) -> list[int]:
        course_ids = []
        for subject_code, number in mentions:
            course_id = self._course_lookup.get((subject_code, number))
            if course_id is not None:
                course_ids.append(course_id)
        return course_ids

    def _course_group_node(
        self, course_ids: list[int], operator: str, minimum_grade: str | None, source_text: str
    ) -> RuleNode:
        if len(course_ids) == 1:
            return RuleNode(
                node_type="COURSE",
                required_course_id=course_ids[0],
                minimum_grade=minimum_grade,
                source_text=source_text,
            )
        return RuleNode(
            node_type="GROUP",
            rule_operator=operator,
            source_text=source_text,
            children=[
                RuleNode(node_type="COURSE", required_course_id=cid, minimum_grade=minimum_grade)
                for cid in course_ids
            ],
        )

    def parse_clause(self, requisite_type: str, text: str) -> RuleNode | None:
        """Parse one Prerequisite:/Corequisite: clause into a RuleNode tree."""
        text = text.strip().rstrip(".")
        if not text:
            return None

        if requisite_type == "PREREQUISITE" and _ACCOMPANIED_BY_RE.search(text):
            requisite_type = "COREQUISITE"

        remainder = text
        children: list[RuleNode] = []

        for grade_m in _GRADE_CLAUSE_RE.finditer(text):
            grade, subtext = grade_m.group(1).upper(), grade_m.group(2)
            mentions = self._find_mentions(subtext)
            course_ids = self._mentions_to_course_ids(mentions)
            if course_ids:
                operator = "ANY" if re.search(r"\bor\b", subtext, re.IGNORECASE) else "ALL"
                children.append(
                    self._course_group_node(course_ids, operator, grade, grade_m.group(0))
                )
            remainder = remainder.replace(grade_m.group(0), " ")

        remainder_mentions = self._find_mentions(remainder)
        remainder_course_ids = self._mentions_to_course_ids(remainder_mentions)
        if remainder_course_ids:
            operator = "ANY" if re.search(r"\bor\b", remainder, re.IGNORECASE) else "ALL"
            children.append(self._course_group_node(remainder_course_ids, operator, None, remainder))

        standing_m = _STANDING_RE.search(text)
        if standing_m:
            children.append(
                RuleNode(
                    node_type="STANDING",
                    minimum_standing=standing_m.group(1).upper(),
                    source_text=standing_m.group(0),
                )
            )

        if not children:
            root = RuleNode(node_type="TEXT", text_value=text, source_text=text)
        elif len(children) == 1:
            root = children[0]
        else:
            root = RuleNode(node_type="GROUP", rule_operator="ALL", source_text=text, children=children)

        self._tag_requisite_type(root, requisite_type)
        return root

    @staticmethod
    def _tag_requisite_type(node: RuleNode, requisite_type: str) -> None:
        node.requisite_type = requisite_type
        for child in node.children:
            RequisiteParser._tag_requisite_type(child, requisite_type)

    def parse_description(self, description: str) -> list[RuleNode]:
        """Find every Prerequisite:/Corequisite: block in a course description."""
        lowered = description.lower() if description else ""
        if not any(marker in lowered for marker in ("prerequisite", "corequisite", "co-requisite")):
            return []

        nodes: list[RuleNode] = []
        for marker, block_text in _REQUISITE_BLOCK_RE.findall(description):
            requisite_type = _requisite_type_for_marker(marker)
            # parse_clause may itself upgrade requisite_type (e.g. "Prerequisite:
            # Accompanied by ..." really means COREQUISITE) and tags the whole
            # subtree accordingly -- don't stomp on that here.
            node = self.parse_clause(requisite_type, block_text)
            if node is not None:
                nodes.append(node)
        return nodes

    def referenced_course_ids(self, nodes: list[RuleNode]) -> set[int]:
        found: set[int] = set()

        def walk(node: RuleNode) -> None:
            if node.required_course_id is not None:
                found.add(node.required_course_id)
            for child in node.children:
                walk(child)

        for node in nodes:
            walk(node)
        return found
