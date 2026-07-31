"""Browser-side scripts for LinkedIn recruiter messaging."""

from __future__ import annotations

import json

from pydoll_mcp_server.tools.linkedin_state_scripts import shared_state_helpers_script


def recruiter_surface_script() -> str:
    return _script(
        """
  const composer = [...document.querySelectorAll(
    'textarea, [contenteditable="true"], .msg-form__contenteditable'
  )].find((element) => visible(element));
  const composerForm = composer?.closest('form');
  const sendButton = [...(composerForm?.querySelectorAll('button, [role="button"]') || [])].find((button) => {
    if (!visible(button) || !enabled(button)) return false;
    const value = fold(controlLabel(button));
    return button.getAttribute('type') === 'submit'
      || /^(send|enviar)$/.test(value)
      || /send message|enviar mensagem/.test(value);
  });
  if (location.pathname.includes('/messaging/compose/') || composer) {
    return {
      success: true,
      recruiter_found: true,
      resolution: 'composer',
      composer_present: Boolean(composer),
      composer_selector: composer ? cssPath(composer) : '',
      send_button_selector: sendButton ? cssPath(sendButton) : '',
      url: location.href,
    };
  }
  const root = findDetailRoot(document);
  if (!root) return { success: true, recruiter_found: false, resolution: 'no_job_detail' };
  const visibleLinks = [...root.querySelectorAll('a[href*="/in/"]')].filter((link) => {
    const href = link.getAttribute('href') || '';
    return visible(link) && !href.includes('/company/') && !link.closest('nav, header, [role="navigation"]');
  });
  const candidates = [];
  for (const link of visibleLinks) {
    const text = norm(link.innerText || link.textContent || '');
    const label = controlAria(link);
    const card = link.closest('.hirer-card, [data-view-name="hirer-card"], .job-details-hiring-team, section, li');
    const container = card || link.parentElement;
    const context = norm(container?.innerText || '');
    const messageRoot = card || root;
    const messageButton = [...messageRoot.querySelectorAll('button, a[role="button"], a')].find((button) => {
      if (!visible(button) || !enabled(button)) return false;
      const value = fold(controlLabel(button));
      return /^(message|enviar mensagem)$/.test(value) || /send message|enviar mensagem/.test(value);
    });
    if (text.length > 1 && messageButton) {
      candidates.push({
        name: text,
        profile_url: link.href || '',
        headline: context.replace(text, '').trim().slice(0, 240),
        context: context.slice(0, 500),
        message_button_selector: cssPath(messageButton),
        message_href: messageButton.href || '',
      });
    }
  }
  const unique = [...new Map(candidates.map((item) => [item.profile_url || item.name, item])).values()];
  if (unique.length !== 1) {
    return {
      success: true,
      recruiter_found: false,
      resolution: unique.length ? 'ambiguous' : 'not_found',
      candidates: unique,
    };
  }
  const recruiter = unique[0];
  return {
    success: true,
    recruiter_found: true,
    resolution: 'unique',
    recruiter_name: recruiter.name,
    recruiter_profile_url: recruiter.profile_url,
    recruiter_headline: recruiter.headline,
    recruiter_context: recruiter.context,
    message_button_selector: recruiter.message_button_selector,
    message_href: recruiter.message_href,
    composer_present: Boolean(composer),
    composer_selector: composer ? cssPath(composer) : '',
    send_button_selector: sendButton ? cssPath(sendButton) : '',
    job_id: selectedJobIdFromUrl(),
  };
"""
    )


def recruiter_confirmation_script(message: str) -> str:
    payload = json.dumps(message[:120])
    return _script(
        f"""
  const needle = fold({payload});
  const successText = [...document.querySelectorAll(
    '[role="alert"], [role="status"], .artdeco-toast-item, .msg-s-message-list__event'
  )]
    .filter((element) => visible(element))
    .map((element) => norm(element.innerText || element.textContent || ''))
    .filter(Boolean);
  const messageVisible = [...document.querySelectorAll(
    '.msg-s-event-listitem, .msg-s-message-list__event, [data-event-urn], [role="main"] p'
  )]
    .filter((element) => visible(element))
    .some((element) => fold(element.innerText || element.textContent || '').includes(needle));
  const confirmationText = successText.find((text) =>
    /message sent|mensagem enviada|sent successfully|enviada com sucesso/.test(fold(text))
  ) || '';
  return {{
    success: true,
    confirmation_observed: Boolean(confirmationText || messageVisible),
    confirmation_text: confirmationText || (messageVisible ? 'Message visible in conversation' : ''),
    message_visible: messageVisible,
    toast_messages: successText,
    composer_present: [...document.querySelectorAll(
      'textarea, [contenteditable="true"][role="textbox"], .msg-form__contenteditable'
    )].some((element) => visible(element)),
    url: location.href,
  }};
"""
    )


def _script(body: str) -> str:
    return '(() => {\n' + shared_state_helpers_script() + body + '\n})()'
