import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import streamlit as st

KB_PATH = Path(__file__).parent / "kb.json"

@dataclass
class FactValue:
    value: Any
    source: str


@dataclass
class UseCase:
    facts: Dict[str, FactValue] = field(default_factory=dict)

    def get(self, key: str) -> Any:
        fv = self.facts.get(key)
        return None if fv is None else fv.value

    def has(self, key: str) -> bool:
        return key in self.facts and self.facts[key].value is not None

    def set(self, key: str, value: Any, source: str = "user") -> None:
        if value is None and key in self.facts:
            return
        self.facts[key] = FactValue(value=value, source=source)

    def as_plain_dict(self) -> Dict[str, Any]:
        return {k: v.value for k, v in self.facts.items() if v.value is not None}

    def provenance(self) -> Dict[str, str]:
        return {k: v.source for k, v in self.facts.items() if v.value is not None}


@dataclass(frozen=True)
class Condition:
    key: str
    equals: Any

    def evaluate(self, uc: UseCase) -> Optional[bool]:
        """True/False if known, None if unknown."""
        if not uc.has(self.key):
            return None
        return uc.get(self.key) == self.equals


@dataclass
class Rule:
    id: str
    priority: int
    conditions: List[Condition]

    asserts: Dict[str, Any] = field(default_factory=dict)

    classification: Optional[str] = None
    explanation: str = ""
    recommended_next_steps: List[str] = field(default_factory=list)

    def specificity(self) -> int:
        return len(self.conditions)

    def status(self, uc: UseCase) -> Tuple[str, Set[str]]:
        """
        Returns (status, missing_keys)
        status ∈ {"satisfied", "contradicted", "undecided"}
        """
        missing: Set[str] = set()
        for c in self.conditions:
            res = c.evaluate(uc)
            if res is None:
                missing.add(c.key)
            elif res is False:
                return "contradicted", set()
        if missing:
            return "undecided", missing
        return "satisfied", set()

    def apply(self, uc: UseCase) -> bool:
        """Apply asserted facts if rule is satisfied. Returns whether anything changed."""
        changed = False
        for k, v in self.asserts.items():
            if not uc.has(k) or uc.get(k) != v:
                uc.set(k, v, source=self.id)
                changed = True
        return changed


def load_kb(path: Path = KB_PATH) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def parse_rules(raw_rules: List[Dict[str, Any]]) -> List[Rule]:
    rules: List[Rule] = []
    for r in raw_rules:
        conds = [Condition(key=k, equals=v) for k, v in r.get("conditions", {}).items()]
        rules.append(
            Rule(
                id=r.get("id", "unknown"),
                priority=int(r.get("priority", 0)),
                conditions=conds,
                asserts=r.get("asserts", {}) or {},
                classification=r.get("classification"),
                explanation=r.get("explanation", ""),
                recommended_next_steps=r.get("recommended_next_steps", []) or [],
            )
        )
    return rules


class InferenceEngine:
    def __init__(self, kb: Dict[str, Any]):
        self.kb = kb
        self.attributes: Dict[str, Any] = kb.get("attributes", {})
        self.derivation_rules = parse_rules(kb.get("derivation_rules", []))
        self.decision_rules = parse_rules(kb.get("rules", []))
        self.default = kb.get("default", {"id": "default", "classification": "needs_review"})

    def forward_chain(self, uc: UseCase, max_iters: int = 20) -> List[str]:
        fired: List[str] = []
        for _ in range(max_iters):
            changed_any = False
            for rule in self.derivation_rules:
                status, _ = rule.status(uc)
                if status == "satisfied":
                    changed = rule.apply(uc)
                    if changed:
                        fired.append(rule.id)
                        changed_any = True
            if not changed_any:
                break
        return fired

    def best_decision(self, uc: UseCase) -> Optional[Rule]:
        best: Optional[Rule] = None
        best_score = (-1, -1)
        for rule in self.decision_rules:
            status, _ = rule.status(uc)
            if status == "satisfied":
                score = (rule.specificity(), rule.priority)
                if score > best_score:
                    best_score = score
                    best = rule
        return best

    def alive_candidates(self, uc: UseCase) -> List[Tuple[Rule, Set[str]]]:
        candidates: List[Tuple[Rule, Set[str]]] = []
        for rule in self.decision_rules:
            status, missing = rule.status(uc)
            if status == "undecided":
                candidates.append((rule, missing))
        candidates.sort(key=lambda rm: (rm[0].priority, rm[0].specificity()), reverse=True)
        return candidates

    def next_question(self, uc: UseCase, asked: Set[str]) -> Optional[str]:
        candidates = self.alive_candidates(uc)
        if not candidates:
            return None

        top = candidates[: min(5, len(candidates))]

        scores: Dict[str, int] = {}
        for rule, missing in top:
            for m in missing:
                if m in asked:
                    continue

                attr_def = self.attributes.get(m)
                if not attr_def:
                    continue

                if "question" not in attr_def:
                    continue
                if attr_def.get("type") == "derived":
                    continue

                scores[m] = scores.get(m, 0) + (10 + rule.priority)

        if not scores:
            return None

        return max(scores.items(), key=lambda kv: kv[1])[0]

    def explain_state(self, uc: UseCase) -> Dict[str, Any]:
        candidates = self.alive_candidates(uc)[:10]
        return {
            "known_facts": uc.as_plain_dict(),
            "provenance": uc.provenance(),
            "top_candidates": [
                {
                    "rule_id": r.id,
                    "priority": r.priority,
                    "specificity": r.specificity(),
                    "missing": sorted(list(missing)),
                    "conditions": {c.key: c.equals for c in r.conditions},
                }
                for r, missing in candidates
            ],
        }


