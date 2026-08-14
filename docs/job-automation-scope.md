# Job Search and Application Scope

## Product objective

Pydoll MCP is a browser MCP for discovering job opportunities and completing
authorized job applications. Its primary workflow is:

```text
search -> inspect opportunity -> prepare application -> review -> authorized submit -> evidence
```

The default `jobs` profile exposes the smallest practical surface for this
workflow. It keeps browser ownership, tab lifecycle, semantic interaction,
form verification, uploads, waits, security handoffs, and evidence together so
an agent can operate a real application without learning DOM, frame, or open
shadow-DOM internals.

## Supported portal model

- LinkedIn has specialized search, result, job snapshot, Easy Apply, upload,
  confirmation, and recruiter-message tools.
- External ATS portals such as Greenhouse, Workable, and Lever use explicit
  navigation plus the semantic surface and form workflow tools.
- `external_ats_multistep` is the default preset for a known external ATS flow.
- Open shadow roots are resolved automatically. Closed shadow roots and
  inaccessible cross-origin frames produce an explicit handoff or partial
  discovery result.

No Indeed-specific adapter or cross-portal search abstraction is part of this
scope. A new adapter requires observed portal behavior, fixtures, and a
separate contract decision.

## Application contract

Applications use the following sequence:

1. `form_preflight` performs read-only discovery and reports blockers,
   missing candidate data, security controls, attestations, and upload state.
2. `form_prepare` applies only caller-provided facts and explicitly planned
   choices, uploads, and intermediate transitions. It never submits the final
   application.
3. `form_review` returns a compact redacted review and may issue a single-use
   review token when the form is consistent.
4. `form_submit_after_review` revalidates the token, form fingerprint, document
   generation, mutation epoch, required fields, security state, and primary
   action before one authorized click.
5. `submission_wait_for_confirmation` classifies the result. URL changes,
   modal disappearance, or browser chrome text alone are not confirmation.

Candidate facts are supplied by the caller. The MCP never invents salary,
address, authorization, demographic information, experience, consent, or
attestation answers.

## Safety boundaries

The MCP never bypasses CAPTCHA, reCAPTCHA, hCaptcha, Turnstile, 2FA, OTP,
login, payment, biometric checks, identity verification, legal attestations,
sensitive consent, or other portal security controls. These states return a
structured handoff for the candidate.

The MCP does not generate resumes or cover letters, maintain an external
application tracker, read email, or infer that a submission succeeded without
visible application evidence.

## Exposure profiles

| Profile | Lifecycle | Purpose |
| --- | --- | --- |
| `jobs` | Recommended | Focused job search and application workflow, 90 tools |
| `full` | Compatibility | Complete 151-tool catalog, including advanced browser diagnostics |
| `agent` | Legacy | Existing 73-tool general browser profile |
| `linkedin` | Legacy | Existing 89-tool agent plus LinkedIn profile |

New clients should use `jobs`. Existing clients can request `agent`,
`linkedin`, or `full` explicitly. The project name and package version remain
unchanged while the default product objective is realigned.
