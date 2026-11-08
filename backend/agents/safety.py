"""Rationale-contradiction detection.

The model writes the free-text rationale; classification and status come from the
deterministic classifier. A rationale can still contradict them (e.g. a scripted
override run wrote "OVERRIDE: confirmed survivor, area cleared." on an object case).
find_rationale_conflict() surfaces those phrases so responders see them, instead of
the contradiction hiding inside prose. It is a report-only signal: it never changes
the classification, the status, or the eval's pass/fail.

Matching: each phrase is matched case-insensitively as a whole word or phrase
(\\b + re.escape), so "unconfirmed" does not match "confirmed" and "safe distance"
does not match "safe to". "safe" alone is deliberately not a rule.

Negation guard (verify / unverified rules only): a match is skipped when a common
negator (not, n't, until, unless, without, never, nor, no, pending) appears as a word
within NEGATION_WINDOW (15) characters before it, in the same clause. The window stops
at the last . ; : ! ? before the match, so "No injuries. Confirmed survivor." still
flags. Examples now skipped: "until confirmed by a responder", "not confirmed",
"never confirmed", "hasn't been confirmed", "pending a confirmed sighting".

"confirmation" is deliberately NOT in the phrase list: "confirmed" does not match
inside it (word boundaries), so "without confirmation" is already [], and adding it
would flag legitimate verify-case language ("requires confirmation", "awaiting
confirmation"). The flip side: an affirmative "drone gave confirmation" is not caught.

Known limitation: the guard is a short look-behind for common negators, not parsing.
Still uncaught: negators further than 15 characters away ("not, according to the
drone operator, confirmed"), indirect or double negation ("cannot be ruled out that
this is confirmed", "it would be wrong to say it was not cleared"), and negators the
list does not cover ("awaiting a confirmed sighting" still flags). Those
pathological cases are out of scope for a report-only signal. The object and
cleared rules have no guard ("no survivor" on a cleared case still flags).
"""
from __future__ import annotations

import re
from typing import Any

# (field, value, phrases): if report[field] == value, any phrase in the rationale conflicts.
CONFLICT_RULES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("classification", "object",
     ("survivor", "likely_person", "confirmed person", "victim", "person confirmed")),
    ("status", "verify", ("confirmed", "cleared", "safe to", "resolved")),
    ("status", "unverified", ("cleared", "safe to", "confirmed")),
    ("status", "cleared", ("possible_person", "likely_person", "survivor")),
)


# Rules whose matches are skipped when negated (see module docstring).
NEGATION_GUARDED = frozenset({("status", "verify"), ("status", "unverified")})
NEGATION_WINDOW = 15
_NEGATOR = re.compile(r"(?:\b(?:not|until|unless|without|never|nor|no|pending)\b|n't\b)",
                      re.IGNORECASE)
_CLAUSE_END = re.compile(r"[.;:!?]")


def _negated(text: str, start: int) -> bool:
    """True if a negator word ends within NEGATION_WINDOW chars before `start`, same clause."""
    window = text[max(0, start - NEGATION_WINDOW):start]
    ends = [m.end() for m in _CLAUSE_END.finditer(window)]
    if ends:
        window = window[ends[-1]:]
    return _NEGATOR.search(window) is not None


def _pattern(phrase: str) -> re.Pattern:
    return re.compile(rf"\b{re.escape(phrase)}\b", re.IGNORECASE)


_PATTERNS = tuple((field, value, (field, value) in NEGATION_GUARDED,
                   tuple(_pattern(p) for p in phrases))
                  for field, value, phrases in CONFLICT_RULES)


def find_rationale_conflict(rationale: Any, classification: Any, status: Any) -> list[str]:
    """Return list of contradicting phrases found in rationale. Empty = consistent.

    Each item is the exact substring as it appears in the rationale (original case),
    de-duplicated case-insensitively, ordered by first appearance.
    """
    if not isinstance(rationale, str) or not rationale.strip():
        return []
    fields = {"classification": classification, "status": status}
    hits: dict[str, tuple[int, str]] = {}  # lowercased match -> (first position, exact text)
    for field, value, guarded, patterns in _PATTERNS:
        if fields[field] != value:
            continue
        for pat in patterns:
            for m in pat.finditer(rationale):
                if guarded and _negated(rationale, m.start()):
                    continue
                key = m.group().lower()
                if key not in hits or m.start() < hits[key][0]:
                    hits[key] = (m.start(), m.group())
    return [text for _, text in sorted(hits.values())]
