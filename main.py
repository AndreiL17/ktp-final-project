import json
from pathlib import Path


def load_kb(path: str) -> dict:
    kb_path = Path(path)
    if not kb_path.exists():
        raise FileNotFoundError(f"Knowledge base not found at: {kb_path}")
    with kb_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def ask_attribute(attr_name: str, attr_def: dict):
    q_type = attr_def.get("type", "text")
    question = attr_def.get("question", f"Enter value for {attr_name}: ")

    while True:
        answer = input(question).strip().lower()

        if q_type == "bool":
            if answer in ("y", "yes"):
                return True
            if answer in ("n", "no"):
                return False
            print("Please answer with 'y' or 'n'.")
        elif q_type == "choice":
            options = attr_def.get("options", [])
            if answer in options:
                return answer
            print(f"Please choose one of: {', '.join(options)}")
        else:
            # Default: free text
            return answer


def collect_facts(kb: dict) -> dict:
    facts = {}
    attributes = kb.get("attributes", {})
    print("\n--- GenAI Use-Case Assessment ---\n")
    for name, definition in attributes.items():
        value = ask_attribute(name, definition)
        facts[name] = value
    return facts


def rule_matches(rule: dict, facts: dict) -> bool:
    conditions = rule.get("conditions", {})
    for attr, expected in conditions.items():
        if facts.get(attr) != expected:
            return False
    return True


def find_best_rule(kb: dict, facts: dict) -> dict:
    rules = kb.get("rules", [])
    for rule in rules:
        if rule_matches(rule, facts):
            return rule
    return kb.get("default", {})


def print_decision(rule: dict, facts: dict):
    classification = rule.get("classification", "unknown")
    explanation = rule.get("explanation", "No explanation available.")
    steps = rule.get("recommended_next_steps", [])

    print("\n--- Assessment Result ---")
    print(f"Classification: {classification}")
    print(f"Explanation: {explanation}")
    print("\nRecommended next steps:")
    if steps:
        for i, step in enumerate(steps, start=1):
            print(f"  {i}. {step}")
    else:
        print("  (No specific next steps in this rule.)")

    print("\nFacts used for this decision:")
    for k, v in facts.items():
        print(f"  - {k}: {v}")


def main():
    kb = load_kb("kb.json")
    facts = collect_facts(kb)
    rule = find_best_rule(kb, facts)
    print_decision(rule, facts)


if __name__ == "__main__":
    main()
