"""Run one fully qualified unittest method through the repository's normal discovery."""
from pathlib import Path
import sys
import unittest


def case_module(selector):
    parts = selector.split('.')
    if (len(parts) == 3 and all(part.isidentifier() for part in parts)
            and parts[0].startswith('test_') and parts[2].startswith('test')):
        return parts[0]
    return None


def run_case(selector, tests):
    module = case_module(selector)
    if module is None:
        raise ValueError('Expected test_module.TestClass.test_method')
    loader = unittest.TestLoader()
    # Unlike the CLI -k shorthand, this pattern matches the complete test ID.
    loader.testNamePatterns = [selector]
    suite = loader.discover(str(tests), pattern=module + '.py')
    if loader.errors:
        raise ValueError('\n'.join(loader.errors))
    def discovered_ids(tests):
        for test in tests:
            if isinstance(test, unittest.TestSuite):
                yield from discovered_ids(test)
            else:
                yield test.id()
    if list(discovered_ids(suite)) != [selector]:
        raise ValueError('Expected exactly one discovered Python test: ' + selector)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return result.wasSuccessful() and result.testsRun == 1


if __name__ == '__main__':
    try:
        raise SystemExit(0 if run_case(sys.argv[1], Path.cwd() / 'tests') else 1)
    except (IndexError, ValueError) as error:
        raise SystemExit(str(error)) from error
