from common.logger import get_logger


def test_get_logger():
    # Test that get_logger actually adds a field called "component" with the expected value.
    # As the public interface of the class does not expose the initial_values, we rely on the output
    # of `repr` to check if the expected fields are indeed present.
    logger = get_logger("MyAwesomeComponent")
    assert "'component': 'MyAwesomeComponent'" in repr(logger)
