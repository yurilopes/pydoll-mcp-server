"""JavaScript builders for LinkedIn Easy Apply helpers."""

from __future__ import annotations

import json

from pydoll_mcp_server.json_types import JsonObject
from pydoll_mcp_server.tools.linkedin_state_scripts import shared_state_helpers_script


def job_snapshot_script() -> str:
    return _script(
        """
  const detailRoot = findDetailRoot(document);
  if (!detailRoot && !isDirectJobView() && location.pathname.includes('/jobs/search/')) {
    return emptyJobSnapshot();
  }
  return jobSnapshotFromRoot(detailRoot || document);
"""
    )


def snapshot_script(include_resume_entries: bool, max_resume_entries: int) -> str:
    payload = json.dumps({'include_resume_entries': include_resume_entries, 'max_resume_entries': max_resume_entries})
    return _script(
        f"""
  const opts = {payload};
  const surface = findApplicationSurface();
  const pageText = rootText(document);
  const confirmation = /se candidatou agora|candidatura enviada|application submitted/.test(fold(pageText));
  if (!surface.root || surface.kind === 'confirmation') {{
    return {{
      success: true,
      surface: confirmation ? 'confirmation' : 'none',
      form_present: false,
      dialog_present: false,
      submitted: confirmation,
      confirmation_text: norm(pageText.match(/(Se candidatou agora|Candidatura enviada|Application submitted).{{0,80}}/i)?.[0] || ''),
      application_status: confirmation ? 'submitted' : '',
      application_state: confirmation ? 'submitted' : 'unknown',
      application_state_text: confirmation ? 'submitted' : '',
      timestamp_text: norm(pageText.match(/\\bagora\\b|just now/i)?.[0] || ''),
      authorization_risk: false,
      risk_text: '',
      fields: [],
      questions: [],
      uploads: {{ selected_or_latest_resume: '', resume_entries: [], upload_button_available: false, new_upload_visible: false }},
      primary_action: {{}},
      secondary_actions: [],
      blocking_prompt: {{}},
      toast_messages: [],
      inline_errors: [],
      pending_required: [],
      review_summary: {{}},
    }};
  }}
  const root = surface.kind === 'dialog' ? narrowApplicationRoot(surface.root) : surface.root;
  const text = rootText(root);
  const surfaceText = rootText(surface.root);
  const progress = stepProgressFor(surfaceText);
  const localProgress = stepProgressFor(text);
  const stepIndex = progress.index || localProgress.index;
  const stepCount = progress.count || localProgress.count;
  const headingText = [...root.querySelectorAll('h1, h2, h3, h4, [role="heading"]')]
    .filter((heading) => visible(heading))
    .map((heading) => norm(heading.innerText || '')).filter(Boolean).join(' ');
  const stepTitle = inferStepTitle(headingText || text);
  const fieldElements = [...root.querySelectorAll('input, textarea, select, [contenteditable="true"]')]
    .filter((el) => visible(el) || fold(el.getAttribute('type') || '') === 'radio');
  const fields = fieldElements.map((el, index) => fieldSnapshot(el, root, index));
  const questionMap = new Map();
  for (const field of fields) {{
    if (!field.label && !field.group_text) continue;
    const key = field.question_key || field.label;
    if (!questionMap.has(key)) {{
      questionMap.set(key, {{
        label: field.label || field.group_text.split('?')[0],
        input_type: field.type || field.tag,
        required: false,
        value: '',
        options: [],
        selected_option: '',
        validation_message: '',
      }});
    }}
    const question = questionMap.get(key);
    question.required = question.required || field.required;
    question.value = field.value || question.value;
    question.validation_message = field.validation_message || question.validation_message;
    if (field.selected_option) question.selected_option = field.selected_option;
    for (const option of field.options || []) {{
      const optionText = typeof option === 'string' ? option : norm(option?.text || '');
      if (optionText && !question.options.includes(optionText)) question.options.push(optionText);
    }}
  }}
  const questions = [...questionMap.values()];
  const buttons = visibleControls(root).filter((button) => enabled(button)).map(controlInfo);
  const submit = buttons.find((button) => isSubmitLabel(`${{button.text}} ${{button.aria}}`));
  const forward = buttons.find((button) => isForwardLabel(button.text));
  const resumeLines = String(text).split(/\\n+/).map(norm).filter((line) => /\\.(?:pdf|docx?)$/i.test(line));
  const inputResumeNames = [...root.querySelectorAll('input[type="file"]')]
    .flatMap((input) => [...(input.files || [])].map((file) => norm(file.name)));
  const resumeNames = [...new Set([...inputResumeNames, ...resumeLines.map((line) => line.replace(/^pdf\\s+/i, ''))])];
  const toastNodes = [...document.querySelectorAll('.artdeco-toast-item, [role="status"], [data-test-toast]')]
    .filter((item) => visible(item));
  const toasts = toastNodes.map((item) => norm(item.innerText || '')).filter(Boolean);
  const inlineErrors = [...root.querySelectorAll('[role="alert"], .artdeco-inline-feedback, .fb-dash-form-element__error-text')]
    .filter((item) => !item.closest('.artdeco-toast-item, [role="status"], [data-test-toast]'))
    .map((item) => norm(item.innerText || '')).filter(Boolean);
  for (const field of fields) {{
    if (field.validation_message) inlineErrors.push(field.validation_message);
  }}
  const uniqueErrors = [...new Set(inlineErrors)];
  const pending = [];
  const pendingKeys = new Set();
  for (const field of fields) {{
    if (!field.required || pendingKeys.has(field.question_key)) continue;
    const isChoice = field.type === 'radio' || field.type === 'checkbox';
    const hasValue = isChoice ? fields.some((item) => item.question_key === field.question_key && item.checked) : Boolean(field.value || field.selected_text?.length);
    if (!hasValue) {{
      pending.push(field.label || field.group_text);
      pendingKeys.add(field.question_key);
    }}
  }}
  const risk = riskTextFor(text);
  const reviewAnswers = reviewAnswersFor(text);
  const isReview = stepTitle === 'Review' || Boolean(submit && /revise sua candidatura|review/.test(fold(text)));
  const reviewSummary = isReview ? {{
    text: norm(text).slice(0, 2500),
    resume_filename: resumeNames[0] || '',
    final_submit_available: Boolean(submit && !submit.disabled),
    answers: questions.length ? questions : reviewAnswers,
  }} : {{}};
  const prompt = isSavePromptText(text) ? {{
    title: 'Salvar esta candidatura?',
    actions: buttons.map((button) => button.text).filter(Boolean),
  }} : {{}};
  return {{
    success: true,
    surface: surface.kind,
    form_present: surface.kind === 'dialog' || surface.kind === 'inline',
    dialog_present: surface.kind === 'dialog' || surface.kind === 'save_prompt',
    step_index: stepIndex,
    step_count: stepCount,
    step_title: stepTitle,
    is_review_step: isReview,
    is_final_submit_step: Boolean(submit && !submit.disabled),
    application_state: isReview ? 'draft' : 'unknown',
    application_state_text: isReview ? 'review_ready' : '',
    fields,
    questions,
    uploads: {{
      selected_or_latest_resume: resumeNames[0] || '',
      resume_entries: opts.include_resume_entries ? resumeNames.slice(0, opts.max_resume_entries) : [],
      upload_button_available: buttons.some((button) => isUploadLabel(`${{button.text}} ${{button.aria}}`)),
      new_upload_visible: Boolean(resumeNames[0]),
    }},
    primary_action: submit || forward || {{}},
    secondary_actions: buttons.filter((button) => /voltar|back|editar|edit/.test(fold(button.text))),
    blocking_prompt: prompt,
    toast_messages: [...new Set(toasts)],
    inline_errors: uniqueErrors,
    pending_required: pending.filter(Boolean),
    review_summary: reviewSummary,
    authorization_risk: Boolean(risk),
    risk_text: risk,
  }};
"""
    )


