contract DisputeRegistryInterface {
    
    /*
     * Dispute Registry is a dedicated global contract for
     * recording state channel disputes.
     * We can fetch the number of disputes it has for a given contract
     * and then iterate over it. 
     * NOTE: If a state channel has recorded too many disputes, we'll run out of gas, but this is unlikely due to time to resolve each dispute. 
     */
 
    // Get index of dispute
    function getDispute(uint index) returns (uint _dStart, uint _dExpire, uint _stateRound); 
    
    // Get total number of recorded disputes
    function getTotalDisputes(address SC) returns (uint); 
}

contract PISA {
    
    // PISA without a one-way payment channel. 
    // Simply stores deposit and waits on evidence of cheating from customer.
    // Note: This implementation relies on "timestamps" and not "block time". 
    
    // NoDeposit = contract set up, but no deposit from PISA. 
    // OK = deposit in contract. ready to accept jobs.
    // CHEATED = customer has provided evidence of cheating, and deposit forfeited
    // CLOSED = PISA has shut down serves and withdrawn their coins. 
    struct Flag { NODEPOSIT, OK, CHEATED, CLOSING, CLOSED }
    
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
    constructor(uint _withdrawperiod, address _disputeregistry) {
        
        withdrawperiod = _withdrawperiod; 
        settleperiod = _settleperiod; 
        disputeregistry = _disputeregistry;
        flag = NODEPOSIT;
        owner = msg.sender; 
    }
    
    // Accept deposit from PISA and set up contract .
    // Can be re-used to topup deposit while channel is on 
    function deposit() {
        require(msg.sender == owner); 
        require(flag == Flag.NODEPOSIT || flag == Flag.OK); 
        require(msg.value > 0); 
        deposit = deposit + msg.value; 
        flag == Flag.OK;
        
        // Tell the world 
        emit PISADeposit(msg.value, block.timestamp); 
    }
    
    // PISA wants to shut down. 
    function stopmonitoring() {
        require(msg.sender == owner);
        require(flag == Flag.OK);
        
        // Ideally, withdrawperiod should be large (1 month)
        withdrawtime = block.timestamp + withdrawperiod; 
        flag = Flag.CLOSING; 
        
        // Tell the world 
        emit PISAClosing(withdrawtime, block.timestamp); 
    }
    
    // Let PISA withdraw deposit after time period 
    function withdraw() { 
        require(flag == Flag.CLOSING); 
        require(withdrawtime > block.timestamp);
        require(owner == msg.sender); 
        flag = Flag.CLOSED;
        
        // Safe from recusion - due to flag being CLOSED. 
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
    function recourse(uint _tStart, uint _tExpire, address _SC, uint _i, bytes32 _h, bytes32 _s, bytes _signature) {
        
        // This feature only works while there is a deposit! 
        require(flag == Flag.OK || flag == Flag.CLOSING); 
        require(_h == sha256(_s)); // Hash should match up 
        require(block.timestamp > _tExpire); 
        
        // Compute hash signed by the tower 
        uint signedhash = keccak256(abi.encodePacked(_tStart, _tExpire, _SC, _i, _h, _s, address(this)));
        require(owner == recoverEthereumSignedMessage(signedhash, signature)); 
        
        // Valid signature. Let's now check for the dispute.
        uint totaldisputes = DisputeRegistryInterface(disputeregistry).getTotalDisputes(_SC); 
        
        // Iterate over every recorded dispute for this channel. 
        // TODO: Perhaps the registry can be made to be an instant lookup based on H(SC || i). 
        uint dStart; uint dExpire; uint stateRound; 
        
        for(uint i=0; i<totaldisputes; i++) {
            
            (dStart, dExpire, stateRound) = DisputeRegistryInterface(disputeregistry).getDispute(i);
            
            // Did the dispute happen after the agreed start time? 
            if(dStart > tStart) { 
                
                // Did the dispute expire before the agreed expiry time? 
                if(tExpire > dExpire) { 
                    
                    // OK it looks like the dispute was between 
                    // our agreed start and expiry time. 
                    
                    // What about the state round? 
                    if(i > stateRound) {
                        
                        // Crucial: State channel records finishing round. 
                        // i.e. if tower broadcast 10 and it was accepted by state channel, 
                        // then stateRound should be 10. 
                        // If tower had "11" and didn't broadcast it, then tower cheated. 
                        flag = Flag.CHEATED; 
                        
                        // Tell the world that PISA cheated!
                        emit PISACheated(_SC, block.timestamp);
                    }
                }
            }
            // No cheating discovered? try the next dispute record! 
        }
    }
    
    // Placeholder for now to verify signed messages from PISA. 
    function recoverEthereumSignedMessage(bytes32 _hash, bytes _signature) internal pure returns (address) {
        bytes memory prefix = "\x19Ethereum Signed Message:\n32";
        bytes32 prefixedHash = keccak256(prefix, _hash);
        return recover(prefixedHash, _signature);
    }
    
    
    
}
