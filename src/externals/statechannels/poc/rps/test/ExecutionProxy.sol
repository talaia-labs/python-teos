pragma solidity ^0.4.2;
import "../contracts/RockPaperScissors.sol";

// adapted from https://truffleframework.com/tutorials/testing-for-throws-in-solidity-tests
contract ExecutionProxy {
    address public target;
    bytes data;
    uint256 value;

    constructor(address _target) public {
        target = _target;
    }

    function() payable public {
        data = msg.data;
        value = msg.value;
    }

    function execute() public returns (bool) {
        return target.call.value(value)(data);
    }
}