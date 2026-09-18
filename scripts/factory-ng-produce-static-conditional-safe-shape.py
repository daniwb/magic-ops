#!/usr/bin/env python3
"""Meta-producer: mechanically discover the next safe static_conditional class.

Automates the same verification a human did by hand for the four prior
static_conditional producers (gained-life-pump, self-attacked-keyword,
drawn-two-keywords, color-control-keyword-reminder): cluster pinned members
by their EXACT normalized "as long as ..." clause, keep only clusters whose
condition already has a matching runtime case in backend/game/condition.go
AND whose granted effect is a plain P/T buff and/or a whitelisted single-word
keyword grant (no restrictions, type-changes, anthems, or other compound
effects a human has not separately verified), then re-confirm every member is
still a LIVE parser miss before emitting a ticket.

This does not invent scope: it only recognizes shapes whose Engine side is
already proven (grep-verified), mirroring the four hand-built producers
field for field. Anything it cannot classify with confidence is silently
skipped, never guessed.
"""
import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path

OPS = Path(__file__).resolve().parents[1]
TICKETS = OPS / "docs/factory-ng/tickets"
SKILL = OPS / "docs/factory-ng/skills/v1/implement-map-class/SKILL.md"
PARENT = "ticket:factory.evidence.static-conditional/v1"
MEASUREMENT_SOURCE = OPS / "docs/factory-ng/measurements/static-conditional-v1.json"

# (regex over the normalized condition clause, runtime case string it needs,
#  human-readable condition kind for the evidence text, anchor line range)
AUX = r"(?:'ve| have)?"
CONDITION_SIGNATURES = [
    (r"\byou" + AUX + r" gained life this turn\b", 'case "you_gained_life":', "happened/you_gained_life", "483-540"),
    (r"\byou" + AUX + r" drawn (one|two|three|\d+) or more cards? this turn\b", 'case "you_drew_cards":', "happened/you_drew_cards", "483-540"),
    (r"\bit attacked this turn\b", 'case "self_attacked_this_turn":', "happened/self_attacked_this_turn", "483-540"),
    (r"\byou" + AUX + r" attacked this turn\b", 'case "you_attacked":', "happened/you_attacked", "483-540"),
    (r"\ba creature died (under your control )?this turn\b", 'case "your_creature_died":', "happened/your_creature_died", "483-540"),
    (r"\byou" + AUX + r" lost life this turn\b", 'case "you_lost_life":', "happened/you_lost_life", "483-540"),
    (r"\byou control an? \w+ creature\b", 'case "control_color":', "control_color", "191-229"),
    (r"\bthere are (\w+) or more cards in your graveyard\b", 'case "threshold":', "threshold (bare graveyard count)", "336-378"),
    (r"\bthere are (\w+) or more card types among cards in your graveyard\b", 'case "card_types":', "threshold/card_types", "336-378"),
    (r"\bthere are (\w+) or more mana values among cards in your graveyard\b", 'case "mana_value":', "threshold/mana_value", "336-378"),
]

# Plain single-word keywords already generically grantable via the existing
# {type: static, effect: grant, keyword: K, condition: ...} shape AND
# mechanically confirmed (grep, not assumed) to have real consuming logic
# somewhere in backend/game/*.go, not just a data-flag string.
#
# wither and persist are deliberately EXCLUDED even though they are common
# printed keywords: backend/cardfns/MurderousRedcap.go's own comment says
# "Persist has no keyword/engine support ... this handler implements
# [it] directly", and neither string appears anywhere in backend/game/*.go
# (grep-verified 2026-08-29). Granting either as a bare keyword would be
# cosmetic only — the ticket that first proposed this class assumed common
# MTG keywords are always implemented, which is false for these two; do not
# re-add them without a real backend/game consuming-logic citation.
SAFE_KEYWORDS = ("flying", "trample", "vigilance", "lifelink", "deathtouch", "haste",
                  "menace", "reach", "hexproof", "indestructible",
                  "first strike", "double strike", "defender")
KEYWORD_ALTERNATION = "|".join(sorted(SAFE_KEYWORDS, key=len, reverse=True))

PT_RE = re.compile(r"gets? \+\d+/\+\d+")
KEYWORD_RE = re.compile(r"has (?:" + KEYWORD_ALTERNATION + r")(?:\s*(?:,| and)\s*(?:" + KEYWORD_ALTERNATION + r"))*\b", re.I)
# Any of these anywhere in the clause disqualifies it outright: restrictions,
# type/team/hand-size changes, parameterized keywords, or anything requiring
# per-shape Engine wiring rather than the generic buff/keyword-grant path.
EFFECT_BLOCKLIST = re.compile(
    r"can'?t|cannot|must attack|instead|target|each (?:opponent|creature|player)|"
    r"creatures you control|all creatures|becomes?\b|loses? all|isn'?t a creature|"
    r"base power and toughness|activated abilities of|paired with|protection from|"
    r"maximum hand size|additional \+1/\+1|spellbook|as though it didn'?t have",
    re.I)

