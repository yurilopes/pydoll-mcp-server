"""Safe profile metadata index backed by runtime_dir/profiles/index.json."""

from __future__ import annotations

import contextlib
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TypeGuard
from urllib.parse import urlparse

from pydoll_mcp_server.browser.models import ProfileInfo, ProfileMode
from pydoll_mcp_server.config import get_config


@dataclass
class ProfileIndexEntry:
    profile_id: str
    owner_client_id: str
    mode: str
    created_at: float
    last_used_at: float = 0.0
    last_urls_redacted: list[str] = field(default_factory=lambda: [])
    site_hints: list[str] = field(default_factory=lambda: [])
    display_name: str = ''
    path_kind: str = 'managed_persistent'
    is_locked: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            'profile_id': self.profile_id,
            'owner_client_id': self.owner_client_id,
            'mode': self.mode,
            'created_at': self.created_at,
            'last_used_at': self.last_used_at,
            'last_urls_redacted': list(self.last_urls_redacted),
            'site_hints': list(self.site_hints),
            'display_name': self.display_name,
            'path_kind': self.path_kind,
            'is_locked': self.is_locked,
        }

    @staticmethod
    def from_dict(data: object) -> ProfileIndexEntry:
        if not _is_dict_obj(data):
            return ProfileIndexEntry(profile_id='', owner_client_id='', mode='', created_at=0.0)
        d: dict[str, object] = {str(k): v for k, v in data.items()}
        return ProfileIndexEntry(
            profile_id=str(d.get('profile_id', '')),
            owner_client_id=str(d.get('owner_client_id', '')),
            mode=str(d.get('mode', '')),
            created_at=float(str(d.get('created_at', 0))),
            last_used_at=float(str(d.get('last_used_at', 0))),
            last_urls_redacted=_safe_str_list(d.get('last_urls_redacted', [])),
            site_hints=_safe_str_list(d.get('site_hints', [])),
            display_name=str(d.get('display_name', '')),
            path_kind=str(d.get('path_kind', '')),
            is_locked=bool(d.get('is_locked', False)),
        )


def _safe_str_list(value: object) -> list[str]:
    if not _is_list_obj(value):
        return []
    result: list[str] = []
    for item in value:
        if isinstance(item, str):
            result.append(item)
    return result


def _is_list_obj(value: object) -> TypeGuard[list[object]]:
    return isinstance(value, list)


def _is_dict_obj(value: object) -> TypeGuard[dict[object, object]]:
    return isinstance(value, dict)


