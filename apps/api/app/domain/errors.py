"""Explicit failures raised by the domain kernel."""


class DomainError(ValueError):
    """Base class for rejected domain operations."""


class DomainInvariantError(DomainError):
    """Raised when an entity or aggregate would violate a business invariant."""


class InvalidTransitionError(DomainError):
    """Raised when a requested case transition is not permitted."""
