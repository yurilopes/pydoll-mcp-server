"""JavaScript builders for LinkedIn-specific browser helpers."""

from __future__ import annotations

import json

from pydoll_mcp_server.json_types import JsonObject


def job_snapshot_script() -> str:
    return """
(() => {
  const norm = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const text = document.body.innerText || '';
  const url = new URL(location.href);
  const idMatch = url.pathname.match(/\\/jobs\\/view\\/(\\d+)/);
  const buttons = [...document.querySelectorAll('button, a')].filter((el) => {
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0;
  }).map((el) => ({
    text: norm(el.innerText || ''),
    aria: norm(el.getAttribute('aria-label') || ''),
    tag: el.tagName.toLowerCase(),
  }));
  const easy = buttons.find((b) => /candidatura simplificada|easy apply/i.test(b.text + ' ' + b.aria));
  const cont = buttons.find((b) => /^continuar$/i.test(b.text));
  const saved = buttons.find((b) => /^salvo$|^saved$/i.test(b.text) || /vaga salva|saved job/i.test(b.aria));
  const applied = /se candidatou agora|candidatura enviada|application submitted/i.test(text);
  const unavailable = /não aceita mais candidaturas|no longer accepting|vaga encerrada|job closed/i.test(text);
  const titleParts = document.title.split('|').map(norm).filter(Boolean);
  const isDirectJobView = Boolean(idMatch);
  const pageTitleRole = isDirectJobView && titleParts.length >= 2 && !/LinkedIn/i.test(titleParts[0]) ? titleParts[0] : '';
  const pageTitleCompany = isDirectJobView && titleParts.length >= 2 ? titleParts[1] : '';
  const heading = norm(document.querySelector('.jobs-unified-top-card h1, .job-details-jobs-unified-top-card h1, .jobs-details__main-content h1')?.innerText || '');
  const title = heading && !/notifica/i.test(heading) ? heading : pageTitleRole;
  const company = norm(
    document.querySelector('.job-details-jobs-unified-top-card__company-name, .job-details-jobs-unified-top-card__primary-description a')?.innerText
    || pageTitleCompany
  );
  const riskMatch = text.match(/.{0,80}(W2|GC Holder|Green Card|US Citizen|C2C|1099|sponsorship|visa|work authorization|no sponsorship).{0,120}/i);
  let buttonState = 'unknown';
  let applicationState = 'unknown';
  let applicationStateText = '';
  if (applied) buttonState = 'applied';
  else if (cont) buttonState = 'continue';
  else if (easy) buttonState = 'easy_apply';
  else if (saved) buttonState = 'saved';
  else if (unavailable) buttonState = 'unavailable';
  if (applied) {
    applicationState = 'submitted';
    applicationStateText = norm(text.match(/(Se candidatou agora|Candidatura enviada|Application submitted).{0,80}/i)?.[0] || '');
  } else if (cont || /suas respostas foram salvas|answers were saved/i.test(text)) {
    applicationState = 'draft';
    applicationStateText = cont?.text || 'saved draft';
  } else if (easy) {
    applicationState = 'not_started';
    applicationStateText = easy.text || easy.aria;
  } else if (saved) {
    applicationState = 'saved';
    applicationStateText = saved.text || saved.aria;
  } else if (unavailable) {
    applicationState = 'unavailable';
    applicationStateText = 'unavailable';
  }
  return {
    success: true,
    linkedin_job_id: idMatch ? idMatch[1] : '',
    canonical_url: idMatch ? `https://www.linkedin.com/jobs/view/${idMatch[1]}/` : location.href,
    url: location.href,
    role: title,
    company,
    location: norm((text.match(/\\n([^\\n]*Estados Unidos[^\\n]*|[^\\n]*Brasil[^\\n]*)\\n/) || [])[1] || ''),
    easy_apply_available: Boolean(easy || cont),
    button_state: buttonState,
    application_state: applicationState,
    application_state_text: applicationStateText,
    easy_apply_button_text: easy?.text || cont?.text || '',
    easy_apply_button_aria: easy?.aria || cont?.aria || '',
    can_continue_easy_apply: Boolean(cont),
    already_applied: applied,
    application_status: applied ? 'submitted' : '',
    authorization_risk: Boolean(riskMatch),
    risk_text: riskMatch ? norm(riskMatch[0]) : '',
    description_excerpt: norm(text).slice(0, 2000),
  };
})()
"""


