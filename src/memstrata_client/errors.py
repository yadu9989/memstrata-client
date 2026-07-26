"""Public exception taxonomy."""


class MemStrataError(RuntimeError):
    """Base class for client errors."""


class ConfigurationError(MemStrataError):
    """The local client configuration is absent or unsafe."""


class ProtocolError(MemStrataError):
    """The runtime returned data outside the public protocol."""


class RuntimeFailure(MemStrataError):
    """The runtime exited, rejected the request, or could not be started."""


class RuntimeTimeout(RuntimeFailure):
    """The runtime did not answer within the configured deadline."""
