## Usage:

```python
from __future__ import annotations

import asyncio
import sys
from os import environ as os_env

from python_socks import ProxyType
from web3 import AsyncWeb3

from web3_proxy import AdvAsyncHTTPProvider


async def main() -> None:
	# NOTE: You can parse using func from `aiohttp_socks` lib
	addr = os_env['PADDR']
	logpass = os_env['PLOGPASS']

	phost, pport = addr.split(':')
	puser, ppasswd = logpass.split(':')

	print('Connecting to:', phost, pport, puser, ppasswd)
	provider = AdvAsyncHTTPProvider(
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

	w3 = AsyncWeb3(provider)

	block_number = await w3.eth.get_block_number()
	print(f'Block number is {block_number}')

	# NOTE: You can have warning of unclosed session after execution end
	#       due internal proxy connector..


if __name__ == '__main__':
	async_loop = asyncio.get_event_loop()
	async_loop.run_until_complete(main())

	print('Complete!')

```