def resolve_action_script(action: str) -> str:
    payload = json.dumps({'action': action})
    return _script(
        f"""
  const opts = {payload};
  let surface = findApplicationSurface();
  let root = surface.root;
  if (opts.action === 'apply') {{
    root = findDetailRoot(document) || document;
    surface = {{ kind: isDirectJobView() ? 'job_view' : 'search_detail', root }};
  }}
  if (!root) return {{ success: false, action: opts.action, reason: 'surface_not_found' }};
  if (opts.action === 'file_input') {{
    const inputs = [...document.querySelectorAll('input[type="file"]')];
    const input = inputs.find((item) => root.contains(item)) || inputs.find((item) => item.isConnected);
    return input ? {{ success: true, action: opts.action, surface: surface.kind, target: controlInfo(input) }}
      : {{
        success: false,
        action: opts.action,
        surface: surface.kind,
        reason: 'file_input_not_found',
        file_system_access_api: typeof window.showOpenFilePicker === 'function',
        native_picker_likely: typeof window.showOpenFilePicker === 'function',
      }};
  }}
  const controls = visibleControls(root)
    .filter((control) => enabled(control))
    .filter((control) => ['button', 'a', 'input', 'label'].includes(control.tagName.toLowerCase())
      || ['button', 'link', 'radio', 'checkbox', 'option'].includes(fold(control.getAttribute('role') || '')));
  let matcher = () => false;
  if (opts.action === 'apply') matcher = (control) => isEasyApplyLabel(`${{controlText(control)}} ${{controlAria(control)}}`) || isContinueLabel(`${{controlText(control)}} ${{controlAria(control)}}`);
  if (opts.action === 'forward') matcher = (control) => isForwardLabel(controlLabel(control));
  if (opts.action === 'submit') matcher = (control) => isSubmitLabel(controlLabel(control));
  if (opts.action === 'upload') matcher = (control) => isUploadLabel(controlLabel(control));
  if (opts.action === 'save') matcher = (control) => isSaveLabel(controlLabel(control));
  if (opts.action === 'discard') matcher = (control) => isDiscardLabel(controlLabel(control));
  if (opts.action === 'close') matcher = (control) => isCloseLabel(controlLabel(control));
  const matches = controls.filter(matcher);
  matches.sort((left, right) => {{
    const leftTag = left.tagName.toLowerCase();
    const rightTag = right.tagName.toLowerCase();
    const leftButton = leftTag === 'button' || fold(left.getAttribute('role') || '') === 'button';
    const rightButton = rightTag === 'button' || fold(right.getAttribute('role') || '') === 'button';
    return Number(rightButton) - Number(leftButton);
  }});
  const target = matches[0];
  if (!target) return {{
    success: false,
    action: opts.action,
    surface: surface.kind,
    reason: 'target_not_found',
    candidates: controls.map(controlInfo).slice(0, 20),
  }};
  return {{ success: true, action: opts.action, surface: surface.kind, target: controlInfo(target) }};
"""
    )


