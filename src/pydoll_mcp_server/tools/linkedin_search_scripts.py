"""JavaScript builders for LinkedIn Jobs search and evidence helpers."""

from __future__ import annotations

import json

from pydoll_mcp_server.tools.linkedin_state_scripts import shared_state_helpers_script


def search_results_script(max_results: int) -> str:
    payload = json.dumps({'max_results': max_results})
    return _script(
        f"""
  const opts = {payload};
  return collectLinkedInJobs(opts.max_results);
""",
        include_collector=True,
    )


def page_snapshot_script(max_results: int) -> str:
    payload = json.dumps({'max_results': max_results})
    return _script(
        f"""
  const opts = {payload};
  const base = collectLinkedInJobs(opts.max_results);
  const detailRoot = findDetailRoot(document);
  const detail = detailRoot ? jobSnapshotFromRoot(detailRoot) : emptyJobSnapshot();
  const selectedId = detail.linkedin_job_id || selectedJobIdFromUrl() || '';
  const selectedResult = base.results.find((item) => item.linkedin_job_id === selectedId);
  if (selectedResult) {{
    detail.role = detail.role || selectedResult.title;
    detail.company = detail.company || selectedResult.company;
    detail.location = detail.location || selectedResult.location;
    if (detail.application_state === 'unknown' && selectedResult.easy_apply_hint) {{
      detail.application_state = 'not_started';
      detail.button_state = 'easy_apply';
      detail.easy_apply_available = true;
    }}
  }}
  const hasNextPage = visibleControls(document).some((el) => !el.disabled && /^(proxima|next|seguinte)$/.test(fold(controlLabel(el))));
  return {{
    ...base,
    selected_job_id: selectedId,
    detail_job_snapshot: detail,
    detail_panel_present: Boolean(detailRoot && !isDirectJobView()),
    easy_apply_button_state: detail.button_state || 'unknown',
    detail_url: detail.canonical_url || location.href,
    list_count: base.count,
    has_next_page: hasNextPage,
    detail_surface: isDirectJobView() ? 'direct' : detailRoot ? 'panel' : 'none',
  }};
""",
        include_collector=True,
    )


def open_result_target_script(linkedin_job_id: str, index: int | None) -> str:
    payload = json.dumps({'linkedin_job_id': linkedin_job_id, 'index': index})
    return _script(
        f"""
  const opts = {payload};
  const results = collectLinkedInJobs(100).results;
  let target = null;
  if (opts.linkedin_job_id) target = results.find((item) => item.linkedin_job_id === opts.linkedin_job_id) || null;
  else if (Number.isInteger(opts.index)) target = results[opts.index] || null;
  if (!target) return {{ success: false, clicked: false, reason: 'result_not_found', results_count: results.length }};
  const cards = [...new Set([
    ...document.querySelectorAll([
      '[data-job-id]',
      '[data-occludable-job-id]',
      '[data-entity-urn*="jobPosting"]',
      '.job-card-container',
      '.jobs-search-results__list-item',
      '.base-search-card',
      '.job-search-card',
      '.scaffold-layout__list-item',
    ].join(', ')),
    ...[...document.querySelectorAll('a[href*="/jobs/view/"]')]
      .map((link) => jobCardForLink(link))
      .filter(Boolean),
  ])].filter((card) => visible(card));
  const card = cards.find((item) => item.getAttribute('data-job-id') === target.linkedin_job_id
    || item.getAttribute('data-occludable-job-id') === target.linkedin_job_id
    || item.querySelector(`a[href*="/jobs/view/${{CSS.escape(target.linkedin_job_id)}}/"]`));
  if (!card) return {{ success: true, clicked: false, reason: 'click_target_not_found', target }};
  const link = card.querySelector(`a[href*="/jobs/view/${{CSS.escape(target.linkedin_job_id)}}/"]`);
  return {{
    success: true,
    clicked: false,
    target,
    search_context: location.pathname.includes('/jobs/search/'),
    card: controlInfo(card),
    link: link ? controlInfo(link) : {{}},
  }};
""",
        include_collector=True,
    )


