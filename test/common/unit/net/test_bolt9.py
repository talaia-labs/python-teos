import pytest
from common.net.bolt9 import Feature, FeatureVector, known_features


def test_feature():
    # Features expect two params, an integer representing the bit of the feature and a boolean with whether that bit
    # is set or not.
    odd_feature_set = Feature(1, True)
    assert odd_feature_set.bit == 1
    assert odd_feature_set.is_set is True
    assert odd_feature_set.is_odd is True

    odd_feature_unset = Feature(1, False)
    assert odd_feature_unset.bit == 1
    assert odd_feature_unset.is_set is False
    assert odd_feature_unset.is_odd is True

    even_feature_set = Feature(0, True)
    assert even_feature_set.bit == 0
    assert even_feature_set.is_set is True
    assert even_feature_set.is_odd is False

    even_feature_unset = Feature(0, False)
    assert even_feature_unset.bit == 0
    assert even_feature_unset.is_set is False
    assert even_feature_unset.is_odd is False


def test_feature_vector():
    # FeatureVector expects kwarg features (name=Feature)
    f1 = Feature(1, True)
    f2 = Feature(3, False)
    fv = FeatureVector(option_data_loss_protect=f1, initial_routing_sync=f2)
    assert fv.option_data_loss_protect == f1 and fv.initial_routing_sync == f2

    # initial_routing_sync is a special feature with no even bit
    with pytest.raises(ValueError, match="initial_routing_sync has no even bit"):
        FeatureVector(initial_routing_sync=Feature(2, True))

    # known features have known bits, mismatches in known pairs are not allowed
    with pytest.raises(ValueError, match="Feature name and bit do not match"):
        FeatureVector(option_data_loss_protect=Feature(10, True))

    # Unknown features can have whatever name and bit they like, as long as they do not collide with known features
    with pytest.raises(ValueError, match="Feature name and bit do not match"):
        FeatureVector(option_data_loss_protect=Feature(42, True))  # known name, unknown bit
    with pytest.raises(ValueError, match="Feature name and bit do not match"):
        FeatureVector(another_unknown_name=Feature(1, True))  # unknown name, know bit

    # unknown name and bits are allowed
    FeatureVector(unknown_feature_name=Feature(42, True))

    # Finally, all kwargs must have a Feature value
    no_feature_dicts = [0, 1.1, True, object, {}, dict()]
    for value in no_feature_dicts:
        with pytest.raises(TypeError):
            FeatureVector(random_name=value)


# Encoded features are correct as long as two bits are set from the same pair
# Known features are parsed with its name, whereas unknown are given unknown_i where i is the feature odd bit
def test_feature_vector_from_bytes():
    # The easiest way of testing this is to create the FeatureVector and serialize it
    no_features = b""
    assert no_features == FeatureVector.from_bytes(no_features).serialize()

    f0 = b"\x02"
    fv0 = FeatureVector.from_bytes(f0)
    assert fv0.option_data_loss_protect.is_set and fv0.option_data_loss_protect.is_odd
    assert f0 == fv0.serialize()

    f0_2 = b"\x0a"
    fv0_2 = FeatureVector.from_bytes(f0_2)
    assert fv0_2.option_data_loss_protect.is_set and fv0_2.option_data_loss_protect.is_odd
    assert fv0_2.initial_routing_sync.is_set and fv0_2.initial_routing_sync.is_odd
    assert f0_2 == fv0_2.serialize()

    # Unknown feature (set bit 22)
    f22 = b"\x40\x00\x00"
    fv22 = FeatureVector.from_bytes(f22)
    assert fv22.unknown_22.is_set
    assert fv22.serialize() == f22

    # All odd features
    f_all_odd = b"\x2a\xaa\xaa"
    fv_all_odd = FeatureVector.from_bytes(f_all_odd)
    assert fv_all_odd.option_data_loss_protect.is_set and fv_all_odd.option_data_loss_protect.is_odd
    assert fv_all_odd.initial_routing_sync.is_set and fv_all_odd.initial_routing_sync.is_odd
    assert fv_all_odd.option_upfront_shutdown_script.is_set and fv_all_odd.option_upfront_shutdown_script.is_odd
    assert fv_all_odd.gossip_queries.is_set and fv_all_odd.gossip_queries.is_odd
    assert fv_all_odd.var_onion_optin.is_set and fv_all_odd.var_onion_optin.is_odd
    assert fv_all_odd.gossip_queries_ex.is_set and fv_all_odd.gossip_queries_ex.is_odd
    assert fv_all_odd.option_static_remotekey.is_set and fv_all_odd.option_static_remotekey.is_odd
    assert fv_all_odd.payment_secret.is_set and fv_all_odd.payment_secret.is_odd
    assert fv_all_odd.basic_mpp.is_set and fv_all_odd.basic_mpp.is_odd
    assert fv_all_odd.option_support_large_channel.is_set and fv_all_odd.option_support_large_channel.is_odd
    assert fv_all_odd.option_anchor_outputs.is_set and fv_all_odd.option_anchor_outputs.is_odd
    assert fv_all_odd.serialize() == f_all_odd

    # All even features (but initial_routing_sync)
    f_all_even = b"\x15\x55\x59"
    fv_all_even = FeatureVector.from_bytes(f_all_even)
    assert fv_all_even.option_data_loss_protect.is_set and not fv_all_even.option_data_loss_protect.is_odd
    assert fv_all_even.initial_routing_sync.is_set and fv_all_even.initial_routing_sync.is_odd
    assert fv_all_even.option_upfront_shutdown_script.is_set and not fv_all_even.option_upfront_shutdown_script.is_odd
    assert fv_all_even.gossip_queries.is_set and not fv_all_even.gossip_queries.is_odd
    assert fv_all_even.var_onion_optin.is_set and not fv_all_even.var_onion_optin.is_odd
    assert fv_all_even.gossip_queries_ex.is_set and not fv_all_even.gossip_queries_ex.is_odd
    assert fv_all_even.option_static_remotekey.is_set and not fv_all_even.option_static_remotekey.is_odd
    assert fv_all_even.payment_secret.is_set and not fv_all_even.payment_secret.is_odd
    assert fv_all_even.basic_mpp.is_set and not fv_all_even.basic_mpp.is_odd
    assert fv_all_even.option_support_large_channel.is_set and not fv_all_even.option_support_large_channel.is_odd
    assert fv_all_even.option_anchor_outputs.is_set and not fv_all_even.option_anchor_outputs.is_odd
    assert fv_all_even.serialize() == f_all_even


