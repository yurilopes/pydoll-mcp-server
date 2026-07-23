"""Browser-side helpers for LinkedIn form progress, matching, and review text."""

from __future__ import annotations


def form_state_helpers_script() -> str:
    """Return helpers shared by Easy Apply snapshots and question actions."""
    return r"""
function stepProgressFor(text) {
  const match = fold(text).match(/(\d+)\s+(?:de|of)\s+(\d+)\s+(?:paginas?|etapas?|pages?|steps?)/i)
    || fold(text).match(/step\s+(\d+)\s+of\s+(\d+)/i);
  return match ? { index: Number(match[1]), count: Number(match[2]) } : { index: 0, count: 0 };
}
function questionText(value) {
  return fold(value).replace(/[^a-z0-9]+/g, ' ').trim();
}
function containsQuestionPhrase(value, needle) {
  const haystack = ` ${questionText(value)} `;
  return haystack.includes(` ${needle} `) || haystack.includes(needle);
}
function questionMatchScore(item, needle, answer) {
  const label = questionText(item.field.label);
  const group = questionText(item.field.group_text);
  if (!containsQuestionPhrase(label, needle) && !containsQuestionPhrase(group, needle)) return -1;
  let score = 0;
  if (label === needle) score += 100;
  else if (containsQuestionPhrase(label, needle)) score += 70;
  else score += 35;
  if (answer.value !== undefined && answer.value !== null && /^-?\d+(?:\.\d+)?$/.test(String(answer.value))) {
    if (/how many|years? of|experience/.test(label)) score += 25;
  }
  if (answer.option_text && /yes|no|citizen|sponsorship|w2|1099|c2c/.test(label)) score += 10;
  return score;
}
function reviewAnswersFor(text) {
  const lines = String(text || '').split(/\n+/).map(norm).filter(Boolean);
  const answers = [];
  const ignored = /^(editar|edit|voltar|back|avancar|next|avaliar|review|enviar candidatura|submit application)$/i;
  for (let index = 0; index < lines.length - 1; index += 1) {
    const question = lines[index];
    const answer = lines[index + 1];
    const answerPattern = new RegExp(
      'years?|experiencia|experience|citizen|sponsorship|authorization|w2|1099|c2c|azure|python|automation', 'i'
    );
    if (ignored.test(question) || ignored.test(answer) || /\.(?:pdf|docx?)$/i.test(answer)) continue;
    if (!/[?]/.test(question) && !answerPattern.test(question)) continue;
    answers.push({ question, answer });
    index += 1;
  }
  return answers;
}
"""
