from teos.logging_server import encode_event_dict


def test_encode_event_dict_with_event():
    event_dict = {"event": "Test"}
    assert encode_event_dict(event_dict) == "Test"


def test_encode_event_dict_with_event_and_timestamp():
    event_dict = {
        "event": "Test",
        "timestamp": "today",  # doesn't matter if it's not correct, should just copy it verbatim
    }
    assert encode_event_dict(event_dict) == "today Test"


def test_encode_event_dict_with_event_and_timestamp_and_component():
    event_dict = {
        "component": "MyAwesomeComponent",
        "event": "Test",
        "timestamp": "today",  # doesn't matter if it's not correct, should just copy it verbatim
    }
    assert encode_event_dict(event_dict) == "today [MyAwesomeComponent] Test"


def test_encode_event_dict_with_event_and_timestamp_and_component_and_extra_keys():
    event_dict = {
        "component": "MyAwesomeComponent",
        "event": "Test",
        "timestamp": "today",  # doesn't matter if it's not correct, should just copy it verbatim
        "key": 6,
        "aKeyBefore": 42,  # should be rendered before "key", because it comes lexicographically before
    }
    assert encode_event_dict(event_dict) == "today [MyAwesomeComponent] Test  (aKeyBefore=42, key=6)"
