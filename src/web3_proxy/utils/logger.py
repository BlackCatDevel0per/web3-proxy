from __future__ import annotations

from logging import DEBUG, INFO, getLogger
from os import environ as os_env
from typing import TYPE_CHECKING

from web3_proxy.utils.meta import PostInitableMeta

if TYPE_CHECKING:
	from logging import Logger


CURRENT_LEVEL: int = DEBUG if os_env.get('W3PROXY_DEBUG') == '1' else INFO


class Loggable(metaclass=PostInitableMeta):

	_p_log_prefix: str = ''

	def __post_init__(self: Loggable) -> None:
		# aka `app.utility.logger.Loggable`
		self._p_log_name: str = f'{self.__module__}.{self.__class__.__name__}'
		self.logger: Logger = getLogger(self._p_log_name)
		self.log: Logger = self.logger
		self.logger.setLevel(CURRENT_LEVEL)
		self.logger.debug('[%s] Post-Init `%s`', self._log_prefix, self._log_name)


	@property
	def _log_prefix(self: Loggable) -> str:
		return self._p_log_prefix


	@property
	def _log_name(self: Loggable) -> str:
		# TODO: Make singlonized property..
		return self._p_log_name
