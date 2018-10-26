pragma solidity ^0.4.25;

contract DisputeRegistryInterface {
    
    /*
     * Dispute Registry is a dedicated global contract for
     * recording state channel disputes.
     * If a state channel has recorded too many disputes, we'll run out of gas, but this is unlikely due to time to resolve each dispute. 
     */
 
    // Test dispute. Day is 0-6 (depending on daily record). 
    function testDispute(address _sc, uint8 _day, uint _starttime, uint _endtime, uint _stateround) returns (bool);
}

contract PISA {
    
    // PISA without a one-way payment channel. 
    // Simply stores deposit and waits on evidence of cheating from customer.
    // Note: This implementation relies on "timestamps" and not "block time". 
    
    // NoDeposit = contract set up, but no deposit from PISA. 
    // OK = deposit in contract. ready to accept jobs.
    // CHEATED = customer has provided evidence of cheating, and deposit forfeited
    // CLOSED = PISA has shut down serves and withdrawn their coins. 
    enum Flag { NODEPOSIT, OK, CHEATED, CLOSING, CLOSED }
    
    Flag public flag;
    uint public withdrawperiod = 0; // How long must PISA wait to withdraw coins? 
    uint public withdrawtime = 0; // What is the exact time PISA can withdraw deposit? 
    
    // Who owns this contract? 
    address public owner;
    address public disputeregistry; 
    
    // PISA deposit
    uint public deposit = 0;
    
    // Inform world the tower has deposited coins. 
    event PISADeposit(uint coins, uint timestamp); 
    event PISAClosing(uint withdrawtime, uint timestamp); 
    event PISAClosed(uint timestamp);
    event PISACheated(address SC, uint timestamp);
    
    // Set up timers for PISA. No deposit yet.
    // Two step process. Set timers, send deposit seperately. 
    constructor(uint _withdrawperiod, address _disputeregistry) public {
        
        withdrawperiod = _withdrawperiod; 
        disputeregistry = _disputeregistry;
        flag = Flag.NODEPOSIT;
        owner = msg.sender; 
    }
    
    // Accept deposit from PISA and set up contract .
    // Can be re-used to topup deposit while channel is on 
    function deposit() public payable {
        require(msg.sender == owner); 
        require(flag == Flag.NODEPOSIT || flag == Flag.OK); 
        require(msg.value > 0); 
        deposit = deposit + msg.value; 
        flag == Flag.OK;
        
        // Tell the world 
        emit PISADeposit(msg.value, block.timestamp); 
    }
    
    // PISA wants to shut down. 
    function stopmonitoring() public {
        require(msg.sender == owner);
        require(flag == Flag.OK);
        
        // Ideally, withdrawperiod should be large (1 month)
        withdrawtime = block.timestamp + withdrawperiod; 
        flag = Flag.CLOSING; 
        
        // Tell the world 
        emit PISAClosing(withdrawtime, block.timestamp); 
    }
    
    // Let PISA withdraw deposit after time period 
    function withdraw() public { 
        require(flag == Flag.CLOSING); 
        require(withdrawtime > block.timestamp);
        require(owner == msg.sender); 
        
        // Safe from recusion - due to flag being CLOSED. 
        flag = Flag.CLOSED;
        msg.sender.transfer(deposit);
        deposit = 0; 
        
        // Tell everyone PISA has shut down
        emit PISAClosed(block.timestamp);
    }
    
    /* 
     * Signed message from PISA during appointment: 
     * - tStart = Start time of appointment
     * - tExpire = End time of appointment
     * - SC = Address of state channel smart contract
     * - i = State Version (i.e. what counter the tower agreed to publish) 
     * - h = Conditional transfer hash (i.e. computed by tower) 
     * - s = Conditional transfer pre-image (i.e. prove Tower has been paid)
     * - addr = address(this) is the final part of the signed message! 
     * - signature = Tower signature 
     */ 
    function recourse(uint8 _day, uint _tStart, uint _tExpire, address _SC, uint _i, bytes32 _h, bytes32 _s, bytes _signature) public {
        
        // This feature only works while there is a deposit! 
        require(flag == Flag.OK || flag == Flag.CLOSING); 
        require(_h == sha256(_s)); // Hash should match up 
        require(block.timestamp > _tExpire); 
        
        // Compute hash signed by the tower 
        bytes32 signedhash = keccak256(abi.encodePacked(_tStart, _tExpire, _SC, _i, _h, _s, address(this)));
        require(owner == recoverEthereumSignedMessage(signedhash, _signature)); 
        
        if(DisputeRegistryInterface(disputeregistry).testDispute(_SC, _day, _tStart, _tExpire, _i)) {
            // Crucial: State channel records finishing round. 
            // i.e. if tower broadcast 10 and it was accepted by state channel, 
            // then stateRound should be 10. 
            // If tower had "11" and didn't broadcast it, then tower cheated. 
            flag = Flag.CHEATED; 
                        
            // Tell the world that PISA cheated!
            emit PISACheated(_SC, block.timestamp);
        }
    }
    
    // Placeholder for now to verify signed messages from PISA. 
    function recoverEthereumSignedMessage(bytes32 _hash, bytes _signature) internal pure returns (address) {
        bytes memory prefix = "\x19Ethereum Signed Message:\n32";
        bytes32 prefixedHash = keccak256(prefix, _hash);
        return recover(prefixedHash, _signature);
    }
    
    function recover(bytes32 _hash, bytes _signature) internal pure returns (address) {
      bytes32 r;
      bytes32 s;
      uint8 v;
      
      // Check the signature length
      if (_signature.length != 65) {
          return (address(0)); 
          
      }
      
      // Divide the signature in r, s and v variables
      // ecrecover takes the signature parameters, and the only way to get them
      // currently is to use assembly.
      // solium-disable-next-line security/no-inline-assembly
      
      assembly { 
          r := mload(add(_signature, 32))
          s := mload(add(_signature, 64))
          v := byte(0, mload(add(_signature, 96)))
          
      }
      
      // Version of signature should be 27 or 28, but 0 and 1 are also possible versions
      if (v < 27) {
          v += 27;
      }
      
      // If the version is correct return the signer address
      if (v != 27 && v != 28) { 
          return (address(0));
          
      } else {
          // solium-disable-next-line arg-overflow
          return ecrecover(_hash, v, r, s);
      }
    }
}
