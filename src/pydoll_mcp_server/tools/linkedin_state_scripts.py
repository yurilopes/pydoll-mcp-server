"""Shared JavaScript helpers for LinkedIn surface and state detection."""

from __future__ import annotations

from pydoll_mcp_server.tools.choice_group_scripts import choice_group_helpers_script
from pydoll_mcp_server.tools.linkedin_form_scripts import form_state_helpers_script


def shared_state_helpers_script() -> str:
    """Return browser-side helpers shared by LinkedIn search and Easy Apply scripts."""
    return (
        r"""
function norm(value) {
  return String(value ?? '').replace(/\s+/g, ' ').trim();
}
function fold(value) {
  return norm(value).normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
}
function rootText(root) {
  return root?.body?.innerText || root?.innerText || '';
}
function visible(el) {
  if (!el || !el.isConnected) return false;
  const rect = el.getBoundingClientRect();
  const style = getComputedStyle(el);
  return rect.width > 0 && rect.height > 0
    && style.display !== 'none'
    && style.visibility !== 'hidden'
    && parseFloat(style.opacity || '1') > 0;
}
function enabled(el) {
  return !el.disabled && el.getAttribute('aria-disabled') !== 'true';
}
function controlText(el) {
  return norm(el.innerText || el.textContent || el.getAttribute('aria-label') || el.value || '');
}
function controlAria(el) {
  return norm(el.getAttribute('aria-label') || '');
}
function controlLabel(el) {
  return norm(controlText(el) || controlAria(el));
}
function hasText(value, pattern) {
  return pattern.test(fold(value));
}
function isDirectJobView() {
  return /\/jobs\/view\/\d+/.test(location.pathname);
}
function selectedJobIdFromUrl() {
  return location.pathname.match(/\/jobs\/view\/(\d+)/)?.[1]
    || new URL(location.href).searchParams.get('currentJobId')
    || '';
}
function jobIdFromUrl() {
  return selectedJobIdFromUrl();
}
function isEasyApplyLabel(value) {
  return hasText(value, /candidatura simplificada|easy apply|usar a candidatura simplificada|use easy apply/);
}
function isContinueLabel(value) {
  const text = fold(value);
  return text === 'continuar' || text === 'continue'
    || /continuar candidatura|continue application/.test(text);
}
function isForwardLabel(value) {
  return /^(avancar|next|avaliar|review|revisar candidatura)$/.test(fold(value));
}
function isSubmitLabel(value) {
  return /enviar candidatura|submit application/.test(fold(value));
}
function isUploadLabel(value) {
  return /carregar curriculo|upload resume|upload cv|choose resume/.test(fold(value));
}
function isSaveLabel(value) {
  return /^(salvar|save)$/.test(fold(value));
}
function isDiscardLabel(value) {
  return /^(descartar|discard)$/.test(fold(value));
}
function isCloseLabel(value) {
  return /^(fechar|close|dismiss)$/.test(fold(value));
}
function isActionableElement(el) {
  if (!el || !enabled(el)) return false;
  const tag = el.tagName?.toLowerCase() || '';
  const role = fold(el.getAttribute('role') || '');
  return ['button', 'a', 'input', 'textarea', 'select', 'label', 'option'].includes(tag)
    || ['button', 'link', 'tab', 'menuitem', 'radio', 'checkbox', 'option', 'combobox'].includes(role)
    || el.tabIndex >= 0;
}
function cssPath(el) {
  if (!el || !el.tagName) return '';
  if (el.id) return `#${CSS.escape(el.id)}`;
  const parts = [];
  let current = el;
  while (current && current.nodeType === 1 && current !== document.body) {
    const tag = current.tagName.toLowerCase();
    let index = 1;
    let sibling = current.previousElementSibling;
    while (sibling) {
      if (sibling.tagName === current.tagName) index += 1;
      sibling = sibling.previousElementSibling;
    }
    parts.unshift(`${tag}:nth-of-type(${index})`);
    current = current.parentElement;
  }
  return `body > ${parts.join(' > ')}`;
}
"""
        + choice_group_helpers_script()
        + r"""
function controlInfo(el) {
  const rect = el.getBoundingClientRect();
  return {
    text: controlText(el),
    aria: controlAria(el),
    tag: el.tagName.toLowerCase(),
    role: el.getAttribute('role') || '',
    disabled: !enabled(el),
    selector_hint: cssPath(el),
    bounds: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
  };
}
function visibleControls(root) {
  return [...root.querySelectorAll(
    'button, a, input, select, textarea, label, [role="button"], [role="link"], '
      + '[role="tab"], [role="menuitem"], [role="radio"], [role="checkbox"], [role="option"], [role="combobox"]'
  )].filter((el) => visible(el) && isActionableElement(el));
}
function isApplicationStepText(value) {
  return /contact info|informacoes de contato|resume|curriculo|additional questions|perguntas adicionais|review|revise sua candidatura|work experience|experiencia profissional|education|formacao/.test(fold(value));
}
function isApplicationControl(el) {
  const label = controlLabel(el);
  return isForwardLabel(label) || isSubmitLabel(label) || isUploadLabel(label)
    || el.matches('input[type="file"]');
}
function hasApplicationAnchor(root) {
  const text = rootText(root);
  if (isApplicationStepText(text) && root.querySelectorAll(
    'input, textarea, select, [role="radio"], [role="checkbox"]'
  ).length > 0) return true;
  return visibleControls(root).some((el) => isApplicationControl(el));
}
function applicationRootFor(node) {
  let current = node;
  let fallback = null;
  for (let depth = 0; current && depth < 12; depth += 1, current = current.parentElement) {
    if (current === document.body || current === document.documentElement) break;
    if (!visible(current)) continue;
    if (hasApplicationAnchor(current) && (isApplicationStepText(rootText(current)) || current.matches('form'))) {
      fallback = current;
      const controls = visibleControls(current);
      const hasForward = controls.some((control) =>
        isForwardLabel(controlLabel(control)) || isSubmitLabel(controlLabel(control))
      );
      if (hasForward || current.matches('form')) return current;
    }
  }
  return fallback ? narrowApplicationRoot(fallback) : null;
}
function narrowApplicationRoot(root) {
  const candidates = [root, ...root.querySelectorAll('section, [data-step], [class*="step"], [id*="step"], form > div')]
    .filter((candidate) => visible(candidate) && isApplicationStepText(rootText(candidate)));
  const actionable = candidates.filter((candidate) => visibleControls(candidate).some((el) => isApplicationControl(el)));
  if (!actionable.length) return root;
  const complete = actionable.filter((candidate) => {
    const controls = visibleControls(candidate);
    const hasForward = controls.some((control) =>
      isForwardLabel(controlLabel(control)) || isSubmitLabel(controlLabel(control))
    );
    const hasContent = controls.some((control) =>
      isUploadLabel(controlLabel(control)) || control.matches(
        'input, textarea, select, [contenteditable="true"], [role="radio"], [role="checkbox"]'
      )
    );
    return hasForward && hasContent;
  });
  const scoped = complete.length ? complete : actionable;
  scoped.sort((left, right) => rootText(left).length - rootText(right).length);
  return scoped[0];
}
function isSavePromptText(value) {
  return /salvar esta candidatura|save this application/.test(fold(value));
}
function findApplicationSurface() {
  const dialogs = [...document.querySelectorAll(
    '[role="dialog"], dialog, [aria-modal="true"], .jobs-easy-apply-modal, .artdeco-modal, [data-test-modal]'
  )]
    .filter((el) => visible(el));
  for (let index = dialogs.length - 1; index >= 0; index -= 1) {
    const dialog = dialogs[index];
    const text = rootText(dialog);
    if (isSavePromptText(text)) return { root: dialog, kind: 'save_prompt' };
    if (hasApplicationAnchor(dialog)) return { root: dialog, kind: 'dialog' };
  }
  const actionControls = visibleControls(document).filter((el) => isApplicationControl(el));
  for (const control of actionControls) {
    const root = applicationRootFor(control);
    if (root) return { root, kind: 'inline' };
  }
  const forms = [...document.querySelectorAll('form, [class*="easy-apply"], [class*="easy_apply"], [data-test-modal]')]
    .filter((el) => visible(el) && hasApplicationAnchor(el));
  if (forms.length) return { root: forms.at(-1), kind: 'inline' };
  const body = rootText(document);
  if (/se candidatou agora|candidatura enviada|application submitted/.test(fold(body))) {
    return { root: document, kind: 'confirmation' };
  }
  return { root: null, kind: 'none' };
}
function findDetailRoot(source) {
  if (isDirectJobView()) return document;
  const selectedId = selectedJobIdFromUrl();
  const selectors = [
    '.jobs-search__job-details',
    '.jobs-details',
    '.jobs-details__main-content',
    '[data-job-details]',
  ];
  const candidates = selectors.flatMap((selector) => [...source.querySelectorAll(selector)])
    .filter((el) => visible(el) && hasLoadedDetailContent(el));
  if (selectedId) {
    const selected = candidates.filter((el) => {
      const link = el.querySelector(`a[href*="/jobs/view/${CSS.escape(selectedId)}/"]`);
      return Boolean(link) || el.getAttribute('data-job-id') === selectedId || rootText(el).length > 100;
    });
    if (selected.length) return selected.at(-1);
  }
  return candidates.at(-1) || null;
}
function hasLoadedDetailContent(root) {
  const text = norm(rootText(root));
  return text.length >= 40 && Boolean(root.querySelector('h1, h2, [role="heading"], button, a'));
}
function labelForControl(el, root) {
  const ids = (el.getAttribute('aria-labelledby') || '').split(/\s+/).filter(Boolean);
  const ariaLabels = ids.map((id) => document.getElementById(id)?.innerText || '').filter(Boolean);
  if (ariaLabels.length) return norm(ariaLabels.join(' '));
  if (el.id) {
    const explicit = root.querySelector(`label[for="${CSS.escape(el.id)}"]`)
      || document.querySelector(`label[for="${CSS.escape(el.id)}"]`);
    if (explicit) return norm(explicit.innerText || '');
  }
  const closest = el.closest('label');
  if (closest) return norm(closest.innerText || '');
  const type = choiceType(el) || fold(el.getAttribute('type') || '');
  if (type === 'radio' || type === 'checkbox') return choiceOptionText(el);
  return norm(el.getAttribute('aria-label') || el.placeholder || (type === 'radio' || type === 'checkbox' ? '' : el.name || ''));
}
function questionRootFor(el, root) {
  const type = choiceType(el);
  if (type) return choiceGroupFor(el, root);
  const label = el.closest('label');
  if (label && root.contains(label)) return label;
  let current = el.parentElement;
  for (let depth = 0; current && current !== root && depth < 6; depth += 1, current = current.parentElement) {
    const text = rootText(current);
    const controls = current.querySelectorAll('input, textarea, select, [role="radio"], [role="checkbox"]');
    if (controls.length <= 4 && (/[?]/.test(text) || current.querySelector('label'))) return current;
  }
  return el.parentElement || root;
}
function optionLabelFor(el) {
  return choiceOptionText(el);
}
function fieldSnapshot(el, root, questionIndex) {
  const tag = el.tagName.toLowerCase();
  const type = choiceType(el) || fold(el.getAttribute('type') || '');
  const questionRoot = questionRootFor(el, root);
  const rawGroupText = norm(rootText(questionRoot));
  const choiceQuestion = type === 'radio' || type === 'checkbox'
    ? choiceQuestionText(questionRoot, root) : '';
  const groupText = choiceQuestion ? norm(`${choiceQuestion} ${rawGroupText}`) : rawGroupText;
  const label = choiceQuestion || labelForControl(el, root) || groupText;
  const selected = tag === 'select' ? [...el.selectedOptions].map((option) => norm(option.textContent || '')) : [];
  const options = tag === 'select'
    ? [...el.options].map((option) => ({ text: norm(option.textContent || ''), value: String(option.value || '') }))
    : (type === 'radio' || type === 'checkbox'
      ? choiceOptionElements(questionRoot).map(optionLabelFor).filter(Boolean)
      : []);
  return {
    tag,
    type,
    label,
    group_text: groupText.slice(0, 500),
    question_key: cssPath(questionRoot) || `question-${questionIndex}`,
    required: Boolean(el.required || el.getAttribute('aria-required') === 'true' || /\*/.test(label || groupText)),
    value: tag === 'select' ? String(el.value || '') : String(el.value || ''),
    checked: type === 'radio' || type === 'checkbox' ? choiceChecked(el) : null,
    selected_option: type === 'radio' || type === 'checkbox' ? (choiceChecked(el) ? optionLabelFor(el) : '') : (selected[0] || ''),
    selected_text: selected,
    selected_value: tag === 'select' ? String(el.value || '') : '',
    options,
    validation_message: norm(el.validationMessage || ''),
  };
}
function inferStepTitle(text) {
  const lower = fold(text);
  if (/additional questions|perguntas adicionais/.test(lower)) return 'Additional Questions';
  const lines = String(text || '').split(/\n+/).map((line) => fold(line)).filter(Boolean);
  if (lines.some((line) => line === 'review' || line === 'revise sua candidatura')) return 'Review';
  if (/resume|curriculo/.test(lower)) return 'Resume';
  if (/education|formacao/.test(lower)) return 'Education';
  if (/work experience|experiencia/.test(lower)) return 'Work Experience';
  if (/contact info|informacoes de contato/.test(lower)) return 'Contact info';
  return '';
}
"""
        + form_state_helpers_script()
        + r"""
function riskTextFor(text) {
  const match = String(text || '').match(/.{0,80}(W2|GC Holder|Green Card|US Citizen|C2C|1099|sponsorship|visa|work authorization|no sponsorship).{0,140}/i);
  return match ? norm(match[0]) : '';
}
function applicationStateFromControls(text, controls) {
  const applied = /se candidatou agora|candidatura enviada|application submitted/.test(fold(text));
  const unavailable = /nao aceita mais candidaturas|no longer accepting|vaga encerrada|job closed/.test(fold(text));
  const easy = controls.find((item) => isEasyApplyLabel(`${item.text} ${item.aria}`) && !item.disabled);
  const cont = controls.find((item) => isContinueLabel(`${item.text} ${item.aria}`) && !item.disabled);
  const saved = controls.find((item) => /^(salvo|saved)$/.test(fold(item.text))
    || /salvar vaga|save job|vaga salva|saved job/.test(fold(`${item.text} ${item.aria}`)));
  if (applied) return { state: 'submitted', text: norm(text.match(/(Se candidatou agora|Candidatura enviada|Application submitted).{0,80}/i)?.[0] || '') };
  if (cont || /suas respostas foram salvas|answers were saved/.test(fold(text))) return { state: 'draft', text: cont?.text || 'saved draft' };
  if (easy) return { state: 'not_started', text: easy.text || easy.aria };
  if (saved) return { state: 'saved', text: saved.text || saved.aria };
  if (unavailable) return { state: 'unavailable', text: 'unavailable' };
  return { state: 'unknown', text: '' };
}
function emptyJobSnapshot() {
  return {
    success: true,
    linkedin_job_id: '',
    canonical_url: location.href,
    url: location.href,
    role: '',
    company: '',
    location: '',
    button_state: 'unknown',
    application_state: 'unknown',
    application_state_text: '',
    easy_apply_available: false,
    easy_apply_button_text: '',
    easy_apply_button_aria: '',
    can_continue_easy_apply: false,
    already_applied: false,
    application_status: '',
    authorization_risk: false,
    risk_text: '',
    description_excerpt: '',
  };
}
function jobSnapshotFromRoot(root) {
  const sourceRoot = root || null;
  const text = rootText(sourceRoot);
  const controls = sourceRoot ? visibleControls(sourceRoot).map(controlInfo) : [];
  const state = applicationStateFromControls(text, controls);
  const easy = controls.find((item) => isEasyApplyLabel(`${item.text} ${item.aria}`) && !item.disabled);
  const cont = controls.find((item) => isContinueLabel(`${item.text} ${item.aria}`) && !item.disabled);
  const id = jobIdFromUrl()
    || sourceRoot?.getAttribute?.('data-job-id')
    || sourceRoot?.querySelector('[data-job-id]')?.getAttribute('data-job-id')
    || '';
  const titleParts = document.title.split('|').map(norm).filter(Boolean);
  const heading = norm(sourceRoot?.querySelector('h1, [role="heading"]')?.innerText || '');
  const role = heading && !/notifica/i.test(heading) ? heading
    : (isDirectJobView() && titleParts.length >= 2 && !/linkedin/i.test(titleParts[0]) ? titleParts[0] : '');
  const company = norm(sourceRoot?.querySelector('.job-details-jobs-unified-top-card__company-name, .job-details-jobs-unified-top-card__primary-description a, .company')?.innerText || (isDirectJobView() ? titleParts[1] || '' : ''));
  const lines = String(text || '').split(/\n+/).map(norm).filter(Boolean);
  const location = lines.find((line) => /remote|remoto|united states|estados unidos|brazil|brasil|europe|europa/.test(fold(line))) || '';
  const risk = riskTextFor(text);
  const result = emptyJobSnapshot();
  result.linkedin_job_id = id;
  result.canonical_url = id ? `https://www.linkedin.com/jobs/view/${id}/` : location.href;
  result.url = location.href;
  result.role = role;
  result.company = company;
  result.location = location;
  result.button_state = state.state === 'not_started' ? 'easy_apply' : state.state === 'draft' ? 'continue' : state.state === 'submitted' ? 'applied' : state.state;
  result.application_state = state.state;
  result.application_state_text = state.text;
  result.easy_apply_available = Boolean(easy || cont);
  result.easy_apply_button_text = easy?.text || cont?.text || '';
  result.easy_apply_button_aria = easy?.aria || cont?.aria || '';
  result.can_continue_easy_apply = Boolean(cont);
  result.already_applied = state.state === 'submitted';
  result.application_status = state.state === 'submitted' ? 'submitted' : '';
  result.authorization_risk = Boolean(risk);
  result.risk_text = risk;
  result.description_excerpt = norm(text).slice(0, 2000);
  return result;
}
function primaryActionFor(root) {
  const controls = visibleControls(root).filter((el) => enabled(el));
  const submit = controls.find((el) => isSubmitLabel(controlLabel(el)));
  const forward = controls.find((el) => isForwardLabel(controlLabel(el)));
  return submit ? controlInfo(submit) : forward ? controlInfo(forward) : {};
}
"""
    )
