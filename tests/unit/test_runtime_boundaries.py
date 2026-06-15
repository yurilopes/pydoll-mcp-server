"""Contracts for dynamic Pydoll and CDP response boundaries."""

from __future__ import annotations

import pytest
from pydoll.browser.tab import Tab
from pydoll.elements.web_element import WebElement
from pydoll.protocol.runtime.methods import CallFunctionOnResponse
from pydoll.protocol.runtime.types import CallArgument, SerializationOptions

from pydoll_mcp_server.browser.pydoll_compat import (
    get_element_attribute,
    get_element_text,
    get_tab_title,
    get_tab_url,
    is_element_visible,
)
from pydoll_mcp_server.browser.script_utils import (
    InvalidScriptResponseError,
    extract_script_response,
    extract_script_value,
)

pytestmark = pytest.mark.unit


class FailingTab(Tab):
    def __init__(self) -> None:
        pass

    @property
    async def current_url(self) -> str:
        raise RuntimeError('url unavailable')

    @property
    async def title(self) -> str:
        raise RuntimeError('title unavailable')


class FailingElement(WebElement):
    def __init__(self) -> None:
        pass

    @property
    async def text(self) -> str:
        raise RuntimeError('text unavailable')

    def get_attribute(self, name: str) -> str:
        raise RuntimeError(f'attribute unavailable: {name}')

    async def execute_script(
        self,
        script: str,
        *,
        arguments: list[CallArgument] | None = None,
        silent: bool | None = None,
        return_by_value: bool | None = None,
        generate_preview: bool | None = None,
        user_gesture: bool | None = None,
        await_promise: bool | None = None,
        execution_context_id: int | None = None,
        object_group: str | None = None,
        throw_on_side_effect: bool | None = None,
        unique_context_id: str | None = None,
        serialization_options: SerializationOptions | None = None,
    ) -> CallFunctionOnResponse:
        raise RuntimeError('visibility unavailable')


@pytest.mark.asyncio
async def test_required_pydoll_reads_do_not_hide_runtime_failures() -> None:
    tab = FailingTab()
    element = FailingElement()

    with pytest.raises(RuntimeError, match='url unavailable'):
        await get_tab_url(tab)
    with pytest.raises(RuntimeError, match='title unavailable'):
        await get_tab_title(tab)
    with pytest.raises(RuntimeError, match='text unavailable'):
        await get_element_text(element)
    with pytest.raises(RuntimeError, match='attribute unavailable'):
        get_element_attribute(element, 'name')
    with pytest.raises(RuntimeError, match='visibility unavailable'):
        await is_element_visible(element)


@pytest.mark.parametrize('response', [None, [], {'result': 'invalid'}, {'result': {'result': 'invalid'}}])
def test_script_response_rejects_invalid_shapes(response: object) -> None:
    with pytest.raises(InvalidScriptResponseError):
        extract_script_value(response)


def test_script_response_extracts_value_and_full_result() -> None:
    response = {'result': {'result': {'type': 'string', 'value': 'hello'}}}

    assert extract_script_value(response) == 'hello'
    assert extract_script_response(response) == {'type': 'string', 'value': 'hello'}
