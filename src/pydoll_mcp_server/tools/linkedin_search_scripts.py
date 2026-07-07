"""JavaScript builders for LinkedIn Jobs search results."""

from __future__ import annotations

import json


def search_results_script(max_results: int) -> str:
    payload = json.dumps({'max_results': max_results})
    return (
        '(() => {\n'
        + shared_helpers_script()
        + '\n  const opts = '
        + payload
        + """;
  return collectLinkedInJobs(opts.max_results);
})()
"""
    )


def page_snapshot_script(max_results: int) -> str:
    payload = json.dumps({'max_results': max_results})
    return (
        '(() => {\n'
        + shared_helpers_script()
        + '\n  const opts = '
        + payload
        + """;
  const base = collectLinkedInJobs(opts.max_results);
  const detail = jobSnapshotFromRoot(document);
  const selectedId = detail.linkedin_job_id || selectedJobIdFromUrl() || '';
  const selectedResult = base.results.find((item) => item.linkedin_job_id === selectedId);
  if (selectedResult) {
    detail.role = detail.role || selectedResult.title;
    detail.company = detail.company || selectedResult.company;
    detail.location = detail.location || selectedResult.location;
    if (detail.application_state === 'unknown' && selectedResult.easy_apply_hint) {
      detail.application_state = 'not_started';
      detail.button_state = 'easy_apply';
      detail.easy_apply_available = true;
    }
  }
  return {
    ...base,
    selected_job_id: selectedId,
    detail_job_snapshot: detail,
    detail_panel_present: Boolean(document.querySelector('.jobs-search__job-details, .jobs-details, main')),
    easy_apply_button_state: detail.button_state || 'unknown',
    detail_url: detail.canonical_url || location.href,
    list_count: base.count,
    has_next_page: [...document.querySelectorAll('button, a')].some((el) => /Pr[oó]xima|Next/i.test(norm(el.innerText || el.getAttribute('aria-label') || '')) && visible(el)),
  };
})()
"""
    )


def open_result_script(linkedin_job_id: str, index: int | None) -> str:
    payload = json.dumps({'linkedin_job_id': linkedin_job_id, 'index': index})
    return (
        '(() => {\n'
        + shared_helpers_script()
        + '\n  const opts = '
        + payload
        + """;
  const results = collectLinkedInJobs(100).results;
  let target = null;
  if (opts.linkedin_job_id) {
    target = results.find((item) => item.linkedin_job_id === opts.linkedin_job_id) || null;
  } else if (Number.isInteger(opts.index)) {
    target = results[opts.index] || null;
  }
  if (!target) return { success: false, clicked: false, reason: 'result_not_found', results_count: results.length };
  const link = document.querySelector(`a[href*="/jobs/view/${target.linkedin_job_id}/"]`);
  const clickable = link || document.querySelector(`[data-job-id="${CSS.escape(target.linkedin_job_id)}"]`);
  if (!clickable) return { success: true, clicked: false, reason: 'click_target_not_found', target };
  clickable.scrollIntoView({ block: 'center', inline: 'center' });
  clickable.click();
  return { success: true, clicked: true, target };
})()
"""
    )


