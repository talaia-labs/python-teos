import os
import shutil
import pytest
from copy import deepcopy
from configparser import ConfigParser
from common.config_loader import ConfigLoader

DEFAULT_CONF = {
    "FOO_STR": {"value": "var", "type": str},
    "FOO_STR_2": {"value": "var", "type": str},
    "FOO_INT": {"value": 12345, "type": int},
    "FOO_INT2": {"value": 6789, "type": int},
    "FOO_STR_PATH": {"value": "foo.var", "type": str, "path": True},
    "FOO_STR_PATH_2": {"value": "foo2.var", "type": str, "path": True},
}

CONF_FILE_CONF = {
    "FOO_STR": {"value": "var", "type": str},
    "FOO_INT2": {"value": 6789, "type": int},
    "FOO_STR_PATH": {"value": "foo.var", "type": str, "path": True},
    "ADDITIONAL_FOO": {"value": "additional_var", "type": str},
}

COMMAND_LINE_CONF = {
    "FOO_STR": {"value": "cmd_var", "type": str},
    "FOO_INT": {"value": 54321, "type": int},
    "FOO_STR_PATH": {"value": "var.foo", "type": str, "path": True},
}

data_dir = "test_data_dir/"
conf_file_name = "test_conf.conf"

conf_file_data = {k: v["value"] for k, v in CONF_FILE_CONF.items()}
cmd_data = {k: v["value"] for k, v in COMMAND_LINE_CONF.items()}


@pytest.fixture(scope="module")
def conf_file_conf():
    config_parser = ConfigParser()

    config_parser["foo_section"] = conf_file_data

    os.mkdir(data_dir)

    with open(data_dir + conf_file_name, "w") as fout:
        config_parser.write(fout)

    yield conf_file_data

    shutil.rmtree(data_dir)


def test_init():
    conf_loader = ConfigLoader(data_dir, conf_file_name, DEFAULT_CONF, COMMAND_LINE_CONF)
    assert conf_loader.data_dir == data_dir
    assert conf_loader.conf_file_path == data_dir + conf_file_name
    assert conf_loader.conf_fields == DEFAULT_CONF
    assert conf_loader.command_line_conf == COMMAND_LINE_CONF


def test_build_conf_only_default():
    foo_data_dir = "foo/"
    default_conf_copy = deepcopy(DEFAULT_CONF)

    conf_loader = ConfigLoader(foo_data_dir, conf_file_name, default_conf_copy, {})
    config = conf_loader.build_config()

    assert foo_data_dir == config.pop("DATA_DIR")

    for k, v in config.items():
        assert k in DEFAULT_CONF
        assert isinstance(v, DEFAULT_CONF[k].get("type"))

        if DEFAULT_CONF[k].get("path"):
            assert v == foo_data_dir + DEFAULT_CONF[k].get("value")
        else:
            assert v == DEFAULT_CONF[k].get("value")

    # No field should have been overwritten
    assert not conf_loader.overwritten_fields


def test_build_conf_with_conf_file(conf_file_conf):
    default_conf_copy = deepcopy(DEFAULT_CONF)

    conf_loader = ConfigLoader(data_dir, conf_file_name, default_conf_copy, {})
    config = conf_loader.build_config()

    assert data_dir == config.pop("DATA_DIR")

    for k, v in config.items():
        # Check that we have only loaded parameters that were already in the default conf. Additional params are not
        # loaded
        assert k in DEFAULT_CONF
        assert isinstance(v, DEFAULT_CONF[k].get("type"))

        # If a value is in the conf file, it will overwrite the one in the default conf
        if k in conf_file_conf:
            comp_v = conf_file_conf[k]

            # Check that we have kept track of what's overwritten
            assert k in conf_loader.overwritten_fields

        else:
            comp_v = DEFAULT_CONF[k].get("value")

        if DEFAULT_CONF[k].get("path"):
            assert v == data_dir + comp_v
        else:
            assert v == comp_v


def test_build_conf_with_command_line():
    foo_data_dir = "foo/"
    default_conf_copy = deepcopy(DEFAULT_CONF)

    conf_loader = ConfigLoader(foo_data_dir, conf_file_name, default_conf_copy, cmd_data)
    config = conf_loader.build_config()

    assert foo_data_dir == config.pop("DATA_DIR")

    for k, v in config.items():
        # Check that we have only loaded parameters that were already in the default conf. Additional params are not
        # loaded
        assert k in DEFAULT_CONF
        assert isinstance(v, DEFAULT_CONF[k].get("type"))

        # If a value is in the command line conf, it will overwrite the one in the default conf
        if k in COMMAND_LINE_CONF:
            comp_v = cmd_data[k]

            # Check that we have kept track of what's overwritten
            assert k in conf_loader.overwritten_fields

        else:
            comp_v = DEFAULT_CONF[k].get("value")

        if DEFAULT_CONF[k].get("path"):
            assert v == foo_data_dir + comp_v
        else:
            assert v == comp_v