def snapshot_script(include_resume_entries: bool, max_resume_entries: int) -> str:
    payload = json.dumps({'include_resume_entries': include_resume_entries, 'max_resume_entries': max_resume_entries})
    return (
        '(() => {\nconst opts = '
        + payload
        + """;
  const norm = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const visible = (el) => {
    const rect = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
  };
  const dialogs = [...document.querySelectorAll('[role="dialog"], dialog, .jobs-easy-apply-modal')]
    .filter((el) => {
      const rect = el.getBoundingClientRect();
      return rect.width > 100 && rect.height > 100 && getComputedStyle(el).visibility !== 'hidden';
    });
  const dialog = dialogs.at(-1);
  const pageText = document.body.innerText || '';
  if (!dialog) {
    return {
      success: true,
      dialog_present: false,
      submitted: /se candidatou agora|candidatura enviada|application submitted/i.test(pageText),
      confirmation_text: norm(pageText.match(/(Se candidatou agora|Candidatura enviada|Application submitted).{0,80}/i)?.[0] || ''),
      application_status: /candidatura enviada|application submitted/i.test(pageText) ? 'submitted' : '',
      timestamp_text: norm(pageText.match(/\\bagora\\b|just now/i)?.[0] || ''),
    };
  }
  const text = dialog.innerText || '';
  const stepMatch = text.match(/(\\d+)\\s+de\\s+(\\d+)\\s+p[aá]ginas?|Step\\s+(\\d+)\\s+of\\s+(\\d+)/i);
  const stepIndex = stepMatch ? Number(stepMatch[1] || stepMatch[3] || 0) : 0;
  const stepCount = stepMatch ? Number(stepMatch[2] || stepMatch[4] || 0) : 0;
  const lower = text.toLowerCase();
  let stepTitle = '';
  if (/revise sua candidatura|review/i.test(lower)) stepTitle = 'Review';
  else if (/additional questions|perguntas adicionais/i.test(lower)) stepTitle = 'Additional Questions';
  else if (/resume|curr[ií]culo/i.test(lower)) stepTitle = 'Resume';
  else if (/education|forma[cç][aã]o/i.test(lower)) stepTitle = 'Education';
  else if (/work experience|experi[eê]ncia/i.test(lower)) stepTitle = 'Work Experience';
  else if (/contact info|informa[cç][oõ]es de contato/i.test(lower)) stepTitle = 'Contact info';
  const fields = [...dialog.querySelectorAll('input, textarea, select')].filter((el) => visible(el) || el.type === 'radio')
    .map((el) => {
      const tag = el.tagName.toLowerCase();
      const type = (el.getAttribute('type') || '').toLowerCase();
      const selected = tag === 'select' ? [...el.selectedOptions].map((opt) => norm(opt.textContent || '')) : [];
      const label = norm(
        (el.id ? dialog.querySelector(`label[for="${CSS.escape(el.id)}"]`)?.innerText || '' : '')
        || el.closest('label')?.innerText || el.getAttribute('aria-label') || el.placeholder || ''
      );
      const group = norm(el.closest('fieldset, .jobs-easy-apply-form-section__grouping, div')?.innerText || '');
      return {
        tag,
        type,
        label,
        group_text: group.slice(0, 500),
        required: Boolean(el.required || /\\*/.test(label || group)),
        value: tag === 'select' ? '' : String(el.value || ''),
        checked: type === 'radio' || type === 'checkbox' ? Boolean(el.checked) : null,
        selected_text: selected,
        selected_value: tag === 'select' ? String(el.value || '') : '',
        validation_message: norm(el.validationMessage || ''),
      };
    });
  const buttons = [...dialog.querySelectorAll('button')].filter(visible).map((button) => ({
    text: norm(button.innerText || ''),
    aria: norm(button.getAttribute('aria-label') || ''),
    disabled: Boolean(button.disabled),
  }));
  const forward = buttons.find((b) => /^Avan|^Aval|^Next|^Review/i.test(b.text));
  const submit = buttons.find((b) => /Enviar candidatura|Submit application/i.test(b.text));
  const resumeMatches = [...text.matchAll(/(?:PDF|DOCX?)\\s+([^\\n]+\\.(?:pdf|docx?|PDF|DOCX?))/g)]
    .map((match) => norm(match[1]));
  const resumes = [...new Set(resumeMatches)];
  const riskMatch = text.match(/.{0,80}(W2|GC Holder|Green Card|US Citizen|C2C|1099|sponsorship|visa|work authorization|no sponsorship).{0,120}/i);
  const inlineErrors = [...dialog.querySelectorAll('[role="alert"], .artdeco-inline-feedback, .fb-dash-form-element__error-text')]
    .map((el) => norm(el.innerText || '')).filter(Boolean);
  const textErrors = [...text.matchAll(/Valor inválido|required|obrigat[oó]rio/gi)].map((match) => match[0]);
  const toastMessages = [...document.querySelectorAll('.artdeco-toast-item, [role="status"]')]
    .map((el) => norm(el.innerText || '')).filter(Boolean);
  const questions = fields.filter((field) => field.label || field.group_text).map((field) => ({
    label: field.label || field.group_text.split('?')[0],
    input_type: field.type || field.tag,
    required: field.required,
    value: field.value,
    options: field.type === 'radio' ? ['Yes', 'No'].filter((option) => field.group_text.includes(option)) : [],
    selected_option: field.checked ? field.label : '',
    validation_message: field.validation_message,
  }));
  const reviewSummary = {};
  if (/revise sua candidatura|review/i.test(lower)) {
    reviewSummary.text = norm(text).slice(0, 2500);
    reviewSummary.resume_filename = resumes[0] || '';
    reviewSummary.final_submit_available = Boolean(submit && !submit.disabled);
  }
  return {
    success: true,
    dialog_present: true,
    step_index: stepIndex,
    step_count: stepCount,
    step_title: stepTitle,
    is_review_step: /revise sua candidatura|review/i.test(lower),
    is_final_submit_step: Boolean(submit),
    fields,
    questions,
    uploads: {
      selected_or_latest_resume: resumes[0] || '',
      resume_entries: opts.include_resume_entries ? resumes.slice(0, opts.max_resume_entries) : [],
      upload_button_available: buttons.some((b) => /Carregar curr|Upload resume/i.test(b.text)),
      new_upload_visible: Boolean(resumes[0]),
    },
    primary_action: submit || forward || {},
    secondary_actions: buttons.filter((b) => /Voltar|Back/i.test(b.text)),
    blocking_prompt: /Salvar esta candidatura\\?|Save this application\\?/i.test(text)
      ? { title: 'Salvar esta candidatura?', actions: buttons.map((b) => b.text).filter(Boolean) } : {},
    toast_messages: toastMessages,
    inline_errors: [...inlineErrors, ...textErrors],
    pending_required: fields.filter((field) => field.required && !field.value && !field.checked).map((field) => field.label),
    review_summary: reviewSummary,
    authorization_risk: Boolean(riskMatch),
    risk_text: riskMatch ? norm(riskMatch[0]) : '',
  };
})()
"""
    )


