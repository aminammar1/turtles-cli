from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PromptScore:
    clarity: int
    specificity: int
    safety: int
    output_quality: int

    @property
    def total(self) -> int:
        return round((self.clarity + self.specificity + self.safety + self.output_quality) / 4)


def enhance_prompt(prompt: str) -> str:
    return "\n".join(
        [
            "Role: Act as a careful developer workflow assistant.",
            "",
            "Goal:",
            prompt.strip() or "Describe the desired outcome clearly.",
            "",
            "Context:",
            "- Project scope only.",
            "- State assumptions before acting.",
            "- Prefer concise, verifiable outputs.",
            "",
            "Output:",
            "- Provide a short plan.",
            "- Execute or recommend concrete next steps.",
            "- Include risks, tests, and follow-up checks.",
        ]
    )


def evaluate_prompt(prompt: str) -> tuple[PromptScore, list[str]]:
    text = prompt.strip()
    words = text.split()
    clarity = 85 if len(words) >= 20 else 55
    specificity = 80 if any(token in text.lower() for token in ["file", "command", "test", "output", "format"]) else 50
    safety = 90 if "secret" not in text.lower() and "credential" not in text.lower() else 60
    output_quality = 85 if any(token in text.lower() for token in ["return", "output", "include", "format"]) else 58
    notes: list[str] = []
    if clarity < 70:
        notes.append("Add more context and define the intended outcome.")
    if specificity < 70:
        notes.append("Name files, constraints, examples, or expected format.")
    if safety < 70:
        notes.append("Clarify how credentials and sensitive data should be handled.")
    if output_quality < 70:
        notes.append("State exactly what the final answer should contain.")
    return PromptScore(clarity, specificity, safety, output_quality), notes


def simulation_grade(prompt: str, code_involved: bool = False) -> dict[str, int | str]:
    score, _ = evaluate_prompt(prompt)
    human_grade = score.total
    ai_grade = min(100, score.total + 4)
    code_grade = 78 if code_involved else 0
    parts = [human_grade, ai_grade] + ([code_grade] if code_involved else [])
    final = round(sum(parts) / len(parts))
    return {
        "human_grade": human_grade,
        "ai_grade": ai_grade,
        "code_grade": code_grade,
        "final_grade": final,
        "warning": "A simulation scenario is only a prompt plus optional context; it is not a real execution.",
    }