def evidence_script(include_review: bool) -> str:
    payload = json.dumps({'include_review': include_review})
    return (
        '(() => {\n'
        + shared_helpers_script()
        + '\n  const opts = '
        + payload
        + """;
  const job = jobSnapshotFromRoot(document);
  const dialog = [...document.querySelectorAll('[role="dialog"], dialog, .jobs-easy-apply-modal')].filter(visible).at(-1);
  const dialogText = dialog ? norm(dialog.innerText || '') : '';
  const reviewText = opts.include_review && dialogText ? dialogText : '';
  const resumeMatch = (reviewText || document.body.innerText || '').match(/([^\\s]+\\.(?:pdf|docx?))/i);
  const answers = [];
  if (reviewText) {
    const lines = reviewText.split(/\\n+/).map(norm).filter(Boolean);
    for (let i = 0; i < lines.length - 1; i += 1) {
      if (lines[i].endsWith('?') || /experience|W2|Citizen|sponsorship|authorization/i.test(lines[i])) {
        answers.push({ question: lines[i], answer: lines[i + 1] });
      }
    }
  }
  return {
    success: true,
    platform: 'linkedin',
    linkedin_job_id: job.linkedin_job_id || '',
    canonical_url: job.canonical_url || '',
    company: job.company || '',
    role: job.role || '',
    location: job.location || '',
    application_state: job.application_state || 'unknown',
    easy_apply_available: Boolean(job.easy_apply_available),
    authorization_risk: Boolean(job.authorization_risk),
    risk_text: job.risk_text || '',
    resume_filename: resumeMatch ? resumeMatch[1] : '',
    answers,
    confirmation_text: job.application_state === 'submitted' ? job.application_state_text : '',
    captured_at_unix: Math.floor(Date.now() / 1000),
  };
})()
"""
    )


