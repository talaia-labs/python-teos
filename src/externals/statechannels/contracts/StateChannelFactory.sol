pragma solidity ^0.4.24;
import "./StateChannel.sol";

// Responsible for creating state channels and forwarding the address back to caller contract. 
// Can be re-used by any contract. 
contract StateChannelFactory {
    
    function createStateChannel(address[] _parties, uint _disputePeriod) public returns (address addr) {
        return new StateChannel(_parties, _disputePeriod);
    }
}