class ProfileIndex:
    def __init__(self) -> None:
        config = get_config()
        self._index_dir = config.profiles_dir
        self._index_dir.mkdir(parents=True, exist_ok=True)
        self._index_path = self._index_dir / 'index.json'
        self._entries: dict[str, ProfileIndexEntry] = {}
        self._load()

    def _load(self) -> None:
        if not self._index_path.exists():
            return
        try:
            raw: object = json.loads(self._index_path.read_text(encoding='utf-8'))
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            return
        if not _is_list_obj(raw):
            return
        for item in raw:
            if _is_dict_obj(item):
                entry = ProfileIndexEntry.from_dict(item)
                if entry.profile_id:
                    self._entries[entry.profile_id] = entry

    def _save(self) -> None:
        data = [entry.to_dict() for entry in self._entries.values()]
        with contextlib.suppress(OSError):
            self._index_path.write_text(json.dumps(data, indent=2), encoding='utf-8')

    def discover_preserved_temps(self, client_id: str = '') -> None:
        config = get_config()
        tmp_root = config.tmp_dir
        if not tmp_root.exists():
            return
        for entry_path in sorted(tmp_root.iterdir()):
            if not entry_path.is_dir():
                continue
            dir_client_id = entry_path.name
            if client_id and dir_client_id != client_id:
                continue
            for profile_path in sorted(entry_path.iterdir()):
                if not profile_path.is_dir():
                    continue
                if not profile_path.name.startswith('profile_'):
                    continue
                profile_id = f'preserved_{dir_client_id}_{profile_path.name}'
                if self._entries.get(profile_id):
                    continue
                hints = _extract_site_hints_from_disk(profile_path)
                self._entries[profile_id] = ProfileIndexEntry(
                    profile_id=profile_id,
                    owner_client_id=dir_client_id,
                    mode='temporary',
                    created_at=profile_path.stat().st_mtime,
                    last_used_at=profile_path.stat().st_mtime,
                    display_name=profile_path.name,
                    site_hints=hints,
                    path_kind='preserved_temporary',
                )

    def upsert(self, profile_id: str, entry: ProfileIndexEntry) -> None:
        entry.profile_id = profile_id
        self._entries[profile_id] = entry
        self._save()

    def get(self, profile_id: str) -> ProfileIndexEntry | None:
        return self._entries.get(profile_id)

    def list_all(self, owner_client_id: str = '') -> list[ProfileIndexEntry]:
        if owner_client_id:
            return [e for e in self._entries.values() if e.owner_client_id == owner_client_id]
        return list(self._entries.values())

    def remove(self, profile_id: str) -> None:
        self._entries.pop(profile_id, None)
        self._save()

    def update_visited(self, profile_id: str, url: str) -> None:
        entry = self._entries.get(profile_id)
        if entry is None:
            return
        entry.last_used_at = time.time()
        redacted = redact_url(url)
        domain = extract_domain(url)
        if redacted and redacted not in entry.last_urls_redacted:
            entry.last_urls_redacted.insert(0, redacted)
            entry.last_urls_redacted = entry.last_urls_redacted[:5]
        if domain and domain not in entry.site_hints:
            entry.site_hints.insert(0, domain)
            entry.site_hints = entry.site_hints[:10]
        self._save()

    def find_matching(
        self, owner_client_id: str, site_hint: str, mode_filter: str | None = None
    ) -> list[ProfileIndexEntry]:
        self.discover_preserved_temps(client_id=owner_client_id)
        normalized = normalize_site_hint(site_hint)
        matches: list[ProfileIndexEntry] = []
        for entry in self._entries.values():
            if entry.owner_client_id != owner_client_id:
                continue
            if mode_filter and entry.mode != mode_filter:
                continue
            if entry.site_hints:
                for hint in entry.site_hints:
                    if hint == normalized or hint.endswith('.' + normalized) or normalized.endswith('.' + hint):
                        matches.append(entry)
                        break
            elif entry.path_kind == 'preserved_temporary':
                matches.append(entry)
        return sorted(matches, key=lambda e: e.last_used_at, reverse=True)


def _extract_site_hints_from_disk(profile_dir: Path) -> list[str]:
    hints: list[str] = []
    for filename in ('Last Tabs', 'Last Session'):
        candidate = profile_dir / filename
        if not candidate.exists():
            continue
        try:
            raw = candidate.read_bytes()
            text = raw.decode('utf-8', errors='replace')
            import re

            urls = re.findall(r'https?://[^\s"\\\\]+', text)
            domains: set[str] = set()
            for u in urls[:20]:
                d = extract_domain(u)
                if d:
                    domains.add(d)
            hints = sorted(domains)[:5]
            if hints:
                break
        except (OSError, UnicodeDecodeError):
            pass
    return hints


def redact_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return ''
        path = parsed.path[:100] if parsed.path else ''
        return f'{parsed.scheme}://{parsed.netloc}{path}'
    except (ValueError, TypeError):
        return ''


def extract_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            return ''
        host = parsed.netloc
        if ':' in host:
            host = host.rsplit(':', 1)[0]
        return host.lower()
    except (ValueError, TypeError):
        return ''


def normalize_site_hint(site_hint: str) -> str:
    return site_hint.strip().lower().split(':')[0].split('/')[0]


def create_entry(client_id: str, profile_info: ProfileInfo) -> ProfileIndexEntry:
    return ProfileIndexEntry(
        profile_id=profile_info.profile_id,
        owner_client_id=client_id,
        mode=profile_info.mode.value,
        created_at=time.time(),
        last_used_at=time.time(),
        path_kind=_path_kind_for_mode(profile_info.mode),
    )


def _path_kind_for_mode(mode: ProfileMode) -> str:
    if mode == ProfileMode.PERSISTENT:
        return 'managed_persistent'
    return 'managed_temporary'


_index_singleton: ProfileIndex | None = None


def get_profile_index() -> ProfileIndex:
    global _index_singleton
    if _index_singleton is None:
        _index_singleton = ProfileIndex()
    return _index_singleton
