from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import TYPE_CHECKING

from aiohttp import (
	ClientResponse,
	ClientSession,
	ClientTimeout,
)
from web3._utils.async_caching import async_lock
from web3._utils.caching import generate_cache_key
from web3._utils.request import (
	DEFAULT_TIMEOUT,
	_async_close_evicted_sessions,
)
from web3.utils.caching import SimpleCache

if TYPE_CHECKING:
	from typing import Any, Final

	from eth_typing import URI


logger = logging.getLogger(__name__)

# NOTE: Main stuff is copied from web3 lib, but with `ClientSession` kwargs saving


class SessionData:

	def __init__(self: SessionData, session: ClientSession, params: dict[str, Any]) -> None:
		self.session: ClientSession | None = session
		self.params: dict[str, Any] = params


	# TODO: `__repr__`


if TYPE_CHECKING:
	from typing import Dict, Union  # noqa: UP035

	EV_ITEMS_TYPE = Union[Dict[str, SessionData], None]  # noqa: UP007,UP006

_async_session_cache: Final[SimpleCache] = SimpleCache()
_async_session_cache_lock: Final[threading.Lock] = threading.Lock()
_async_session_pool: Final[ThreadPoolExecutor] = ThreadPoolExecutor(max_workers=1)


def __prepare_sess_params(params: dict[str, Any]) -> dict[str, Any]:
	new_params: dict[str, Any] = params.copy()
	if 'connector' in params:
		# FIXME: Annotate
		# make connector "thread safe"
		conn, conn_params = new_params['connector']
		new_params['connector'] = conn(**conn_params)

	return new_params


def __make_session_on_new(
	session_data: ClientSession | None, cache_key: str, endpoint_uri: str,
	*, raise_on_no_sdata: bool,
) -> tuple[ClientSession, EV_ITEMS_TYPE]:
	evicted_items: EV_ITEMS_TYPE

	new_session_data: SessionData | None = session_data
	if session_data is None or session_data.session is None:
		# if no session, but have params for a new one
		if session_data is not None:
			new_session_data = SessionData(
				ClientSession(**__prepare_sess_params(session_data.params), raise_for_status=True),
				params=session_data.params,
			)
		else:
			# if no session_data
			if raise_on_no_sdata:
				raise ValueError from None
			new_session_data = SessionData(ClientSession(raise_for_status=True), params={})

	new_cached_session_data: SessionData
	new_cached_session_data, evicted_items = _async_session_cache.cache(
		cache_key, new_session_data,
	)
	cached_session = new_cached_session_data.session
	logger.debug(
		'Async session cached: %s, %s',
		endpoint_uri, cached_session,
	)

	return cached_session, evicted_items


async def __get_cached_session(
	cache_key: str, endpoint_uri: str,
) -> tuple[ClientSession, EV_ITEMS_TYPE]:
	# get the cached session
	evicted_items: EV_ITEMS_TYPE = None
	cached_session_data: SessionData = _async_session_cache.get_cache_entry(cache_key)
	got_cached_session: ClientSession = cached_session_data.session

	got_session_is_closed: Final[bool] = got_cached_session.closed
	got_session_loop_is_closed: Final[bool] = got_cached_session._loop.is_closed()  # noqa: SLF001

	warning: str | None = (
		'Async session was closed'
		if got_session_is_closed
		else (
			'Loop was closed for async session'
			if got_session_loop_is_closed
			else None
		)
	)
	if warning:
		logger.debug(
			'%s: %s, %s. '
			'Creating and caching a new async session for uri.',
			warning,
			endpoint_uri,
			got_cached_session,
		)

		_async_session_cache._data.pop(cache_key)  # noqa: SLF001
		# if loop was closed but not the session, close the session
		if not got_session_is_closed:
			await got_cached_session.close()
			##del
			# if not isinstance(got_cached_session.connector, TCPConnector):
			# 	got_cached_session.connector.close()

		logger.debug(
			'Async session closed and evicted from cache: %s',
			got_cached_session,
		)
		del got_cached_session

		# NOTE: Main difference:
		# replace stale session with a new session at the cache key
		new_session_data = SessionData(
			ClientSession(
				**__prepare_sess_params(cached_session_data.params),
				raise_for_status=True,
			),
			params=cached_session_data.params,
		)
		cached_session_data, evicted_items = _async_session_cache.cache(
			cache_key, new_session_data,
		)
		del new_session_data
		cached_session = cached_session_data.session
		logger.debug('New Async session cached: %s, %s', endpoint_uri, cached_session)
	else:
		cached_session = got_cached_session
		del got_cached_session

	return cached_session, evicted_items


async def _async_cache_and_return_session(
	endpoint_uri: URI,
	session_data: SessionData | None = None,
	*,
	raise_on_no_sdata: bool = False,
) -> ClientSession:
	# cache key should have a unique thread identifier
	cache_key = generate_cache_key(f'{threading.get_ident()}:{endpoint_uri}')

	evicted_items: EV_ITEMS_TYPE = None
	async with async_lock(_async_session_pool, _async_session_cache_lock):
		cached_session: ClientSession
		if cache_key not in _async_session_cache:
			cached_session, evicted_items = __make_session_on_new(
				session_data, cache_key, endpoint_uri,
				raise_on_no_sdata=raise_on_no_sdata,
			)
		else:
			cached_session, evicted_items = await __get_cached_session(cache_key, endpoint_uri)

	# FIXME: Split to separate (to reduce the complexity) methods & unite to the one object..
	if evicted_items is not None:
		# At this point the evicted sessions are already popped out of the cache and
		# just stored in the `evicted_sessions` dict. So we can kick off a future task
		# to close them and it should be safe to pop out of the lock here.
		evicted_sessions = evicted_items.values()
		for evicted_session in evicted_sessions:
			logger.debug(
				'Async session cache full. Session evicted from cache: %s',
				evicted_session,
			)
		# Kick off a future task, in a separate thread, to close the evicted
		# sessions. In the case that the cache filled very quickly and some
		# sessions have been evicted before their original request has been made,
		# we set the timer to a bit more than the `DEFAULT_TIMEOUT` for a call. This
		# should make it so that any call from an evicted session can still be made
		# before the session is closed.
		threading.Timer(
			DEFAULT_TIMEOUT + 0.1,
			_async_close_evicted_sessions,
			args=[evicted_sessions],
		).start()

	return cached_session


async def _async_get_response_from_post_request(
	endpoint_uri: URI, *args: Any,
	custom_session_data: SessionData | None = None,
	raise_on_no_sdata: bool = False,
	**kwargs: Any
) -> ClientResponse:
	kwargs.setdefault('timeout', ClientTimeout(DEFAULT_TIMEOUT))
	session = await _async_cache_and_return_session(
		endpoint_uri,
		custom_session_data,
		raise_on_no_sdata=raise_on_no_sdata,
	)
	return await session.post(endpoint_uri, *args, **kwargs)


async def _async_make_post_request(
	endpoint_uri: URI, data: bytes | dict[str, Any], *args: Any,
	custom_session_data: SessionData | None = None, **kwargs: Any
) -> bytes:
	response = await _async_get_response_from_post_request(
		endpoint_uri, *args, data=data, custom_session_data=custom_session_data, **kwargs,
	)
	response.raise_for_status()
	return await response.read()
