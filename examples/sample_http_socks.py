from __future__ import annotations

import asyncio
import logging
import sys
from os import environ as os_env

from python_socks import ProxyType
from web3 import AsyncWeb3

# from web3 import AsyncHTTPProvider
from web3_proxy import AdvAsyncHTTPProvider
from web3_proxy.utils.request import logger as sess_logger

provider_cls = AdvAsyncHTTPProvider
# provider_cls = AsyncHTTPProvider


async def main() -> None:
	addr = os_env['PADDR']
	logpass = os_env['PLOGPASS']

	phost, pport = addr.split(':')
	puser, ppasswd = logpass.split(':')

	print('Connecting to:', phost, pport, puser, ppasswd)
	provider = provider_cls(
		endpoint_uri='https://eth.drpc.org',
		proxy_conn_kwargs={
			# 'proxy_type': ProxyType.HTTP,
			'proxy_type': ProxyType.SOCKS5,
			'host': phost,
			'port': pport,
			'username': puser,
			'password': ppasswd,
		},
	)
	handler = logging.StreamHandler(sys.stdout)
	handler.setLevel(logging.DEBUG)
	formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
	handler.setFormatter(formatter)

	provider.logger.addHandler(handler)
	provider.logger.setLevel(logging.DEBUG)

	sess_logger.addHandler(handler)
	sess_logger.setLevel(logging.DEBUG)

	w3 = AsyncWeb3(provider)
	# ...
	for _ in range(3):
		block_number = await w3.eth.get_block_number()
		print(f'Block number is {block_number}')
		# await asyncio.sleep(3)
	print()

	# closes..
	# from web3_proxy.utils.request import _async_session_cache
	# for sd in _async_session_cache._data.values():
	# 	# FIXME: Run for current loop or make "on die" handler for every single session..?
	# 	await sd.session.close()


if __name__ == '__main__':
	async_loop = asyncio.get_event_loop()
	async_loop.run_until_complete(main())

	from web3_proxy.utils.request import _async_session_cache
	print(_async_session_cache._data)

	print('Complete!')
