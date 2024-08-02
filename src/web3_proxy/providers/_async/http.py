from __future__ import annotations

from typing import TYPE_CHECKING

from aiohttp_socks import ProxyConnector
from eth_typing import URI
from eth_utils import to_dict
from web3._utils.http import construct_user_agent
from web3._utils.request import get_default_http_endpoint
from web3.providers.async_base import AsyncJSONBaseProvider

from web3_proxy.providers.base import BaseProvider
from web3_proxy.utils.request import (
	SessionData,
	_async_cache_and_return_session,
	_async_make_post_request,
)

if TYPE_CHECKING:
	from collections.abc import Iterable
	from ssl import SSLContext
	from typing import Any, Final, TypedDict

	from aiohttp import ClientSession
	from python_socks import ProxyType
	from web3.types import (
		RPCEndpoint,
		RPCResponse,
	)

	class PROXY_KW(TypedDict):
		proxy_type: ProxyType
		host: str
		port: int
		username: str
		password: str
		rdns: bool
		proxy_ssl: SSLContext


# FIXME: Close session before loop ends..


class AdvAsyncHTTPProvider(BaseProvider, AsyncJSONBaseProvider):

	endpoint_uri: str | None = None
	_request_kwargs: dict[str, Any] | None = None

	# TODO: Middlewares..?
	# NOTE: https://github.com/ethereum/web3.py/issues/2446

	def __init__(
		self: AdvAsyncHTTPProvider,
		endpoint_uri: URI | str | None = None,
		request_kwargs: dict[str, Any] = {},

		proxy_conn_kwargs: dict[str, Any] = {},
		sess_params: dict[str, Any] = {},
	) -> None:
		"""NOTE: if need, in `connector` proxy conn kwarg just specify connector's class + kwargs.

		aka `(ProxyConnector, {'host': 'localhost', 'port': 8080})`

		TODO: Checkout other conn args/kwargs..
		"""
		if endpoint_uri is None:
			self.endpoint_uri = get_default_http_endpoint()
		else:
			self.endpoint_uri = URI(endpoint_uri)

		assert isinstance(self.endpoint_uri, str)  # linter plug

		self._request_kwargs = request_kwargs
		assert isinstance(self._request_kwargs, dict)  # linter plug

		if 'proxy_type' in proxy_conn_kwargs:
			connector_cls = ProxyConnector
			params = {'connector': (connector_cls, proxy_conn_kwargs), **sess_params}
		else:
			params = {}

		self._session_data: Final[SessionData] = SessionData(
			None,  # Session obj. will be created inside cache during post request(s)
			params=params,
		)

		super().__init__()


	async def cache_async_session(self: AdvAsyncHTTPProvider, session: ClientSession) -> ClientSession:
		return await _async_cache_and_return_session(self.endpoint_uri, session)


	def __str__(self: AdvAsyncHTTPProvider) -> str:
		return f'RPC connection {self.endpoint_uri}'


	@to_dict
	def get_request_kwargs(self: AdvAsyncHTTPProvider) -> Iterable[tuple[str, Any]]:
		assert isinstance(self._request_kwargs, dict)  # linter plug
		if 'headers' not in self._request_kwargs:
			yield 'headers', self.get_request_headers()
		yield from self._request_kwargs.items()


	def get_request_headers(self: AdvAsyncHTTPProvider) -> dict[str, str]:
		return {
			'Content-Type': 'application/json',
			# FIXME: Mb better use `obj.__class__.__name__`?
			'User-Agent': construct_user_agent(str(type(self))),
		}


	async def make_request(
		self: AdvAsyncHTTPProvider,
		method: RPCEndpoint, params: Any,
	) -> RPCResponse:
		self.logger.debug(
			'Making request HTTP. URI: %s, Method: %s',
			self.endpoint_uri, method,
		)
		request_data: bytes = self.encode_rpc_request(method, params)
		raw_response: bytes = await _async_make_post_request(
			self.endpoint_uri, request_data,
			custom_session_data=self._session_data,
			raise_on_no_sdata=True,  # NOTE: Give it to the user..?
			**self.get_request_kwargs(),
		)
		response = self.decode_rpc_response(raw_response)
		self.logger.debug(
			'Getting response HTTP. URI: %s, '
			'Method: %s, Response: %s',
			self.endpoint_uri, method, response,
		)
		return response
