"""Shared support objects for semantic form workflow operations."""

from __future__ import annotations

import time
from dataclasses import dataclass
from urllib.parse import urlsplit

from pydoll_mcp_server.json_types import JsonObject, get_array, get_bool


@dataclass
class DomainRestriction:
    domain: str
    reason: str
    evidence_text: list[str]
    timestamp: float
    expires_at: float | None
    job_identifiers: list[str]


DOMAIN_RESTRICTIONS: dict[str, DomainRestriction] = {}
_DOMAIN_RESTRICTIONS = DOMAIN_RESTRICTIONS


def normalize_employer_domain(value: str) -> str:
    candidate = value.strip()
    if not candidate:
        return ''
    parsed = urlsplit(candidate if '://' in candidate else f'https://{candidate}')
    return (parsed.hostname or '').lower().rstrip('.')


def record_domain_restriction(
    employer_domain: str,
    reason: str,
    evidence_text: list[str],
    job_identifiers: list[str] | None = None,
    expires_at: float | None = None,
) -> JsonObject:
    domain = normalize_employer_domain(employer_domain)
    if not domain:
        return {'recorded': False, 'reason': 'employer_domain is required'}
    restriction = DomainRestriction(
        domain=domain,
        reason=reason,
        evidence_text=list(evidence_text),
        timestamp=time.time(),
        expires_at=expires_at,
        job_identifiers=list(job_identifiers or []),
    )
    DOMAIN_RESTRICTIONS[domain] = restriction
    return domain_restriction_to_json(restriction)


def active_domain_restriction(domain: str) -> DomainRestriction | None:
    restriction = DOMAIN_RESTRICTIONS.get(normalize_employer_domain(domain))
    if restriction is not None and restriction.expires_at is not None and restriction.expires_at <= time.time():
        DOMAIN_RESTRICTIONS.pop(restriction.domain, None)
        return None
    return restriction


def domain_restriction_to_json(restriction: DomainRestriction) -> JsonObject:
    return {
        'domain': restriction.domain,
        'reason': restriction.reason,
        'evidence_text': list(restriction.evidence_text),
        'timestamp': restriction.timestamp,
        'expires_at': restriction.expires_at,
        'job_identifiers': list(restriction.job_identifiers),
    }


def snapshot_as_surface(snapshot: JsonObject) -> JsonObject:
    return {
        'success': True,
        'surface': 'form',
        'fields': get_array(snapshot, 'fields', []),
        'primary_action': {},
        'security_controls': [],
        'errors': [],
        'warnings': [{'kind': 'fallback', 'message': 'Active surface discovery failed; form snapshot used.'}],
        'partial': get_bool(snapshot, 'partial', False),
    }


__all__ = [
    'DOMAIN_RESTRICTIONS',
    '_DOMAIN_RESTRICTIONS',
    'DomainRestriction',
    'active_domain_restriction',
    'domain_restriction_to_json',
    'normalize_employer_domain',
    'record_domain_restriction',
    'snapshot_as_surface',
]