def click_forward_script() -> str:
    return """
(() => {
  const norm = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const visible = (el) => {
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0 && getComputedStyle(el).visibility !== 'hidden';
  };
  const dialog = [...document.querySelectorAll('[role="dialog"], dialog, .jobs-easy-apply-modal')].filter(visible).at(-1);
  if (!dialog) return { clicked: false, reason: 'no_dialog' };
  const buttons = [...dialog.querySelectorAll('button')].filter((button) => visible(button) && !button.disabled);
  const target = buttons.find((button) => /^Avan|^Aval|^Next|^Review/i.test(norm(button.innerText || '')));
  if (!target) return { clicked: false, reason: 'forward_not_found', buttons: buttons.map((button) => norm(button.innerText || '')) };
  target.click();
  return { clicked: true, text: norm(target.innerText || '') };
})()
"""


def click_dialog_button_script(pattern: str) -> str:
    payload = json.dumps({'pattern': pattern})
    return (
        '(() => {\nconst opts = '
        + payload
        + """;
  const norm = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const visible = (el) => {
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0 && getComputedStyle(el).visibility !== 'hidden';
  };
  const dialog = [...document.querySelectorAll('[role="dialog"], dialog, .jobs-easy-apply-modal')].filter(visible).at(-1);
  if (!dialog) return { clicked: false, reason: 'no_dialog' };
  const regex = new RegExp(opts.pattern, 'i');
  const target = [...dialog.querySelectorAll('button')].find((button) => visible(button) && !button.disabled && regex.test(norm(button.innerText || button.getAttribute('aria-label') || '')));
  if (!target) return { clicked: false, reason: 'button_not_found' };
  target.click();
  return { clicked: true, text: norm(target.innerText || target.getAttribute('aria-label') || '') };
})()
"""
    )