def action_state_script(action: str) -> str:
    payload = json.dumps({'action': action})
    return _script(
        f"""
  const opts = {payload};
  const surface = findApplicationSurface();
  const root = surface.root && surface.kind !== 'confirmation'
    ? (surface.kind === 'dialog' ? narrowApplicationRoot(surface.root) : surface.root)
    : null;
  const text = root ? rootText(root) : rootText(document);
  const progress = stepProgressFor(text);
  const buttons = root ? visibleControls(root).filter((button) => enabled(button)).map(controlInfo) : [];
  const submit = buttons.find((button) => isSubmitLabel(`${{button.text}} ${{button.aria}}`));
  const forward = buttons.find((button) => isForwardLabel(button.text));
  const primary = submit || forward || {{}};
  const bodyText = rootText(document);
  return {{
    success: true,
    action: opts.action,
    surface: surface.kind,
    form_present: surface.kind === 'dialog' || surface.kind === 'inline',
    dialog_present: surface.kind === 'dialog' || surface.kind === 'save_prompt',
    submitted: surface.kind === 'confirmation' || /se candidatou agora|candidatura enviada|application submitted/.test(fold(bodyText)),
    prompt_present: surface.kind === 'save_prompt' || isSavePromptText(bodyText),
    step_index: progress.index,
    step_count: progress.count,
    step_title: inferStepTitle(text),
    primary_label: norm(`${{primary.text || ''}} ${{primary.aria || ''}}`),
    content_signature: norm(text).slice(0, 1200),
  }};
"""
    )


