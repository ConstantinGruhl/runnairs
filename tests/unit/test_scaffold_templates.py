from pathlib import Path

from platform_cli.main import render_automation_template


def test_render_automation_template_includes_required_files(tmp_path: Path) -> None:
    rendered = render_automation_template(
        slug="daily-digest",
        display_name="Daily Digest",
        modules=["summary_generation", "email_delivery"],
    )
    assert sorted(rendered) == [
        "AI_INSTRUCTIONS.md",
        "README.md",
        "automation.yaml",
        "main.py",
        "tests/test_agent.py",
    ]