def fill_questions_script(answers: list[JsonObject]) -> str:
    payload = json.dumps({'answers': answers})
    return (
        '(() => {\nconst opts = '
        + payload
        + """;
  const norm = (value) => (value || '').replace(/\\s+/g, ' ').trim();
  const lower = (value) => norm(value).toLowerCase();
  const visible = (el) => {
    const rect = el.getBoundingClientRect();
    return rect.width > 0 && rect.height > 0 && getComputedStyle(el).visibility !== 'hidden';
  };
  const setValue = (el, value) => {
    const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
      || Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value')?.set;
    if (setter) setter.call(el, String(value));
    else el.value = String(value);
    el.dispatchEvent(new InputEvent('input', { bubbles: true, inputType: 'insertReplacementText', data: String(value) }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    el.dispatchEvent(new Event('blur', { bubbles: true }));
  };
  const dialog = [...document.querySelectorAll('[role="dialog"], dialog, .jobs-easy-apply-modal')].filter(visible).at(-1);
  if (!dialog) return { success: false, filled: [], unfilled: opts.answers, ambiguous: [], blockers: [], reason: 'no_dialog' };
  const filled = [];
  const unfilled = [];
  const ambiguous = [];
  for (const answer of opts.answers) {
    const needle = lower(answer.question_contains || '');
    const controls = [...dialog.querySelectorAll('input, textarea, select')].filter((el) => {
      const groupText = lower(el.closest('fieldset, .jobs-easy-apply-form-section__grouping, div')?.innerText || '');
      return groupText.includes(needle);
    });
    if (!needle || controls.length === 0) {
      unfilled.push({ question_contains: answer.question_contains || '', reason: 'no_match' });
      continue;
    }
    const textControl = controls.find((el) => visible(el) && (el.matches('input[type="text"], input:not([type]), textarea') || el.tagName === 'TEXTAREA'));
    if (answer.value !== undefined && textControl) {
      setValue(textControl, answer.value);
      filled.push({ question_contains: answer.question_contains || '', value: String(answer.value) });
      continue;
    }
    const optionText = lower(answer.option_text || answer.value || '');
    const radios = controls.filter((el) => el.matches('input[type="radio"]'));
    if (optionText && radios.length > 0) {
      const groupText = controls.map((el) => norm(el.closest('fieldset, .jobs-easy-apply-form-section__grouping, div')?.innerText || '')).join('\\n');
      const optionLines = groupText.split(/\\n+/)
        .map((line) => norm(line))
        .filter((line) => line && line.length < 80 && !line.includes('?') && !line.includes('*'));
      const optionIndex = optionLines.findIndex((line) => lower(line) === optionText);
      const targetIndex = optionIndex >= 0 ? Math.min(optionIndex, radios.length - 1) : -1;
      if (targetIndex >= 0) {
        radios[targetIndex].click();
        radios[targetIndex].dispatchEvent(new Event('change', { bubbles: true }));
        filled.push({ question_contains: answer.question_contains || '', option_text: answer.option_text || String(answer.value || '') });
        continue;
      }
    }
    ambiguous.push({ question_contains: answer.question_contains || '', matches: controls.length });
  }
  const text = dialog.innerText || '';
  const blockerMatches = [...text.matchAll(/.{0,80}(W2|GC Holder|Green Card|US Citizen|C2C|1099|sponsorship|visa|work authorization|no sponsorship).{0,120}/gi)].map((match) => norm(match[0]));
  return { success: unfilled.length === 0 && ambiguous.length === 0, filled, unfilled, ambiguous, blockers: [...new Set(blockerMatches)] };
})()
"""
    )
