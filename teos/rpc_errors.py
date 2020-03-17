# Ported from https://github.com/bitcoin/bitcoin/blob/0.18/src/rpc/protocol.h

# General application defined errors
RPC_MISC_ERROR = -1  # std::exception thrown in command handling
RPC_TYPE_ERROR = -3  # Unexpected type was passed as parameter
RPC_INVALID_ADDRESS_OR_KEY = -5  #  Invalid address or key
RPC_OUT_OF_MEMORY = -7  #  Ran out of memory during operation
RPC_INVALID_PARAMETER = -8  #  Invalid  missing or duplicate parameter
RPC_DATABASE_ERROR = -20  #  Database error
RPC_DESERIALIZATION_ERROR = -22  #  Error parsing or validating structure in raw format
RPC_VERIFY_ERROR = -25  #  General error during transaction or block submission
RPC_VERIFY_REJECTED = -26  #  Transaction or block was rejected by network rules
RPC_VERIFY_ALREADY_IN_CHAIN = -27  #  Transaction already in chain
RPC_IN_WARMUP = -28  #  Client still warming up
RPC_METHOD_DEPRECATED = -32  #  RPC method is deprecated

# Aliases for backward compatibility
RPC_TRANSACTION_ERROR = RPC_VERIFY_ERROR
RPC_TRANSACTION_REJECTED = RPC_VERIFY_REJECTED
RPC_TRANSACTION_ALREADY_IN_CHAIN = RPC_VERIFY_ALREADY_IN_CHAIN

# P2P client errors
RPC_CLIENT_NOT_CONNECTED = -9  #  Bitcoin is not connected
RPC_CLIENT_IN_INITIAL_DOWNLOAD = -10  #  Still downloading initial blocks
RPC_CLIENT_NODE_ALREADY_ADDED = -23  #  Node is already added
RPC_CLIENT_NODE_NOT_ADDED = -24  #  Node has not been added before
RPC_CLIENT_NODE_NOT_CONNECTED = -29  #  Node to disconnect not found in connected nodes
RPC_CLIENT_INVALID_IP_OR_SUBNET = -30  #  Invalid IP/Subnet
RPC_CLIENT_P2P_DISABLED = -31  #  No valid connection manager instance found

# Wallet errors
RPC_WALLET_ERROR = -4  #  Unspecified problem with wallet (key not found etc.)
RPC_WALLET_INSUFFICIENT_FUNDS = -6  #  Not enough funds in wallet or account
RPC_WALLET_INVALID_LABEL_NAME = -11  #  Invalid label name
RPC_WALLET_KEYPOOL_RAN_OUT = -12  #  Keypool ran out  call keypoolrefill first
RPC_WALLET_UNLOCK_NEEDED = -13  #  Enter the wallet passphrase with walletpassphrase first
RPC_WALLET_PASSPHRASE_INCORRECT = -14  #  The wallet passphrase entered was incorrect
RPC_WALLET_WRONG_ENC_STATE = (
    -15
)  #  Command given in wrong wallet encryption state (encrypting an encrypted wallet etc.)
RPC_WALLET_ENCRYPTION_FAILED = -16  #  Failed to encrypt the wallet
RPC_WALLET_ALREADY_UNLOCKED = -17  #  Wallet is already unlocked
RPC_WALLET_NOT_FOUND = -18  #  Invalid wallet specified
RPC_WALLET_NOT_SPECIFIED = -19  #  No wallet specified (error when there are multiple wallets loaded)