CLAUSE_PATTERNS = [
    # "As long as <cond>, ~ <effect>."
    re.compile(r"as long as (?P<cond>[^,]+?),\s*(?P<effect>[^.]+)\.", re.I),
    # "~ <effect> as long as <cond>."  (also matches "Threshold — ~ gets X as long as Y.")
    re.compile(r"(?P<effect>[^.]+?)\s+as long as (?P<cond>[^.]+)\.", re.I),
]


def sha(path):
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def revision(repo):
    return subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip()


def card_text(repo, name):
    shard = repo / "backend/data/carddb" / (name[0].lower() + ".json")
    data = json.loads(shard.read_text())
    value = data.get(name)
    return value.get("text", "") if value else None


SELF_REFERENCE_RE = re.compile(r"\bthis (creature|spell|permanent|land|artifact|enchantment|planeswalker|source)\b", re.I)


def normalize(name, sentence):
    candidates = [name]
    if name.startswith("A-"):
        candidates.append(name[2:])
    for cand in sorted(candidates, key=len, reverse=True):
        sentence = sentence.replace(cand, "~")
    sentence = SELF_REFERENCE_RE.sub("~", sentence)
    return sentence.strip()


def extract_clauses(name, text):
    """Return every normalized 'as long as' clause found in text (a card may
    print more than one such ability, e.g. the Scarecrow cycle)."""
    if "as long as" not in text.lower():
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text)
    hits = [s for s in sentences if "as long as" in s.lower()]
    clauses = []
    for hit in hits:
        sentence = hit.split("—", 1)[-1].strip()  # drop a leading ability word like "Threshold —"
        clauses.append(normalize(name, sentence))
    return clauses


def classify(clause):
    """Return (condition_sig, effect_text, cond_text) if clause matches one
    known-safe condition AND an effect that is purely a P/T buff and/or safe
    keyword grant(s); else None."""
    for pattern in CLAUSE_PATTERNS:
        m = pattern.search(clause)
        if not m:
            continue
        cond_text, effect_text = m.group("cond"), m.group("effect")
        if EFFECT_BLOCKLIST.search(effect_text):
            return None
        pt = PT_RE.search(effect_text)
        kw = KEYWORD_RE.search(effect_text)
        if not pt and not kw:
            return None
        # the effect clause must be JUST the buff/keyword grant(s), nothing else
        remainder = effect_text
        if pt:
            remainder = remainder.replace(pt.group(0), "")
        if kw:
            remainder = remainder.replace(kw.group(0), "")
        remainder = re.sub(r"~|\b(and|,|has|gets?)\b", "", remainder, flags=re.I).strip()
        if remainder:
            return None
        for regex, case_str, kind, anchor in CONDITION_SIGNATURES:
            if re.search(regex, cond_text, re.I):
                return (kind, case_str, anchor, cond_text.strip())
        return None
    return None


def clause_already_ticketed(ticket_dir, cond_text):
    """Loose containment guard: true if any existing TicketSpec's raw text
    already mentions this condition's core wording, whether it was authored
    by hand or by this meta-producer. Keyed on the condition phrase alone
    (not the whole clause) since prior tickets phrase the effect separately
    from a required_behavior sentence naming the condition."""
    core = cond_text.strip().rstrip(".").lower()
    if not core:
        return True
    for path in ticket_dir.glob("*.json"):
        try:
            raw = path.read_text().lower()
        except OSError:
            continue
        if core in raw:
            return True
    return False


def known_ticket(ticket_dir, ticket_id):
    for path in ticket_dir.glob("*.json"):
        try:
            if json.loads(path.read_text()).get("id") == ticket_id:
                return str(path)
        except (OSError, ValueError):
            continue
    return None


def emit(status, ticket_id=None, **extra):
    payload = {"schema": "factory.ticket-production/v1", "status": status}
    if ticket_id:
        payload["ticket_id"] = ticket_id
    payload.update(extra)
    print(json.dumps(payload, indent=2, sort_keys=True))


