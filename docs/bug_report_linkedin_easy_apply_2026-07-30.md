# Pydoll MCP Server - LinkedIn Tool Profile: Bug Report

**Date**: 2026-07-30
**Environment**: Windows 11, `linkedin` tool profile, visible Chrome with authenticated LinkedIn session
**Server**: `python -m pydoll_mcp_server.cli --host 127.0.0.1 --port 8765 --tool-profile linkedin`

---

## Bug 1: `linkedin_easy_apply_open` resolves wrong "Candidatura simplificada" element

### Severity
High - blocks the primary LinkedIn Easy Apply workflow.

### Symptom
The tool resolves the search filter toggle (`#searchFilter_applyWithLinkedin`, `role="radio"`, `aria="Filtro Candidatura simplificada."`) instead of the actual Easy Apply button on the job detail panel (`tag="button"`, `aria="Usar a candidatura simplificada para esta vaga"`). This causes the tool to toggle the Easy Apply search filter rather than opening the application form.

### Expected behavior
The tool should find and click the Easy Apply button on the currently selected job's detail panel (right side of the LinkedIn Jobs search page), which triggers the Easy Apply modal.

### Steps to reproduce
1. Navigate to a LinkedIn Jobs search with Easy Apply filter active:
   ```
   https://www.linkedin.com/jobs/search/?keywords=AI%20Engineer&location=Canada&f_WT=2&f_AL=true
   ```
2. Click a job listing to open its detail panel (e.g., via `linkedin_jobs_open_result` with `index=0`)
3. Call `linkedin_easy_apply_open`

### Actual result
```json
{
  "error_code": "NO_EFFECT",
  "details": {
    "resolved": {
      "text": "Candidatura simplificada",
      "aria": "Filtro Candidatura simplificada.",
      "tag": "button",
      "role": "radio",
      "id": "searchFilter_applyWithLinkedin"
    }
  }
}
```

### Expected resolved element
```json
{
  "text": "Candidatura simplificada - vaga de <Job Title> na <Company>",
  "aria": "Usar a candidatura simplificada para esta vaga",
  "tag": "button",
  "role": ""
}
```

### Workaround
Manually locate the correct button by calling `page_get_active_surface` and filtering controls where `name` contains `'candidatura simplificada'` and the element's `aria` attribute does not contain `'Filtro'` or `'filter'`.

### Root cause hypothesis
The tool's element resolution logic matches the first element containing the text "Candidatura simplificada", which is the search filter toggle at the top of the page. It should prefer the button on the job detail panel (right side), or exclude elements with `role="radio"` or `id` containing `searchFilter`.

---

## Bug 2: `linkedin_easy_apply_fill_questions` crashes with empty/invalid response

### Severity
High - completely breaks the MCP session when triggered.

### Symptom
The tool returns an empty response that cannot be parsed as JSON, causing `JSONDecodeError` in the MCP client and terminating the session.

### Steps to reproduce
1. Open an Easy Apply modal (via workaround from Bug 1)
2. Call `linkedin_easy_apply_snapshot` to get the current questions
3. Build an `answers` dict mapping question labels to string values:
   ```json
   {
     "Email address": "yuriabreu.jl@gmail.com",
     "Phone country code": "+55",
     "Mobile phone number": "21998330989"
   }
   ```
4. Call `linkedin_easy_apply_fill_questions` with the `answers` parameter

### Actual result
```
json.decoder.JSONDecodeError: Expecting value: line 1 column 1 (char 0)
```
The MCP client session terminates with an unhandled `ExceptionGroup`.

### Expected behavior
The tool should fill all matching form fields and return a structured success/failure response with counts of filled/unfilled fields.

### Workaround
Use `form_snapshot` to enumerate fields, then fill each individually with `element_fill` or `element_select_option` based on question type. This is fragile because question labels and input types vary between jobs.

---

## Bug 3: `linkedin_easy_apply_submit` fails to observe state transition

### Severity
Medium - has a reliable workaround.

### Symptom
When on the review/final step of Easy Apply (where `is_review_step=true` or `is_final_submit_step=true`), calling `linkedin_easy_apply_submit` with `confirm_submit=true` returns `success=None` with message "LinkedIn submit click produced no observable state transition", even though the submit button is visible and enabled.

### Steps to reproduce
1. Complete all Easy Apply steps until the review/final step
2. Verify `linkedin_easy_apply_snapshot` shows `is_review_step: true` or `is_final_submit_step: true`
3. Call `linkedin_easy_apply_submit` with `confirm_submit: true`

### Actual result
```json
{
  "success": null,
  "message": "LinkedIn submit click produced no observable state transition"
}
```

### Expected behavior
The tool should click the submit button, wait for the confirmation page, and return `success: true` with the confirmation state.

### Workaround
Use `element_click_by_text` with `text="Enviar candidatura"` (Portuguese UI) or "Submit application" (English UI), then verify success by checking `page_get_text` for "enviada" or "submitted".

### Root cause hypothesis
The tool clicks the submit button but does not wait long enough for the post-submit page to load, or the success detection logic does not recognize LinkedIn's Portuguese-language confirmation page (URL changes to `/jobs/search/post-apply/next-best-action/`).

---

## Additional Observations

### Easy Apply form structure varies significantly
Different LinkedIn job postings have different question sets. Common steps include:
1. Contact info (email, phone country code, mobile number)
2. Resume selection (radio buttons for previously uploaded resumes)
3. Experience questions (text inputs for years of experience in specific technologies)
4. Dropdown/select questions (e.g., "Are you comfortable working in a remote setting?")
5. Review step with "Enviar candidatura" (Submit) button

A robust `fill_questions` implementation should handle:
  - `text`, `email`, `number`, `tel` inputs via `element_fill`
  - `select-one` dropdowns via `element_select_option` (matching by visible option text)
  - `radio` groups for single-choice questions
  - Dynamically appearing "Next"/"Review"/"Submit" buttons after all required fields are completed

### Session timeout
After extended use (10+ minutes), some tool calls begin hanging indefinitely. A heartbeat or automatic session refresh may help for long-running application workflows.

### Portuguese locale
LinkedIn's UI is in Portuguese ("Candidatura simplificada", "Avançar", "Enviar candidatura"). The tools should be locale-aware or accept button text as a parameter.

---

## Test Account

- **LinkedIn account**: yuh.lopes@gmail.com
- **Browser profile**: `curriculum` (persistent, managed by Pydoll MCP profiles)
- **Test page**: `https://www.linkedin.com/jobs/search/?keywords=AI%20Engineer&location=Canada&f_WT=2&f_AL=true`
