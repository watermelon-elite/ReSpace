"""Shared advisory layout reference for Gemini reasoning prompts."""
from functools import cache
from pathlib import Path


@cache
def layout_reference():
    path = Path(__file__).resolve().parents[2] / 'prompts' / 'layouts.md'
    if not path.is_file():
        path = Path('prompts/layouts.md')
    return {
        'usage': ('Optional reference: consult relevant guidance only when useful to the current task. '
                  'Task instructions, supplied facts, user choices, hard constraints, stage permissions and response schema take precedence. '
                  'This adds no required questions, tool calls, scoring criteria, validation checks or workflow steps. '
                  'Research statistics are background evidence, not promises of user outcomes.'),
        'content': path.read_text(encoding='utf-8'),
    }
