"""Runtime capability gates: discovery never starts an engine or hides a module."""
from functools import wraps
from advertised_limits import capabilities


def require_capability(test, name):
    value = capabilities()[name]['supported_here']
    if not isinstance(value, bool):
        raise AssertionError(f'Invalid platform capability: {name}')
    if not value:
        test.skipTest(f'Engine capabilities.{name}.supported_here is false')


def requires_capability(name):
    def decorate(function):
        @wraps(function)
        def run(test, *args, **kwargs):
            require_capability(test, name)
            return function(test, *args, **kwargs)
        return run
    return decorate
