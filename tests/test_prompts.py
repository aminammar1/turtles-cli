from turtles_cli.prompts import enhance_prompt, evaluate_prompt, simulation_grade


def test_prompt_eval_scores_prompt() -> None:
    score, notes = evaluate_prompt("Review the file app.py and return findings with tests to run.")

    assert score.total >= 70
    assert isinstance(notes, list)


def test_enhance_prompt_preserves_goal() -> None:
    enhanced = enhance_prompt("Audit Dockerfiles")

    assert "Audit Dockerfiles" in enhanced
    assert "Project scope only" in enhanced


def test_simulation_grade_has_final_score() -> None:
    result = simulation_grade("Create a code review plan", code_involved=True)

    assert "final_grade" in result
    assert result["code_grade"] > 0