def evidence_script(include_review: bool) -> str:
    payload = json.dumps({'include_review': include_review})
    return _script(
        f"""
  const opts = {payload};
  const detailRoot = findDetailRoot(document);
  const job = detailRoot ? jobSnapshotFromRoot(detailRoot) : (isDirectJobView() ? jobSnapshotFromRoot(document) : emptyJobSnapshot());
  const surface = findApplicationSurface();
  const applicationRoot = surface.root && surface.kind !== 'confirmation' ? surface.root : null;
  const applicationText = applicationRoot ? rootText(applicationRoot) : '';
  const fields = applicationRoot
    ? [...applicationRoot.querySelectorAll('input, textarea, select')]
      .filter((el) => visible(el) || ['radio', 'checkbox'].includes(fold(el.getAttribute('type') || '')))
      .map((el, index) => fieldSnapshot(el, applicationRoot, index))
    : [];
  const answersByKey = new Map();
  for (const field of fields) {{
    if (!field.label && !field.group_text) continue;
    const key = field.question_key || field.label;
    const answer = answersByKey.get(key) || {{ question: field.label || field.group_text, answer: '' }};
    answer.answer = field.selected_option || field.value || field.selected_text?.[0] || answer.answer;
    answersByKey.set(key, answer);
  }}
  const resumeLines = String(applicationText || rootText(document)).split(/\\n+/).map(norm).filter((line) => /\\.(?:pdf|docx?)$/i.test(line));
  const resumeFilename = resumeLines[0]?.replace(/^pdf\\s+/i, '').replace(/^curriculo\\s*:?\\s*/i, '') || '';
  const reviewAnswers = reviewAnswersFor(applicationText);
  const reviewReady = Boolean(applicationRoot && /revise sua candidatura|review/.test(fold(applicationText))
    && [...applicationRoot.querySelectorAll('button, [role="button"]')].some((button) => isSubmitLabel(controlLabel(button))));
  const risk = job.risk_text || riskTextFor(applicationText);
  const confirmationText = job.application_state === 'submitted'
    ? job.application_state_text
    : norm(rootText(document).match(/(Se candidatou agora|Candidatura enviada|Application submitted).{{0,80}}/i)?.[0] || '');
  const applicationState = confirmationText || surface.kind === 'confirmation'
    ? 'submitted'
    : reviewReady || applicationRoot
      ? 'draft'
      : job.application_state || 'unknown';
  return {{
    success: true,
    platform: 'linkedin',
    linkedin_job_id: job.linkedin_job_id || selectedJobIdFromUrl() || '',
    canonical_url: job.canonical_url || '',
    company: job.company || '',
    role: job.role || '',
    location: job.location || '',
    application_state: applicationState,
    easy_apply_available: Boolean(job.easy_apply_available || applicationRoot),
    authorization_risk: Boolean(job.authorization_risk || risk),
    risk_text: risk,
    resume_filename: resumeFilename,
    answers: opts.include_review
      ? (answersByKey.size ? [...answersByKey.values()] : reviewAnswers)
      : [],
    confirmation_text: confirmationText,
    surface: surface.kind,
    captured_at_unix: Math.floor(Date.now() / 1000),
  }};
""",
    )


def _script(body: str, include_collector: bool = False) -> str:
    collector = _collector_script() if include_collector else ''
    return '(() => {\n' + shared_state_helpers_script() + collector + body + '\n})()'


def _collector_script() -> str:
    return r"""
function collectLinkedInJobs(maxResults) {
  const params = new URL(location.href).searchParams;
  const selectors = [
    '[data-job-id]',
    '[data-occludable-job-id]',
    '[data-entity-urn*="jobPosting"]',
    '.job-card-container',
    '.jobs-search-results__list-item',
    '.base-search-card',
    '.job-search-card',
    '.scaffold-layout__list-item',
  ];
  const cards = [...new Set([
    ...selectors.flatMap((selector) => [...document.querySelectorAll(selector)]),
    ...[...document.querySelectorAll('a[href*="/jobs/view/"]')]
      .map((link) => jobCardForLink(link))
      .filter(Boolean),
  ])];
  const byId = new Map();
  for (const card of cards) {
    const link = [...card.querySelectorAll('a[href*="/jobs/view/"]')][0]
      || (card.matches('a[href*="/jobs/view/"]') ? card : null);
    if (!visible(card) && !visible(link)) continue;
    const idFromUrl = link?.href.match(/\/jobs\/view\/(\d+)/)?.[1] || '';
    const entityId = card.getAttribute('data-entity-urn')?.match(/jobPosting:(\d+)/)?.[1] || '';
    const id = card.getAttribute('data-job-id') || card.getAttribute('data-occludable-job-id')
      || entityId || idFromUrl;
    if (!id || byId.has(id)) continue;
    const rawText = card.innerText || '';
    const text = norm(rawText);
    const lines = rawText.split(/\n+/).map(norm).filter(Boolean);
    const title = norm(link?.innerText || card.querySelector('[aria-label*="title"], strong, h3, h4')?.innerText || lines[0] || '');
    const company = lines.find((line) => line !== title && !/promoted|promovida|sponsored|candidatura|easy apply/i.test(line)) || '';
    const locationLine = lines.find((line) => /remote|remoto|united states|estados unidos|brazil|brasil|europe|europa/i.test(line)) || '';
    byId.set(id, {
      linkedin_job_id: id,
      title,
      company,
      location: locationLine,
      url: `https://www.linkedin.com/jobs/view/${id}/`,
      visible_text: text.slice(0, 800),
      // The f_AL query filter is only a request to LinkedIn, not evidence that
      // this particular card actually exposes Easy Apply.
      easy_apply_hint: /candidatura simplificada|easy apply/i.test(fold(text)),
      remote_hint: /remote|remoto/i.test(fold(text)) || params.get('f_WT') === '2',
      sponsored: /promoted|promovida|sponsored/i.test(fold(text)),
    });
    if (byId.size >= maxResults) break;
  }
  const pageText = rootText(document);
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
    no_results: /nenhum resultado|no matching jobs|no results/i.test(fold(pageText)),
  };
}

function jobCardForLink(link) {
  if (!link) return null;
  const semantic = link.closest([
    '[data-job-id]',
    '[data-occludable-job-id]',
    '[data-entity-urn*="jobPosting"]',
    '.job-card-container',
    '.jobs-search-results__list-item',
    '.base-search-card',
    '.job-search-card',
    '.scaffold-layout__list-item',
  ].join(', '));
  if (semantic) return semantic;
  let current = link.parentElement;
  for (let depth = 0; current && depth < 8; depth += 1, current = current.parentElement) {
    const links = current.querySelectorAll('a[href*="/jobs/view/"]');
    if (links.length === 1 && norm(current.innerText || '').length > norm(link.innerText || '').length) return current;
  }
  return link;
}
"""
