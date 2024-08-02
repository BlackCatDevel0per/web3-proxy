from __future__ import annotations

from typing import TYPE_CHECKING

from web3_proxy.utils.logger import Loggable

if TYPE_CHECKING:
    ...


class BaseProvider(Loggable):
    pass