def test_build_conf_with_all(conf_file_conf):
    default_conf_copy = deepcopy(DEFAULT_CONF)

    conf_loader = ConfigLoader(data_dir, conf_file_name, default_conf_copy, cmd_data)
    config = conf_loader.build_config()

    assert data_dir == config.pop("DATA_DIR")

    for k, v in config.items():
        # Check that we have only loaded parameters that were already in the default conf. Additional params are not
        # loaded
        assert k in DEFAULT_CONF
        assert isinstance(v, DEFAULT_CONF[k].get("type"))

        # The priority is: cmd, conf file, default
        if k in cmd_data:
            comp_v = cmd_data[k]
        elif k in conf_file_conf:
            comp_v = conf_file_conf[k]
        else:
            comp_v = DEFAULT_CONF[k].get("value")

        if DEFAULT_CONF[k].get("path"):
            assert v == data_dir + comp_v
        else:
            assert v == comp_v

        if k in cmd_data or k in conf_file_conf:
            # Check that we have kept track of what's overwritten
            assert k in conf_loader.overwritten_fields


def test_build_invalid_data(conf_file_conf):
    # Lets first try with only default
    foo_data_dir = "foo/"
    default_conf_copy = deepcopy(DEFAULT_CONF)
    default_conf_copy["FOO_INT"]["value"] = "foo"

    conf_loader = ConfigLoader(foo_data_dir, conf_file_name, default_conf_copy, {})

    with pytest.raises(ValueError):
        conf_loader.build_config()

    # Set back the default value
    default_conf_copy["FOO_INT"]["value"] = DEFAULT_CONF["FOO_INT"]["value"]

    # Only conf file now
    conf_file_conf["FOO_INT2"] = "foo"
    # Save the wrong data
    config_parser = ConfigParser()
    config_parser["foo_section"] = conf_file_data
    with open(data_dir + conf_file_name, "w") as fout:
        config_parser.write(fout)

    conf_loader = ConfigLoader(data_dir, conf_file_name, default_conf_copy, {})

    with pytest.raises(ValueError):
        conf_loader.build_config()

    # Only command line now
    cmd_data["FOO_INT"] = "foo"
    conf_loader = ConfigLoader(foo_data_dir, conf_file_name, default_conf_copy, cmd_data)

    with pytest.raises(ValueError):
        conf_loader.build_config()

    # All together
    # Set back a wrong default
    default_conf_copy["FOO_STR"]["value"] = 1234
    conf_loader = ConfigLoader(data_dir, conf_file_name, default_conf_copy, cmd_data)

    with pytest.raises(ValueError):
        conf_loader.build_config()


def test_create_config_dict():
    # create_config_dict should create a dictionary with the config fields in ConfigLoader.config_fields as long as
    # the type of the field "value" matches the type in "type". The conf source does not matter here.
    foo_data_dir = "foo/"
    default_conf_copy = deepcopy(DEFAULT_CONF)
    conf_loader = ConfigLoader(foo_data_dir, conf_file_name, default_conf_copy, {})
    config = conf_loader.create_config_dict()

    assert isinstance(config, dict)
    for k, v in config.items():
        assert k in config
        assert isinstance(v, default_conf_copy[k].get("type"))


def test_create_config_dict_invalid_type():
    # If any type does not match the expected one, we should get a ValueError
    foo_data_dir = "foo/"
    default_conf_copy = deepcopy(DEFAULT_CONF)

    # Modify a field so the type does not match
    default_conf_copy["FOO_STR_2"]["value"] = 1234

    conf_loader = ConfigLoader(foo_data_dir, conf_file_name, default_conf_copy, {})

    with pytest.raises(ValueError):
        conf_loader.create_config_dict()


def test_extend_paths():
    # Test that only items with the path flag are extended
    foo_data_dir = "foo/"
    default_conf_copy = deepcopy(DEFAULT_CONF)

    conf_loader = ConfigLoader(foo_data_dir, conf_file_name, default_conf_copy, {})
    conf_loader.extend_paths()

    for k, field in conf_loader.conf_fields.items():
        if isinstance(field.get("value"), str):
            if field.get("path") is True:
                assert conf_loader.data_dir in field.get("value")
            else:
                assert conf_loader.data_dir not in field.get("value")

    # Check that absolute paths are not extended
    absolute_path = "/foo/var"
    conf_loader.conf_fields["ABSOLUTE_PATH"] = {"value": absolute_path, "type": str, "path": True}
    conf_loader.extend_paths()

    assert conf_loader.conf_fields["ABSOLUTE_PATH"]["value"] == absolute_path