def render_single_question(attr_name: str, attr_def: Dict[str, Any], current: Any) -> Any:
    if "question" not in attr_def:
        st.warning(f"'{attr_name}' is derived and should not be asked.")
        return None

    q_type = attr_def.get("type", "text")
    question = attr_def.get("question", attr_name)

    if q_type == "bool":
        options = ["Not sure", "No", "Yes"]
        if current is True:
            idx = 2
        elif current is False:
            idx = 1
        else:
            idx = 0
        choice = st.radio(question, options, index=idx, horizontal=True)
        if choice == "Not sure":
            return None
        return choice == "Yes"

    if q_type == "choice":
        options = attr_def.get("options", [])
        if not options:
            return st.text_input(question, value="" if current is None else str(current)) or None
        options2 = ["(Not sure)"] + options
        idx = 0 if current is None else (options2.index(current) if current in options2 else 0)
        val = st.selectbox(question, options2, index=idx)
        return None if val == "(Not sure)" else val

    return st.text_input(question, value="" if current is None else str(current)) or None


def show_decision(rule_payload: Dict[str, Any], used_facts: Dict[str, Any]) -> None:
    classification = rule_payload.get("classification", "needs_review")
    explanation = rule_payload.get("explanation", "")
    steps = rule_payload.get("recommended_next_steps", [])
    rule_id = rule_payload.get("id", "unknown")

    st.subheader(f"Risk classification: {classification}")
    if explanation:
        st.write(explanation)

    st.caption(f"Rule applied: {rule_id}")

    if steps:
        st.markdown("### Recommended next steps")
        for step in steps:
            st.markdown(f"- {step}")

    with st.expander("Facts used"):
        st.json(used_facts)


def init_state() -> None:
    if "uc" not in st.session_state:
        st.session_state.uc = UseCase()
    if "asked" not in st.session_state:
        st.session_state.asked = set()
    if "last_decision" not in st.session_state:
        st.session_state.last_decision = None
    if "trace" not in st.session_state:
        st.session_state.trace = {}


def reset_all() -> None:
    st.session_state.uc = UseCase()
    st.session_state.asked = set()
    st.session_state.last_decision = None
    st.session_state.trace = {}


def app() -> None:
    st.set_page_config(page_title="GenAI Use Case Risk Advisor", layout="centered")

    st.title("GenAI Use Case Risk Advisor")
    st.write("This version asks only what it needs, using inference (goal-driven questioning).")

    kb = load_kb()
    engine = InferenceEngine(kb)

    init_state()
    uc: UseCase = st.session_state.uc

    # 1) Forward chaining to derive any implied facts (optional but scalable)
    fired = engine.forward_chain(uc)

    # 2) Check if we can already decide
    best = engine.best_decision(uc)
    if best:
        st.session_state.last_decision = {
            "id": best.id,
            "classification": best.classification,
            "explanation": best.explanation,
            "recommended_next_steps": best.recommended_next_steps,
        }

    c1, c2 = st.columns([1, 2])
    with c1:
        st.button("Reset", on_click=reset_all)
    with c2:
        if fired:
            st.caption(f"Derived facts updated by: {', '.join(fired[:3])}" + (" …" if len(fired) > 3 else ""))

    if st.session_state.last_decision is not None:
        st.divider()
        show_decision(st.session_state.last_decision, uc.as_plain_dict())
        return

    next_attr = engine.next_question(uc, asked=st.session_state.asked)

    if next_attr is None:
        st.divider()
        show_decision(engine.default, uc.as_plain_dict())
        return

    st.subheader("Next question")
    attr_def = engine.attributes.get(next_attr, {})
    current = uc.get(next_attr)

    with st.form("answer_form", clear_on_submit=False):
        answer = render_single_question(next_attr, attr_def, current=current)
        submitted = st.form_submit_button("Submit")

    if submitted:
        st.session_state.asked.add(next_attr)
        uc.set(next_attr, answer, source="user")
        st.rerun()


if __name__ == "__main__":
    app()
