"""Browser scripts for resolving live LinkedIn choice controls."""

from __future__ import annotations

import json

from pydoll_mcp_server.tools.linkedin_state_scripts import shared_state_helpers_script


def resolve_choice_script(question_contains: str, option_text: str) -> str:
    """Resolve a current radio or checkbox target without caching a stale element."""
    payload = json.dumps({'question_contains': question_contains, 'option_text': option_text})
    return (
        '(() => {\n'
        + shared_state_helpers_script()
        + f"""
  const opts = {payload};
  const surface = findApplicationSurface();
  const root = surface.root && surface.kind !== 'confirmation'
    ? (surface.kind === 'dialog' ? narrowApplicationRoot(surface.root) : surface.root)
    : null;
  if (!root) return {{ success: false, reason: 'surface_not_found' }};
  const match = choiceFindGroup(root, opts.question_contains);
  const describeGroup = (item) => ({{
    label: item.label,
    score: item.score,
    options: item.options.map(choiceOptionText).filter(Boolean),
  }});
  if (!match.group) return {{
    success: false,
    reason: match.reason,
    question_contains: opts.question_contains,
    candidates: match.candidates.map(describeGroup),
  }};
  const choices = choiceOptionMatches(match.group, opts.option_text);
  if (choices.length !== 1) return {{
    success: false,
    reason: choices.length ? 'ambiguous_option' : 'option_not_found',
    question_contains: opts.question_contains,
    matched_label: match.group.label,
    candidates: choices.map((choice) => ({{ label: choiceOptionText(choice), selector: choiceSelectorHint(choice) }})),
  }};
  const target = choices[0];
  return {{
    success: true,
    selected: choiceChecked(target),
    question_contains: opts.question_contains,
    matched_label: match.group.label,
    option_text: choiceOptionText(target),
    selector: choiceSelectorHint(target),
    tag: target.tagName.toLowerCase(),
    role: target.getAttribute('role') || '',
  }};
"""
        + '\n})()'
    )