def shared_helpers_script() -> str:
    return """
function norm(value) {
  return (value || '').replace(/\\s+/g, ' ').trim();
}
function visible(el) {
  const rect = el.getBoundingClientRect();
  const style = getComputedStyle(el);
  return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
}
function selectedJobIdFromUrl() {
  return location.href.match(/\\/jobs\\/view\\/(\\d+)/)?.[1] || new URL(location.href).searchParams.get('currentJobId') || '';
}
function collectLinkedInJobs(maxResults) {
  const params = new URL(location.href).searchParams;
  const cards = [...document.querySelectorAll('li, .job-card-container, .jobs-search-results__list-item, [data-job-id]')];
  const byId = new Map();
  for (const card of cards) {
    if (!visible(card)) continue;
    const link = [...card.querySelectorAll('a[href*="/jobs/view/"]')][0];
    const rawUrl = link?.href || '';
    const idFromUrl = rawUrl.match(/\\/jobs\\/view\\/(\\d+)/)?.[1] || '';
    const id = card.getAttribute('data-job-id') || idFromUrl;
    if (!id || byId.has(id)) continue;
    const rawText = card.innerText || '';
    const text = norm(rawText);
    const lines = rawText.split(/\\n+/).map(norm).filter(Boolean);
    const title = norm(link?.innerText || card.querySelector('[aria-label*="title"], strong')?.innerText || text.split('\\n')[0] || '');
    const company = lines.find((line) => line !== title && !/Promoted|Promovida|Candidatura|Easy Apply/i.test(line)) || '';
    const locationLine = lines.find((line) => /Remote|Remoto|United States|Estados Unidos|Brazil|Brasil|Europe|Europa/i.test(line)) || '';
    byId.set(id, {
      linkedin_job_id: id,
      title,
      company,
      location: locationLine,
      url: `https://www.linkedin.com/jobs/view/${id}/`,
      visible_text: text.slice(0, 800),
      easy_apply_hint: /Candidatura simplificada|Easy Apply/i.test(text) || params.get('f_AL') === 'true',
      remote_hint: /Remote|Remoto/i.test(text) || params.get('f_WT') === '2',
    });
    if (byId.size >= maxResults) break;
  }
  const pageText = document.body.innerText || '';
  return {
    success: true,
    url: location.href,
    keywords: params.get('keywords') || '',
    location: params.get('location') || '',
    filters: {
      remote: params.get('f_WT') === '2',
      easy_apply: params.get('f_AL') === 'true',
      sort_by: params.get('sortBy') === 'R' ? 'recent' : 'relevance',
      date_posted: params.get('f_TPR') || '',
      experience_levels: params.get('f_E') || '',
      job_types: params.get('f_JT') || '',
      geo_id: params.get('geoId') || '',
      start: params.get('start') || '',
    },
    results: [...byId.values()],
    count: byId.size,
    partial: byId.size >= maxResults,
    no_results: /Nenhum resultado|No matching jobs|No results/i.test(pageText),
  };
}
function jobSnapshotFromRoot(root) {
  const text = root.body?.innerText || root.innerText || '';
  const url = new URL(location.href);
  const idMatch = url.pathname.match(/\\/jobs\\/view\\/(\\d+)/);
  const currentJobId = idMatch?.[1] || url.searchParams.get('currentJobId') || '';
  const controls = [...root.querySelectorAll('button, a')].filter(visible).map((el) => ({
    text: norm(el.innerText || ''),
    aria: norm(el.getAttribute('aria-label') || ''),
    disabled: Boolean(el.disabled || el.getAttribute('aria-disabled') === 'true'),
  }));
  const easy = controls.find((item) => /candidatura simplificada|easy apply/i.test(`${item.text} ${item.aria}`));
  const cont = controls.find((item) => /^continuar$/i.test(item.text) || /continue/i.test(item.aria));
  const saved = controls.find((item) => /^salvo$|^saved$/i.test(item.text) || /vaga salva|saved job/i.test(item.aria));
  const submitted = /se candidatou agora|candidatura enviada|application submitted/i.test(text);
  const unavailable = /não aceita mais candidaturas|no longer accepting|vaga encerrada|job closed/i.test(text);
  let applicationState = 'unknown';
  let stateText = '';
  if (submitted) {
    applicationState = 'submitted';
    stateText = norm(text.match(/(Se candidatou agora|Candidatura enviada|Application submitted).{0,80}/i)?.[0] || '');
  } else if (cont || /suas respostas foram salvas|answers were saved/i.test(text)) {
    applicationState = 'draft';
    stateText = cont?.text || 'saved draft';
  } else if (easy) {
    applicationState = 'not_started';
    stateText = easy.text || easy.aria;
  } else if (saved) {
    applicationState = 'saved';
    stateText = saved.text || saved.aria;
  } else if (unavailable) {
    applicationState = 'unavailable';
    stateText = 'unavailable';
  }
  const riskMatch = text.match(/.{0,80}(W2|GC Holder|Green Card|US Citizen|C2C|1099|sponsorship|visa|work authorization|no sponsorship).{0,120}/i);
  const titleParts = document.title.split('|').map(norm).filter(Boolean);
  const isDirectJobView = Boolean(idMatch);
  const pageTitleRole = isDirectJobView && titleParts.length >= 2 && !/LinkedIn/i.test(titleParts[0]) ? titleParts[0] : '';
  const pageTitleCompany = isDirectJobView && titleParts.length >= 2 ? titleParts[1] : '';
  const heading = norm(root.querySelector('.jobs-unified-top-card h1, .job-details-jobs-unified-top-card h1, .jobs-details__main-content h1')?.innerText || '');
  const title = heading && !/notifica/i.test(heading) ? heading : pageTitleRole;
  const company = norm(root.querySelector('.job-details-jobs-unified-top-card__company-name, .job-details-jobs-unified-top-card__primary-description a, .company')?.innerText || pageTitleCompany);
  return {
    success: true,
    linkedin_job_id: currentJobId,
    canonical_url: currentJobId ? `https://www.linkedin.com/jobs/view/${currentJobId}/` : location.href,
    url: location.href,
    role: title,
    company,
    location: norm((text.match(/\\n([^\\n]*Estados Unidos[^\\n]*|[^\\n]*Brasil[^\\n]*|[^\\n]*Remote[^\\n]*|[^\\n]*Remoto[^\\n]*)\\n/) || [])[1] || ''),
    button_state: applicationState === 'not_started' ? 'easy_apply' : applicationState === 'draft' ? 'continue' : applicationState,
    application_state: applicationState,
    application_state_text: stateText,
    easy_apply_available: Boolean(easy || cont),
    easy_apply_button_text: easy?.text || cont?.text || '',
    easy_apply_button_aria: easy?.aria || cont?.aria || '',
    can_continue_easy_apply: Boolean(cont),
    already_applied: submitted,
    application_status: submitted ? 'submitted' : '',
    authorization_risk: Boolean(riskMatch),
    risk_text: riskMatch ? norm(riskMatch[0]) : '',
    description_excerpt: norm(text).slice(0, 2000),
  };
}
"""
