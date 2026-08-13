"""Shared browser-side discovery helpers for radio and checkbox groups."""

from __future__ import annotations


def choice_group_helpers_script() -> str:
    """Return JavaScript helpers for controls with native or ARIA choice semantics."""
    return r"""
function choiceFold(value) {
  return String(value ?? '').normalize('NFC').replace(/\s+/g, ' ').trim().toLocaleLowerCase();
}
function choiceVisible(el) {
  if (!el || !el.isConnected) return false;
  const rect = el.getBoundingClientRect();
  const style = getComputedStyle(el);
  return rect.width > 0 && rect.height > 0
    && style.display !== 'none' && style.visibility !== 'hidden'
    && parseFloat(style.opacity || '1') > 0;
}
function choiceType(el) {
  const type = (el.getAttribute('type') || '').toLowerCase();
  const role = (el.getAttribute('role') || '').toLowerCase();
  if (type === 'radio' || type === 'checkbox') return type;
  if (role === 'radio' || role === 'checkbox') return role;
  if (role === 'switch' || el.getAttribute('aria-pressed') !== null
      || el.getAttribute('aria-checked') !== null) return 'checkbox';
  if (choiceButtonGroup(el)) return 'radio';
  return '';
}
function choiceOptionSelector() {
  return 'input[type="radio"], input[type="checkbox"], [role="radio"], [role="checkbox"], '
    + '[role="switch"], button[aria-pressed], button[aria-checked], '
    + '[data-field-path] button, .yesno button, .choice-group button, '
    + '.radio-group button, .checkbox-group button';
}
function choiceButtonGroup(el) {
  if (!el || el.tagName !== 'BUTTON') return null;
  const group = el.closest('[data-field-path], .yesno, .choice-group, .radio-group, .checkbox-group');
  if (!group) return null;
  const buttons = [...group.querySelectorAll('button')];
  const inputs = [...group.querySelectorAll('input[type="radio"], input[type="checkbox"]')];
  return buttons.length >= 2 && inputs.length ? group : null;
}
function choiceOptionElements(group) {
  return [...group.querySelectorAll(choiceOptionSelector())]
    .filter((el) => Boolean(choiceType(el)));
}
function choiceText(value) {
  return String(value || '').replace(/\s+/g, ' ').trim();
}
function choiceOptionText(el) {
  if (!el) return '';
  if (el.id) {
    const explicit = document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
    if (explicit) return choiceText(explicit.innerText || explicit.textContent || '');
  }
  const label = el.closest('label');
  if (label) return choiceText(label.innerText || label.textContent || '');
  const aria = choiceText(el.getAttribute('aria-label') || '');
  if (aria) return aria;
  const ownText = choiceText(el.innerText || el.textContent || '');
  if (ownText && ownText.length <= 120) return ownText;
  for (const sibling of [el.previousElementSibling, el.nextElementSibling]) {
    const text = choiceText(sibling?.innerText || sibling?.textContent || '');
    if (text && text.length <= 120) return text;
  }
  return choiceText(el.value || '');
}
function choiceGroupFor(el, root) {
  const grouped = el.closest(
    'fieldset, [role="radiogroup"], [role="group"], ' +
    '[data-field-path], .form-group, .yesno, .choice-group, .radio-group, .checkbox-group, ' +
    '.jobs-easy-apply-form-section__grouping'
  );
  if (grouped && root.contains(grouped)) return grouped;
  const name = choiceText(el.getAttribute('name') || '');
  if (name) {
    const sameName = [...root.querySelectorAll(choiceOptionSelector())]
      .filter((candidate) => choiceType(candidate) === choiceType(el)
        && choiceText(candidate.getAttribute('name') || '') === name);
    if (sameName.length > 1) return sameName[0].parentElement || root;
  }
  return el.parentElement || root;
}
function choiceCandidateText(node) {
  if (!node || node.matches('input, textarea, select, button')) return '';
  return choiceText(node.innerText || node.textContent || '');
}
function choiceQuestionText(group, root) {
  const labelledBy = (group.getAttribute('aria-labelledby') || '').split(/\s+/)
    .filter(Boolean).map((id) => document.getElementById(id)?.innerText || '')
    .map(choiceText).filter(Boolean);
  if (labelledBy.length) return labelledBy.join(' ');
  const direct = [...group.children].find((node) =>
    node.matches('legend, label, h1, h2, h3, h4, [role="heading"]')
  );
  if (direct) return choiceCandidateText(direct);
  const aria = choiceText(group.getAttribute('aria-label') || '');
  if (aria) return aria;
  let sibling = group.previousElementSibling;
  for (let index = 0; sibling && index < 4; index += 1, sibling = sibling.previousElementSibling) {
    const text = choiceCandidateText(sibling);
    if (text && text.length >= 4) return text;
  }
  const parent = group.parentElement;
  if (parent) {
    const before = [...parent.children].slice(0, [...parent.children].indexOf(group)).reverse();
    for (const node of before.slice(0, 4)) {
      const text = choiceCandidateText(node);
      if (text && text.length >= 4) return text;
    }
  }
  const options = choiceOptionElements(group).map(choiceOptionText).filter(Boolean);
  const lines = String(group.innerText || group.textContent || '').split(/\n+/)
    .map(choiceText).filter(Boolean)
    .filter((line) => !options.some((option) => choiceFold(option) === choiceFold(line)));
  return lines.join(' ');
}
function choiceGroupsFor(root) {
  const map = new Map();
  const controls = [...root.querySelectorAll(choiceOptionSelector())]
    .filter((el) => Boolean(choiceType(el)));
  for (const control of controls) {
    const group = choiceGroupFor(control, root);
    const entries = map.get(group) || [];
    entries.push(control);
    map.set(group, entries);
  }
  return [...map.entries()].map(([group, options]) => {
    const renderedButtons = options.filter((option) =>
      option.tagName === 'BUTTON' && choiceButtonGroup(option)
    );
    const source = renderedButtons.length >= 2 ? renderedButtons : options;
    const unique = [];
    const seen = new Set();
    for (const option of source) {
      const key = `${choiceSelectorHint(option)}|${choiceOptionText(option)}`;
      if (seen.has(key)) continue;
      seen.add(key);
      unique.push(option);
    }
    return {
      group,
      options: unique,
      label: choiceQuestionText(group, root),
    };
  });
}
function choiceContainsPhrase(text, needle) {
  const haystack = ` ${choiceFold(text)} `;
  const query = choiceFold(needle);
  return Boolean(query) && (haystack.includes(` ${query} `) || haystack.includes(query));
}
function choiceMatchScore(label, needle) {
  const question = choiceFold(label);
  const query = choiceFold(needle);
  if (!question || !query || !choiceContainsPhrase(question, query)) return -1;
  if (question === query) return 1000;
  if (` ${question} `.includes(` ${query} `)) return 700;
  return 400;
}
function choiceFindGroup(root, needle) {
  const candidates = choiceGroupsFor(root)
    .map((item) => ({ ...item, score: choiceMatchScore(item.label, needle) }))
    .filter((item) => item.score >= 0)
    .sort((left, right) => right.score - left.score);
  if (!candidates.length) return { group: null, candidates: [], reason: 'no_match' };
  const bestScore = candidates[0].score;
  const matches = candidates.filter((item) => item.score === bestScore);
  if (matches.length > 1) return { group: null, candidates: matches, reason: 'ambiguous_question' };
  return { group: matches[0], candidates, reason: '' };
}
function choiceOptionMatches(group, optionText) {
  const wanted = choiceFold(optionText);
  const exact = group.options.filter((option) => choiceFold(choiceOptionText(option)) === wanted);
  if (exact.length) return exact;
  return group.options.filter((option) => choiceContainsPhrase(choiceOptionText(option), wanted));
}
function choiceChecked(el) {
  const type = choiceType(el);
  const buttonGroup = choiceButtonGroup(el);
  if (buttonGroup) {
    const selectedByClass = [...el.classList].some((name) =>
      /(^|[-_])(active|selected|checked|chosen)(?:$|[-_])/i.test(name)
    );
    if (selectedByClass) return true;
    const input = buttonGroup.querySelector('input[type="radio"], input[type="checkbox"]');
    const option = choiceFold(choiceOptionText(el));
    if (input && ['yes', 'true'].includes(option)) return input.checked === true;
    return false;
  }
  return type === 'radio' || type === 'checkbox'
    ? (el.checked === true || el.getAttribute('aria-checked') === 'true'
      || el.getAttribute('aria-pressed') === 'true'
      || ['checked','selected','active','on'].includes((el.getAttribute('data-state') || '').toLowerCase())
      || el.classList.contains('selected') || el.classList.contains('is-selected'))
    : false;
}
function choiceSelectorHint(el) {
  if (!el || !el.tagName) return '';
  if (el.id) return `#${CSS.escape(el.id)}`;
  const name = el.getAttribute('name');
  const value = el.getAttribute('value');
  if (name && value) return `${el.tagName.toLowerCase()}[name="${name.replace(/"/g, '\\"')}"]`
    + `[value="${value.replace(/"/g, '\\"')}"]`;
  const parts = [];
  let current = el;
  while (current && current.nodeType === 1 && current !== document.body) {
    let position = 1;
    let sibling = current.previousElementSibling;
    while (sibling) {
      if (sibling.tagName === current.tagName) position += 1;
      sibling = sibling.previousElementSibling;
    }
    parts.unshift(`${current.tagName.toLowerCase()}:nth-of-type(${position})`);
    current = current.parentElement;
  }
  return `body > ${parts.join(' > ')}`;
}
"""
