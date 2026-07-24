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
function stepProgressFromDom() {
  const candidates = [...document.querySelectorAll(
    '[role="progressbar"], [aria-valuenow][aria-valuemax], [data-test-progress]'
  )].filter((element) => typeof visible !== 'function' || visible(element));
  for (const element of candidates) {
    const index = Number(element.getAttribute('aria-valuenow') || element.getAttribute('data-value') || '0');
    const count = Number(element.getAttribute('aria-valuemax') || element.getAttribute('data-max') || '0');
    if (Number.isInteger(index) && index > 0 && Number.isInteger(count) && count >= index && count <= 20) {
      return { index, count };
    }
  }
  return { index: 0, count: 0 };
}
function stepProgressFromTitle(title) {
  const lower = fold(title);
  if (/contact info|informacoes de contato/.test(lower)) return { index: 1, count: 0 };
  if (/resume|curriculo/.test(lower)) return { index: 2, count: 0 };
  if (/additional questions|perguntas adicionais/.test(lower)) return { index: 3, count: 0 };
  if (/work experience|experiencia profissional/.test(lower)) return { index: 4, count: 0 };
  if (/education|formacao/.test(lower)) return { index: 4, count: 0 };
  if (/revise sua candidatura|review/.test(lower)) return { index: 5, count: 0 };
  return { index: 0, count: 0 };
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
  const labelScore = choiceMatchScore(label, needle);
  const groupScore = choiceMatchScore(group, needle);
  if (labelScore < 0 && groupScore < 0) return -1;
  let score = Math.max(labelScore, groupScore);
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
