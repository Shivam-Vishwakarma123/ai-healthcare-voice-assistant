# Raised when a requested healthcare or platform resource cannot be found in the database.
class ResourceNotFoundError(Exception):
    pass

# Raised when an entity creation conflicts with an existing unique identifier or constraint.
class DuplicateResourceError(Exception):
    pass