def test_feature_vector_from_bytes_both_set():
    # The same feature cannot be set with both bits set
    f0_1 = b"\x03"
    with pytest.raises(ValueError, match="Both odd and even bits cannot be set in a pair"):
        FeatureVector.from_bytes(f0_1)


def test_feature_vector_from_bytes_wrong_type():
    # Features must be bytes
    with pytest.raises(TypeError, match="Features must be bytes"):
        FeatureVector.from_bytes("random string")


def test_feature_vector_set_feature():
    # A feature can be set as long as the name and bit match, or a wrong pair (known name, unknown bit or vice versa) is
    # not set.
    fv = FeatureVector.from_bytes(b"\x00")

    # Set option_upfront_shutdown_script
    fv.set_feature("option_upfront_shutdown_script", 4)
    assert fv.option_upfront_shutdown_script.is_set
    assert not fv.option_upfront_shutdown_script.is_odd

    # We can set it to odd too
    fv.set_feature("option_upfront_shutdown_script", 5)
    assert fv.option_upfront_shutdown_script.is_set
    assert fv.option_upfront_shutdown_script.is_odd

    # Unknown features work too as long as they don't mismatch
    fv.set_feature("random_feature", 24)
    assert fv.random_feature.is_set
    assert not fv.random_feature.is_odd


def test_feature_vector_set_feature_mismatch():
    # If the feature name and the bit do not match, set_feature will fail
    # Set option_upfront_shutdown_script
    fv = FeatureVector.from_bytes(b"\x00")
    with pytest.raises(ValueError, match="Feature name and bit do not match"):
        fv.set_feature("option_upfront_shutdown_script", 3)

    # Unknown features that mismatch are not accepted either
    with pytest.raises(ValueError, match="Feature name and bit do not match"):
        fv.set_feature("random_feature", 3)


def test_feature_vector_set_wrong_types():
    fv = FeatureVector.from_bytes(b"\x00")
    # Name must be str and bit must be int
    with pytest.raises(TypeError):
        fv.set_feature(int(), int())

    with pytest.raises(TypeError):
        fv.set_feature(str(), str())


def test_feature_vector_serialize():
    # This has been covered in test_feature_vector_from_bytes
    pass


def test_feature_vector_to_dict():
    # Converts feature names to dict
    fv = FeatureVector.from_bytes(b"\x00")

    # There is no feature set
    for k, v in fv.to_dict().items():
        assert v is 0

    # The dict contains only known features, as long as an unknown is not set
    assert fv.to_dict().keys() == known_features.keys()

    fv.set_feature("option_data_loss_protect", 0)
    # Only option_data_loss_protect is set (and it's even)
    for k, v in fv.to_dict().items():
        if k == "option_data_loss_protect":
            assert v == "even"
        else:
            assert v == 0

    fv.set_feature("option_upfront_shutdown_script", 5)
    # option_data_loss_protect is set (and it's even) and option_upfront_shutdown_script is set (and it's odd)
    for k, v in fv.to_dict().items():
        if k == "option_data_loss_protect":
            assert v == "even"
        elif k == "option_upfront_shutdown_script":
            assert v == "odd"
        else:
            assert v == 0

    # It works with unknown features too (name is unknown_i)
    fv.set_feature("unknown_24", 24)
    for k, v in fv.to_dict().items():
        if k == "option_data_loss_protect":
            assert v == "even"
        elif k == "option_upfront_shutdown_script":
            assert v == "odd"
        elif k == "unknown_24":
            assert v == "even"
        else:
            assert v == 0

    assert set(fv.to_dict().keys()).difference(known_features.keys()) == {"unknown_24"}
