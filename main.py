import json
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

import streamlit as st

KB_PATH = Path(__file__).parent / "kb.json"


def load_kb(path: Path = KB_PATH) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def build_front(attributes: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    facts: Dict[str, Any] = {}

    with st.form(key="use_case_form"):
        for attr_name, attr_def in attributes.items():
            q_type = attr_def.get("type", "text")
            question = attr_def.get("question", attr_name)
            key = f"attr_{attr_name}"

            if q_type == "bool":
                choice = st.radio(question, ["No", "Yes"], key=key, horizontal=True)
                facts[attr_name] = (choice == "Yes")

            elif q_type == "choice":
                options = attr_def.get("options", [])
                if not options:
                    facts[attr_name] = st.text_input(question, key=key)
                else:
                    facts[attr_name] = st.selectbox(question, options, key=key)

            else:
                facts[attr_name] = st.text_input(question, key=key)

        submitted = st.form_submit_button("Evaluate use case")

    return facts if submitted else None


def rule_matches(conditions: Dict[str, Any], facts: Dict[str, Any]) -> bool:
    return all(facts.get(attr) == value for attr, value in conditions.items())


def score_rule(rule: Dict[str, Any]) -> Tuple[int, int]:
    """
    Scoring: (specificity, priority)
    - specificity: number of conditions (more conditions = more specific)
    - priority: optional tie-breaker (higher wins)
    """
    conditions = rule.get("conditions", {})
    specificity = len(conditions)
    priority = int(rule.get("priority", 0))
    return specificity, priority


def find_best_rule(kb: Dict[str, Any], facts: Dict[str, Any]) -> Dict[str, Any]:
    rules = kb.get("rules", [])
    best_rule: Optional[Dict[str, Any]] = None
    best_score = (-1, -1)

    for rule in rules:
        conditions = rule.get("conditions", {})
        if rule_matches(conditions, facts):
            s = score_rule(rule)
            if s > best_score:
                best_score = s
                best_rule = rule

    if best_rule is None:
        return kb.get("default", {"id": "default", "classification": "needs_review"})

    return best_rule


def show_decision(rule: Dict[str, Any], facts: Dict[str, Any]) -> None:
    classification = rule.get("classification", "needs_review")
    explanation = rule.get("explanation", "")
    steps = rule.get("recommended_next_steps", [])
    rule_id = rule.get("id", "unknown")

    st.subheader(f"Risk classification: {classification}")
    if explanation:
        st.write(explanation)

    st.caption(f"Rule applied: {rule_id}")

    if steps:
        st.markdown("### Recommended next steps")
        for step in steps:
            st.markdown(f"- {step}")

    with st.expander("Facts used for this decision"):
        st.json(facts)


def app() -> None:
    st.set_page_config(page_title="GenAI Use Case Risk Advisor", layout="centered")
    st.title("GenAI Use Case Risk Advisor")
    st.write(
        "Answer the questions below to receive a rule-based risk classification and recommended next steps."
    )

    kb = load_kb()
    attributes = kb.get("attributes", {})

    facts = build_front(attributes)
    if facts is not None:
        rule = find_best_rule(kb, facts)
        show_decision(rule, facts)


if __name__ == "__main__":
    app()
