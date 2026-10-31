"""Narrow explicit-symptom gate; no diagnosis or exercise advice."""
import re
from pathlib import Path
import yaml

RULES = yaml.safe_load((Path(__file__).resolve().parents[1] / "config/red_flags.yaml").read_text())
SAFETY_NOTE = ("See a physio if pain is sharp/stabbing or steadily worsening, occurs at rest or wakes you at night, "
               "lasts over two weeks without improving despite cutting load, or follows a fall/impact; "
               "or if you have swelling, bruising, deformity, a pop, giving way, locking, catching, "
               "numbness, tingling, radiating weakness or limping. Back pain with bladder/bowel changes "
               "or groin numbness needs emergency care.")

# Questions that get the "See a physio if..." line (AGENTS.md rule 3); whole words, so "coach" isn't "ache".
_PAIN_RE = re.compile(
    r"\b(?:pain\w*|ach(?:e|es|ed|ing|y)|sore\w*|stiff\w*|hurts?|hurting|injur\w*|tendons?|"
    r"tendin\w*|tendon\w*|strain\w*|sprain\w*)\b", re.I)


def mentions_pain(question):
    return bool(_PAIN_RE.search(question))


def referral_kind(question):
    # Exclude simple negated symptom lists ("no swelling or bruising").
    # This deliberately handles explicit language, not a clinical diagnosis.
    text = re.sub(
        r"\b(?:no|without|denies?)\s+(?:pain at rest|night pain|back pain|groin numbness|"
        r"(?:bladder|bowel)(?:/bowel)? changes|(?:sharp(?: or stabbing)?|stabbing)\s+pain|swelling|bruising|"
        r"numbness|tingling|limping|locking|catching|giving way)"
        r"(?:\s*(?:,|or|and)\s*(?:swelling|bruising|numbness|tingling|limping|locking|catching|giving way))*",
        "", question, flags=re.I)
    for kind, key in (("urgent", "urgent_patterns"), ("physio", "referral_patterns")):
        if any(re.search(pattern, text, re.I) for pattern in RULES[key]):
            return kind
    if all(re.search(RULES[key], text, re.I) for key in
           ("duration_pattern", "no_improvement_pattern", "cut_load_pattern")):
        return "physio"
    return None
