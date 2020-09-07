from math import ceil

# feature_name: odd_bit
known_features = {
    "option_data_loss_protect": 0,
    "initial_routing_sync": 2,
    "option_upfront_shutdown_script": 4,
    "gossip_queries": 6,
    "var_onion_optin": 8,
    "gossip_queries_ex": 10,
    "option_static_remotekey": 12,
    "payment_secret": 14,
    "basic_mpp": 16,
    "option_support_large_channel": 18,
    "option_anchor_outputs": 20,
}

# Reversed map -> odd_bit : feature_name
known_odd_bits = {v: k for k, v in known_features.items()}


def check_feature_name_bit_pair(name, bit):
    """
    Checks whether a given name and bit pair match for known features.

    For unknown features, it returns True as long as they are not using a known name nor bit.

    Args:
        name (:obj:`str`): the feature name.
        bit (:obj:`int`): the bit position.

    Returns:
        :obj:`bool`: For known features, returns True if the pair matches. For unknown features, returns True if the bit
        is unknown.
    """

    if name in known_features:
        # The pair matches
        return bit in [known_features[name], known_features[name] + 1]
    else:
        # The name and bit are unknown
        return not (bit in known_features.values() or bit + 1 in known_features.values())


class Feature:
    """
    Feature represents a feature bit.

    Args:
        bit (:obj:`int`): the index that the feature bit holds in the feature vector.
        is_set (:obj:`bool`): whether the feature is set or not.

    Attributes:
        is_odd (:obj:`bool`): whether the bit is odd or even.
    """

    def __init__(self, bit, is_set):
        if not isinstance(bit, int):
            raise TypeError("bit must be int")
        if not isinstance(is_set, bool):
            raise TypeError("is_set must be bool")

        self.bit = bit
        self.is_set = is_set
        self.is_odd = bool(self.bit % 2)


class FeatureVector:
    """The FeatureVector encapsulates all the features."""

    def __init__(self, **kwargs):
        self._features = {}
        for key, value in kwargs.items():
            if not isinstance(value, Feature):
                raise TypeError(f"Features must be of type Feature, {type(value)} received")
            elif key == "initial_routing_sync" and value.is_set and not value.is_odd:
                raise ValueError("initial_routing_sync has no even bit")
            elif not check_feature_name_bit_pair(key, value.bit):
                raise ValueError("Feature name and bit do not match")

            vars(self)[key] = value
            self._features[key] = value

        for name in set(known_features.keys()).difference(kwargs.keys()):
            vars(self)[name] = Feature(known_features[name], is_set=False)
            self._features[name] = vars(self)[name]

    @classmethod
    def from_bytes(cls, features):
        """
        Builds the FeatureVector from its byte representation.

        Unknown features are parsed as unknown_i where i is the odd_byte of the encoded feature.

        Args:
            features (:obj:`bytes`): the byte-encoded feature vector.

        Returns:
            :obj:`FeatureVector`: The FeatureVector created from the given bytes.

        Raises:
            :obj:`TypeError`: If the provided features are not in bytes.
            :obj:`ValueError`: If two bits from the same pair are set. Or if there is a mismatch between name and bit
            for known features.
        """

        if not isinstance(features, bytes):
            raise TypeError(f"Features must be bytes, {type(features)} received")

        int_features = int.from_bytes(features, "big")
        padding = max(2 * len(known_features), int_features.bit_length())
        padding = padding + 1 if padding % 2 else padding

        bit_features = f"{int_features:b}".zfill(padding)
        bit_pairs = [bit_features[i : i + 2] for i in range(0, len(bit_features), 2)]
        features_dict = {}

        for i, pair in enumerate(reversed(bit_pairs)):
            # Known features are stored no matter if they are set or not
            odd_bit = 2 * i
            feature_name = known_odd_bits.get(odd_bit)
            if feature_name:
                if pair == "00":
                    features_dict[feature_name] = Feature(odd_bit, is_set=False)
                elif pair == "01":
                    features_dict[feature_name] = Feature(odd_bit, is_set=True)
                elif pair == "10":
                    features_dict[feature_name] = Feature(odd_bit + 1, is_set=True)
                else:
                    raise ValueError("Both odd and even bits cannot be set in a pair")
            # For unknown features, we only store the ones that are set
            else:
                feature_name = f"unknown_{odd_bit}"
                if pair == "01":
                    features_dict[feature_name] = Feature(odd_bit, is_set=True)
                elif pair == "10":
                    features_dict[feature_name] = Feature(odd_bit + 1, is_set=True)

        return cls(**features_dict)

    def set_feature(self, name, bit):
        """
        Sets a feature from the FeatureVector identified by its name and bit.

        Args:
            name (:obj:`str`): the name of the feature.
            bit (:obj:`int`): the index that the feature bit holds in the feature vector.

        Raises:
            :obj:`TypeError`: If name is not str or bit is not integer.
            :obj:`ValueError`: If the given name and bit do not match (for known features).
        """

        if not isinstance(name, str):
            raise TypeError("name must be str")
        if not isinstance(bit, int):
            raise TypeError("bit must be integer")

        # Features we know about or features we don't know about and that do not collide with the ones we know about
        if check_feature_name_bit_pair(name, bit):
            vars(self)[name] = Feature(bit, is_set=True)
            self._features[name] = vars(self)[name]
        else:
            raise ValueError("Feature name and bit do not match")

    def serialize(self):
        """Computes the serialization of the FeatureVector."""
        serialized_features = 0
        for feature in self._features.values():
            if feature.is_set:
                serialized_features += pow(2, feature.bit)

        return serialized_features.to_bytes(ceil(serialized_features.bit_length() / 8), "big")

    def to_dict(self):
        """Creates the dictionary representation of the Feature."""
        features = {}
        for name in self._features:
            feature = vars(self)[name]
            if feature.is_set:
                if feature.is_odd:
                    features[name] = "odd"
                else:
                    features[name] = "even"
            else:
                features[name] = 0
        return features