def fill_questions_script(answers: list[JsonObject]) -> str:
    payload = json.dumps({'answers': answers})
    return _script(
        f"""
  const opts = {payload};
  const surface = findApplicationSurface();
  if (!surface.root) return {{ success: false, filled: [], unfilled: opts.answers, ambiguous: [], radio_actions: [], blockers: [], reason: 'surface_not_found' }};
  const root = surface.root;
  const filled = [];
  const unfilled = [];
  const ambiguous = [];
  const radioActions = [];
  const controls = [...root.querySelectorAll('input, textarea, select, [contenteditable="true"]')]
    .filter((el) => visible(el) || ['radio', 'checkbox'].includes(fold(el.getAttribute('type') || '')));
  const metadata = controls.map((el) => {{
    const questionRoot = questionRootFor(el, root);
    return {{ el, field: fieldSnapshot(el, root, 0), questionRoot }};
  }});
  const uniqueQuestionRoots = (items) => [...new Map(items.map((item) => [item.field.question_key, item])).values()];
  const setValue = (el, value) => {{
    const stringValue = String(value ?? '');
    const prototype = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    const setter = Object.getOwnPropertyDescriptor(prototype, 'value')?.set;
    if (setter) setter.call(el, stringValue); else el.value = stringValue;
    el.dispatchEvent(new InputEvent('input', {{ bubbles: true, inputType: 'insertReplacementText', data: stringValue }}));
    el.dispatchEvent(new Event('change', {{ bubbles: true }}));
    el.dispatchEvent(new Event('blur', {{ bubbles: true }}));
  }};
  for (const answer of opts.answers) {{
    const needle = questionText(answer.question_contains || '');
    if (!needle) {{
      unfilled.push({{ question_contains: '', reason: 'no_match' }});
      continue;
    }}
    const scored = uniqueQuestionRoots(metadata)
      .map((item) => ({{ item, score: questionMatchScore(item, needle, answer) }}))
      .filter((candidate) => candidate.score >= 0)
      .sort((left, right) => right.score - left.score);
    if (scored.length === 0) {{
      unfilled.push({{ question_contains: answer.question_contains || '', reason: 'no_match' }});
      continue;
    }}
    const bestScore = scored[0].score;
    const matches = scored.filter((candidate) => candidate.score === bestScore).map((candidate) => candidate.item);
    if (matches.length > 1) {{
      ambiguous.push({{
        question_contains: answer.question_contains || '',
        reason: 'multiple_equally_specific_questions',
        matches: matches.map((item) => ({{ label: item.field.label, input_type: item.field.type || item.field.tag, question_key: item.field.question_key, match_score: bestScore }})),
      }});
      continue;
    }}
    const match = matches[0];
    const group = metadata.filter((item) => item.field.question_key === match.field.question_key);
    const optionText = fold(answer.option_text || answer.value || '');
    const textControl = group.find((item) => ['text', 'email', 'number', 'tel', 'url', ''].includes(fold(item.field.type)) || item.field.tag === 'textarea');
    if (answer.value !== undefined && answer.value !== null && textControl) {{
      setValue(textControl.el, answer.value);
      filled.push({{ question_contains: answer.question_contains || '', matched_label: match.field.label, value: String(answer.value), input_type: textControl.field.type || textControl.field.tag }});
      continue;
    }}
    const selectControl = group.find((item) => item.field.tag === 'select');
    if (optionText && selectControl) {{
      const option = [...selectControl.el.options].find((item) => fold(item.textContent || '') === optionText || fold(item.value || '') === optionText);
      if (!option) {{
        unfilled.push({{ question_contains: answer.question_contains || '', reason: 'option_not_found', matched_label: match.field.label }});
        continue;
      }}
      const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, 'value')?.set;
      if (setter) setter.call(selectControl.el, option.value); else selectControl.el.value = option.value;
      selectControl.el.dispatchEvent(new Event('input', {{ bubbles: true }}));
      selectControl.el.dispatchEvent(new Event('change', {{ bubbles: true }}));
      filled.push({{ question_contains: answer.question_contains || '', matched_label: match.field.label, option_text: norm(option.textContent || ''), selected_value: String(option.value || '') }});
      continue;
    }}
    const radios = group.filter((item) => ['radio', 'checkbox'].includes(fold(item.field.type)));
    if (optionText && radios.length) {{
      const choices = radios.filter((item) => fold(optionLabelFor(item.el)) === optionText);
      if (choices.length !== 1) {{
        unfilled.push({{ question_contains: answer.question_contains || '', reason: choices.length ? 'ambiguous_option' : 'option_not_found', matched_label: match.field.label }});
        continue;
      }}
      const choice = choices[0];
      if (choice.field.checked) {{
        filled.push({{ question_contains: answer.question_contains || '', matched_label: match.field.label, option_text: optionLabelFor(choice.el), verified: true }});
      }} else {{
        radioActions.push({{ selector: cssPath(choice.el), question_contains: answer.question_contains || '', matched_label: match.field.label, option_text: optionLabelFor(choice.el) }});
      }}
      continue;
    }}
    ambiguous.push({{ question_contains: answer.question_contains || '', matches: group.length, reason: 'unsupported_or_ambiguous_control' }});
  }}
  const risk = riskTextFor(rootText(root));
  return {{ success: unfilled.length === 0 && ambiguous.length === 0, filled, unfilled, ambiguous, radio_actions: radioActions, blockers: risk ? [risk] : [], authorization_risk: Boolean(risk), risk_text: risk }};
"""
    )


def set_choice_state_script(selector: str) -> str:
    payload = json.dumps({'selector': selector})
    return _script(
        f"""
  const opts = {payload};
  const target = document.querySelector(opts.selector);
  if (!target) return {{ success: false, verified: false, reason: 'choice_not_found' }};
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'checked')?.set;
  if (setter) setter.call(target, true); else target.checked = true;
  target.dispatchEvent(new InputEvent('input', {{ bubbles: true }}));
  target.dispatchEvent(new Event('change', {{ bubbles: true }}));
  target.dispatchEvent(new MouseEvent('click', {{ bubbles: true, view: window }}));
  return {{ success: target.checked === true, verified: target.checked === true, selector: opts.selector }};
"""
    )


def _script(body: str) -> str:
    return '(() => {\n' + shared_state_helpers_script() + body + '\n})()'