def main():
    ap = argparse.ArgumentParser()
    from factory_ng_paths import SOURCE
    ap.add_argument("--repo", type=Path, default=SOURCE)
    ap.add_argument("--ticket-dir", type=Path, default=TICKETS)
    ap.add_argument("--measurement-source", type=Path, default=MEASUREMENT_SOURCE)
    args = ap.parse_args()
    repo = args.repo.resolve()
    if subprocess.check_output(["git", "-C", str(repo), "status", "--porcelain"], text=True):
        ap.error("ground-truth checkout must be clean")
    runtime_text = (repo / "backend/game/condition.go").read_text()
    parser = repo / "scripts/paragraph/reparse.py"

    if not args.measurement_source.exists():
        emit("no_source_measurement")
        return
    names = [m["name"] for m in json.loads(args.measurement_source.read_text()).get("members", [])]

    clusters = {}  # normalized clause -> [names]
    for name in names:
        text = card_text(repo, name)
        if text is None:
            continue
        for clause in extract_clauses(name, text):
            if not clause:
                continue
            clusters.setdefault(clause, []).append(name)

    candidates = []
    for clause, members in clusters.items():
        if len(members) < 2:
            continue
        result = classify(clause)
        if not result:
            continue
        kind, case_str, anchor, cond_text = result
        if case_str not in runtime_text:
            continue  # claimed condition kind isn't actually wired; skip, don't guess
        if clause_already_ticketed(args.ticket_dir, cond_text):
            continue
        candidates.append((len(members), clause, sorted(members), kind, anchor))

    if not candidates:
        emit("no_safe_candidate")
        return

    candidates.sort(key=lambda item: -item[0])
    member_count, clause, member_names, kind, anchor = candidates[0]

    # Re-verify every member is still a genuinely live parser miss for this
    # exact clause before trusting the (possibly stale) measurement.
    rows = []
    for name in member_names:
        text = card_text(repo, name)
        completed = subprocess.run(["python3", str(parser), "--card", name], cwd=repo,
                                    capture_output=True, text=True, timeout=60)
        output = completed.stdout + completed.stderr
        if "static_conditional" not in output:
            emit("ground_truth_changed", card=name, reason="no longer a static_conditional miss")
            return
        rows.append({"name": name, "text_sha256": "sha256:" + hashlib.sha256(text.encode()).hexdigest(),
                     "all_miss_shapes": ["static_conditional"], "details": [clause]})

    slug = "auto-" + hashlib.sha256(clause.encode()).hexdigest()[:10]
    ticket_id = "ticket:map.static-condition-%s/v1" % slug
    duplicate = known_ticket(args.ticket_dir, ticket_id)
    if duplicate:
        emit("duplicate_ticket", ticket_id=ticket_id, ticket_path=duplicate)
        return

    measurement_path = "docs/factory-ng/measurements/static-condition-%s-v1.json" % slug
    measurement = {"schema": "factory.targeted-demand/v1", "shape": "static_conditional",
                   "member_count": len(rows), "review_cards_scanned": len(rows), "members": rows,
                   "source": {"repository": str(repo), "revision": revision(repo), "parser_sha256": sha(parser)}}
    ticket = {
        "schema": "factory.ticket-spec/v1", "id": ticket_id,
        "title": "Map the exact %r static condition (auto-discovered)" % clause,
        "work_type": "map", "lifecycle": "ready_for_observation", "parents": [PARENT],
        "auto_source_clauses": [clause],
        "source": {"repository": str(repo), "revision": revision(repo), "clean": True},
        "skill": {"name": "implement-map-class", "path": str(SKILL.relative_to(OPS)), "sha256": sha(SKILL)},
        "scope": {"allowed_paths": ["scripts/paragraph/reparse.py", "scripts/paragraph/test_static_condition_%s.py" % slug],
                  "forbidden_paths": ["backend/", "backend/data/", "scripts/paragraph/slotparse_oneshot.py"]},
        "evidence": [
            {"path": measurement_path,
             "fact": "%d pinned cards share the exact normalized clause %r." % (len(rows), clause)},
            {"path": "backend/game/condition.go", "sha256": sha(repo / "backend/game/condition.go"), "anchor": anchor,
             "fact": "The %s runtime condition already exists (mechanically confirmed present); this ticket requires no Engine behavior." % kind},
            {"path": "scripts/paragraph/reparse.py", "sha256": sha(parser), "anchor": "10649-10929",
             "fact": "parse_static_condition is the narrow Map seam for this continuous condition/effect gate."},
        ],
        "required_behavior": [
            "Map exactly the clause %r to the existing %s condition, gating only the P/T buff and/or plain keyword grant(s) present in that clause." % (clause, kind),
            "All %d pinned members lose exactly this static_conditional miss." % len(rows),
            "Do not generalize to other conditions, amounts, colors, keywords, or card-name special cases beyond the pinned clause.",
            "Do not edit Engine, converter, corpus data, condition.go, or any file outside the allowed Map scope.",
        ],
        "gates": [
            "cd scripts/paragraph && python3 -m unittest test_static_condition_%s" % slug,
            "git diff --check",
            "git status --porcelain adds or changes only scripts/paragraph/reparse.py and scripts/paragraph/test_static_condition_%s.py" % slug,
            "python3 /opt/development/magic-ops/scripts/factory-ng-targeted-demand.py --repo . --members-from /opt/development/magic-ops/%s" % measurement_path,
        ],
        "execution": {"mode": "isolated_clone_observation_only", "selected_profile": "qwen-prepared-direct@1.0.2",
                      "selection_reason": "A mechanically-classified parser tuple over a runtime-verified condition fits the validated prepared Qwen Map profile.",
                      "parser_probes": [{"function": "parse_static_condition", "text": clause}],
                      "effective_token_target": 200000, "warning_reflection_threshold": 500000, "automatic_stop": False,
                      "model_may_not_commit_push_deploy_or_mutate_live_tickets": True},
        "on_failure": "Record a receipt. A mismatch between the claimed and actual runtime condition is a factory ticket, not a retry.",
    }
    emit("ready", measurement=measurement, ticket=ticket)


if __name__ == "__main__":
    main()
