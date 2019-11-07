# Porting some functionality from https://github.com/sr-gi/bitcoin_tools with some modifications <3
from os import urandom

from test.simulator.utils import *


class TX:
    """ Defines a class TX (transaction) that holds all the modifiable fields of a Bitcoin transaction, such as
    version, number of inputs, reference to previous transactions, input and output scripts, value, etc.
    """

    def __init__(self):
        self.version = None
        self.inputs = None
        self.outputs = None
        self.nLockTime = None
        self.prev_tx_id = []
        self.prev_out_index = []
        self.scriptSig = []
        self.scriptSig_len = []
        self.nSequence = []
        self.value = []
        self.scriptPubKey = []
        self.scriptPubKey_len = []

        self.offset = 0
        self.hex = ""

    @classmethod
    def deserialize(cls, hex_tx):
        """ Builds a transaction object from the hexadecimal serialization format of a transaction that
        could be obtained, for example, from a blockexplorer.
        :param hex_tx: Hexadecimal serialized transaction.
        :type hex_tx: hex str
        :return: The transaction build using the provided hex serialized transaction.
        :rtype: TX
        """

        tx = cls()
        tx.hex = hex_tx

        try:
            tx.version = int(change_endianness(parse_element(tx, 4)), 16)

            # INPUTS
            tx.inputs = int(parse_varint(tx), 16)

            for i in range(tx.inputs):
                tx.prev_tx_id.append(change_endianness(parse_element(tx, 32)))
                tx.prev_out_index.append(int(change_endianness(parse_element(tx, 4)), 16))
                # ScriptSig
                tx.scriptSig_len.append(int(parse_varint(tx), 16))
                tx.scriptSig.append(parse_element(tx, tx.scriptSig_len[i]))
                tx.nSequence.append(int(parse_element(tx, 4), 16))

            # OUTPUTS
            tx.outputs = int(parse_varint(tx), 16)

            for i in range(tx.outputs):
                tx.value.append(int(change_endianness(parse_element(tx, 8)), 16))
                # ScriptPubKey
                tx.scriptPubKey_len.append(int(parse_varint(tx), 16))
                tx.scriptPubKey.append(parse_element(tx, tx.scriptPubKey_len[i]))

            tx.nLockTime = int(parse_element(tx, 4), 16)

            if tx.offset != len(tx.hex):
                # There is some error in the serialized transaction passed as input. Transaction can't be built
                tx = None
            else:
                tx.offset = 0

        except ValueError:
            # If a parsing error occurs, the deserialization stops and None is returned
            tx = None

        return tx

    def serialize(self, rtype=hex):
        """ Serialize all the transaction fields arranged in the proper order, resulting in a hexadecimal string
        ready to be broadcast to the network.
        :param self: self
        :type self: TX
        :param rtype: Whether the serialized transaction is returned as a hex str or a byte array.
        :type rtype: hex or bool
        :return: Serialized transaction representation (hexadecimal or bin depending on rtype parameter).
        :rtype: hex str / bin
        """

        if rtype not in [hex, bin]:
            raise Exception("Invalid return type (rtype). It should be either hex or bin.")
        serialized_tx = change_endianness(int2bytes(self.version, 4))  # 4-byte version number (LE).

        # INPUTS
        serialized_tx += encode_varint(self.inputs)  # Varint number of inputs.

        for i in range(self.inputs):
            serialized_tx += change_endianness(self.prev_tx_id[i])  # 32-byte hash of the previous transaction (LE).
            serialized_tx += change_endianness(int2bytes(self.prev_out_index[i], 4))  # 4-byte output index (LE)
            serialized_tx += encode_varint(len(self.scriptSig[i]) // 2)  # Varint input script length.
            # ScriptSig
            serialized_tx += self.scriptSig[i]  # Input script.
            serialized_tx += int2bytes(self.nSequence[i], 4)  # 4-byte sequence number.

        # OUTPUTS
        serialized_tx += encode_varint(self.outputs)  # Varint number of outputs.

        if self.outputs != 0:
            for i in range(self.outputs):
                serialized_tx += change_endianness(int2bytes(self.value[i], 8))  # 8-byte field Satoshi value (LE)
                # ScriptPubKey
                serialized_tx += encode_varint(len(self.scriptPubKey[i]) // 2)  # Varint Output script length.
                serialized_tx += self.scriptPubKey[i]  # Output script.

        serialized_tx += int2bytes(self.nLockTime, 4)  # 4-byte lock time field

        # If return type has been set to binary, the serialized transaction is converted.
        if rtype is bin:
            serialized_tx = unhexlify(serialized_tx)

        return serialized_tx

    @staticmethod
    def create_dummy_transaction(prev_tx_id=None, prev_out_index=None):
        tx = TX()

        if prev_tx_id is None:
            prev_tx_id = urandom(32).hex()

        if prev_out_index is None:
            prev_out_index = 0

        tx.version = 1
        tx.inputs = 1
        tx.outputs = 1
        tx.prev_tx_id = [prev_tx_id]
        tx.prev_out_index = [prev_out_index]
        tx.nLockTime = 0
        tx.scriptSig = [
            "47304402204e45e16932b8af514961a1d3a1a25fdf3f4f7732e9d624c6c61548ab5fb8cd410220181522ec8eca07de4860"
            "a4acdd12909d831cc56cbbac4622082221a8768d1d0901"
        ]
        tx.scriptSig_len = [77]
        tx.nSequence = [4294967295]
        tx.value = [5000000000]
        tx.scriptPubKey = [
            "4104ae1a62fe09c5f51b13905f07f06b99a2f7159b2225f374cd378d71302fa28414e7aab37397f554a7df5f142c21c"
            "1b7303b8a0626f1baded5c72a704f7e6cd84cac"
        ]
        tx.scriptPubKey_len = [67]

        return tx.serialize()
