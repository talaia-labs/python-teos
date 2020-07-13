from common.logger import CustomLogRenderer


def test_CustomLogRenderer_with_event():
    event_dict = {
        "event": "Test",
    }
    renderer = CustomLogRenderer()
    assert renderer(None, None, event_dict) == "Test"


def test_CustomLogRenderer_with_event_and_timestamp():
    event_dict = {
        "event": "Test",
        "timestamp": "today",  # doesn't matter if it's not correct, should just copy it verbatim
    }
    renderer = CustomLogRenderer()
    assert renderer(None, None, event_dict) == "today Test"


def test_CustomLogRenderer_with_event_and_timestamp_and_component():
    event_dict = {
        "component": "MyAwesomeComponent",
        "event": "Test",
        "timestamp": "today",  # doesn't matter if it's not correct, should just copy it verbatim
    }
    renderer = CustomLogRenderer()
    assert renderer(None, None, event_dict) == "today [MyAwesomeComponent] Test"


def test_CustomLogRenderer_with_event_and_timestamp_and_component_and_extra_keys():
    event_dict = {
        "component": "MyAwesomeComponent",
        "event": "Test",
        "timestamp": "today",  # doesn't matter if it's not correct, should just copy it verbatim
        "key": 6,
        "aKeyBefore": 42,  # should be rendered before "key", because it comes lexicographically before
    }
    renderer = CustomLogRenderer()
    assert renderer(None, None, event_dict) == "today [MyAwesomeComponent] Test\taKeyBefore=42 key=6"
