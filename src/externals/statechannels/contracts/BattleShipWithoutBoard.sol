pragma solidity ^0.4.24;
pragma experimental ABIEncoderV2; // Required to support an array of "bytes' which is annoying 
import "./StateChannel.sol";
import "./StateChannelFactory.sol";

/*
 * Game Rules: Five ships, all can be placed on the board. Players take turns hitting other player's board. 
 * Our game only relies on a commitment to every ship; failure to set up correctly eventually allows the loser to claim all winnings. 
 * Fraud proofs are used to allow both players to "prove" the counterparty has cheated. Necessary to minimise storage requirements. 
 * Why? Because sending a 10x10 grid is ~2m gas. Could have root + merkle tree; but impl complex + still significant gas overhead. 
 *
 */ 
contract BattleShipWithoutBoard {
    // *********** START OF STATE CHANNEL EXTRA FUNCTIONALITY  ***********
    /* 
     * 1. Store address of a new state channel (and perhaps a pointer to its code)
     * 2. Track whether the state channel is on/off (modifier will disable functionality in contract if turned on)
     * 3. Track whether this battleship game is in the main chain or a private "off-chain" network (disable some functionality if in "off-chain" network)
     */
    StateChannel public stateChannel;
    StateChannelFactory stateChannelFactory;
    
    bool privatenetwork = false; // If this contract is deployed via a private network to simulate execution. Set this to true. Compiler can set it. 
    bool public statechannelon = false; // "false" if state channel contract is not instantiated, and "true" if instantiated.  
    uint disputetime = 20; // fixed time for the dispute process 
    uint extratime; // We need to "add time" to any timer to take into account dispute process (triggering + resolving). 
    uint public channelCounter; // How many times has a state channel been created? 
    
    // Attach to all functions in the contract. 
    // Disables all functionality if the state channel is instantiated 
    modifier disableForStateChannel() {
        require(!statechannelon);
        _;
    }
    
    // Attach to all functions in the contract "with side-effects" 
    // This should disable all functionality if this contract is deployed via private network. 
    modifier disableForPrivateNetwork() {
        require(!privatenetwork);
        _;
    }
    
    // Have all parties agreed to lock this contract? 
    function lock(bytes[] _signatures) public disableForStateChannel disableForPrivateNetwork {
        require(!statechannelon);
        
        // Check signatures from everybody in battleship game
        bytes32 sighash = keccak256(abi.encodePacked("lock",channelCounter, round,address(this)));
        for(uint i=0; i<players.length; i++) {
            require(recoverEthereumSignedMessage(sighash, _signatures[i]) == players[i]);
        }
        
        // All good. Lets lock up contract
        channelCounter += 1;
        statechannelon = true; 
        
        // Create state channel contract! 
        stateChannel = StateChannel(stateChannelFactory.createStateChannel(players, disputetime)); 
    }

    // Paddy: Work in Progress, but this looks really ugly to set the full state. 
    // Ideally we can fit it inside one function. But perhaps we spread it across several and just submit h1,h2,h3, and h' = h(h1,h2,h3). 
    // 
    // Parameters: 
    // bool[4] _ready 
    // --> [0][1] = playerShipsReceived
    // --> [2][3] = playerReady
    // --> [4][5] = cheated
    // _uints8[2]
    // -> [0] = x, [1] = y, 
    // uints[7] uints 
    // -> [0] = round, [1] = move_ctr, 
    // -> [2] = _totalShipPositions
    // -> [3] = turn 
    // -> [4] = Phase
    // -> [5] = challengeTime
    // -> [6] = r ---> Random nonce! 
    // address _winner 
    // uint[4] maps 
    // --> [0][1] is waterhits 
    // --> [2][3] is ship_hits 
    // --> [4][5] is balance
    // --> [6][7] is bets 
    // List of ship information (hash, co-ordinates, etc)
    // "r" is the random nonce, agreed by both parties. 
    // Have all parties agreed to unlock this contract? 
    function unlock(bool[6] _bool, uint8[2] _uints8, uint[6] _uints, address _winner, uint[8] _maps, bytes32[10] _shiphash, uint8[10] _x1, uint8[10] _y1, uint8[10] _x2, uint8[10] _y2, bool[10] _sunk) public disableForPrivateNetwork {
        // if the channel has been closed without setstate being called then we allow the battleship
        // game to be unlocked in it's prior state. if setstate is missed for some reason, then an
        // unlock would be impossible otherwise.
        if(bytes32(0x00) == stateChannel.getStateHash()) {
            statechannelon = false;
            delete stateChannel;
            return;
        }
    
        // "round" is included in _uints
        bytes32 _h = keccak256(abi.encodePacked(_bool, _uints8, _uints, _winner, _maps, _shiphash, _x1, _y1, _x2, _y2, _sunk));
        _h = keccak256(abi.encodePacked(_h, address(this)));
        
        // Compare hashes
        require(_h == stateChannel.getStateHash());

        statechannelon = false;
        delete stateChannel;
        
        // Store the "_ready" variables 
        playerShipsReceived[0] = _bool[0];
        playerShipsReceived[1] = _bool[1];
        playerReady[0] = _bool[2];
        playerReady[1] = _bool[3]; 
        cheated[players[0]] = _bool[4];
        cheated[players[1]] = _bool[5];
        
        // Store the "individual uints" 
        x = _uints8[0];
        y = _uints8[1];
        round = _uints[0]; 
        move_ctr = _uints[1];
        totalShipPositions = _uints[2];
        turn = _uints[3]; 
        phase = GamePhase(_uints[4]);
        // we dont include challengetime in the supplied state here, or as part of getState
        // as these timers would need to be synchronised to be synchronised between offchain
        // instances of the battleship contract. This means that challengetime cannot be enforced
        // offchain - channel participants will have to triggerdispute if updates are occuring too
        // slowly.
        challengeTime = now + timer_challenge;
        
        // Store Winner
        winner = _winner;
        
        // Store mappings
        water_hits[players[0]] = _maps[0];
        water_hits[players[1]] = _maps[1];
        ship_hits[players[0]] = _maps[2];
        ship_hits[players[1]] = _maps[3];
        player_balance[players[0]] = _maps[4];
        player_balance[players[1]] = _maps[5];
        bets[players[0]] = _maps[6];
        bets[players[1]] = _maps[7];
        
        // Store ships! 
        for(uint i=0; i<sizes.length*2; i++) {
            
            if(i < sizes.length) {
                ships[players[0]][i] = Ship({hash: _shiphash[i], k: sizes[i % sizes.length], x1: _x1[i], y1: _y1[i], x2: _x2[i], y2: _y2[i], sunk: _sunk[i]});
            } else {
                ships[players[1]][i % sizes.length] = Ship({hash: _shiphash[i], k: sizes[i % sizes.length], x1: _x1[i], y1: _y1[i], x2: _x2[i], y2: _y2[i], sunk: _sunk[i]});
            }
            
        }
    }
    
    // Only required in the PRIVATE contract. Not required in the public / ethereum contract. 
    function getState(uint r) public view returns (bool[6] _bool, uint8[2] _uints8, uint[6] _uints, address _winner, uint[8] _maps, bytes32[10] _shiphash, uint8[10] _x1, uint8[10] _y1, uint8[10] _x2, uint8[10] _y2, bool[10] _sunk, bytes32 _h) {
        
        // Store the "_ready" variables 
        _bool[0] = playerShipsReceived[0]; 
        _bool[1] = playerShipsReceived[1];
        _bool[2] = playerReady[0];
        _bool[3] = playerReady[1];
        _bool[4] = cheated[players[0]];
        _bool[5] = cheated[players[1]];
            
        // Store the "individual uints" 
        _uints8[0] = x;
        _uints8[1] = y;
        _uints[0] = round; 
        _uints[1] = move_ctr;
        _uints[2] = totalShipPositions;
        _uints[3] = turn;
        _uints[4] = uint(phase);
        _uints[5] = r;
            
        // Store Winner
        _winner = winner;
        
        // Store mappings
        _maps[0] = water_hits[players[0]];
        _maps[1] = water_hits[players[1]];
        _maps[2] = ship_hits[players[0]];
        _maps[3] = ship_hits[players[1]];
        _maps[4] = player_balance[players[0]];
        _maps[5] = player_balance[players[1]];
        _maps[6] = bets[players[0]];
        _maps[7] = bets[players[1]];

        // Store ships! 
        for(uint i=0; i<sizes.length*2; i++) {
                
            address toUpdate; 
                
            if(i < sizes.length) {
                toUpdate = players[0];
            } else {
                toUpdate = players[1];
            }
            
            _shiphash[i] = ships[toUpdate][i % sizes.length].hash;
            _x1[i] = ships[toUpdate][i % sizes.length].x1;
            _y1[i] = ships[toUpdate][i % sizes.length].y1;
            _x2[i] = ships[toUpdate][i % sizes.length].x2;
            _y2[i] = ships[toUpdate][i % sizes.length].y2;
            _sunk[i] = ships[toUpdate][i % sizes.length].sunk; 
            
        }
        
        // Compute state hash - that will need to be signed! 
        _h = keccak256(abi.encodePacked(_bool, _uints8, _uints, _winner, _maps, _shiphash, _x1, _y1, _x2, _y2, _sunk)); 
    }
    
    /* Expected Template Variables:
     * - A list of "timers". Anything that begins with "timer_" will be increased when state channel is instantiated 
     * - A list of "players". Simply an array called "players". We expect a signature from each one. 
     */
    
    // *********** END OF STATE CHANNEL EXTRA FUNCTIONALITY  ***********
    
    /* An explanation for each phase of the game 
     * SETUP - Both players swap boards. Counterparty picks one board. All other boards must be revealed. Both parties must agree to "begin game"
     * ATTACK - One player can attack a slot on the counterpartys board. Must send co-ordinate on grid. Transitions to Reveal. 
     * REVEAL - Counterparty must open slot and declare if it hit a ship or not. Full ship must be revealed if it is sunk. Performs integrity checks. Transition to ATTACK or WIN. 
     * WIN - Winner must reveal all ship commitments 
     * FRAUD - Non-winner has a fixed time period to prove fraud based on signed messages received during game + winner's ship openings. 
     * Note: If only one party is caught cheating - counterparty gets full bet. If both players cheated, winnings is burnt. 
     */
    enum GamePhase { Setup, Attack, Reveal, Win, Fraud } 
    GamePhase public phase;
    
    struct Ship {
        bytes32 hash; // commitment to full ship
        uint8 k; // number of spaces 
        
        // first co-ordinate 
        uint8 x1; uint8 y1; // TODO: Do I change this to x0, and y0? Keep everything counting from zero. Slight overslight. 
        
        // second co-ordinate 
        uint8 x2; uint8 y2;
        
        // declared as sunk by counterparty
        bool sunk;
    }
    
    uint8[5] sizes = [5,4,3,3,2];
    address[] public players;
    address public winner;
    address public charity; // if both players cheat; we get coins.
    uint public charity_balance; 
    
    // Ship information 
    mapping (address => Ship[5]) public ships; 
    uint totalShipPositions; // Set in "checkShipList"
    bool[2] public playerShipsReceived; 
    
    // Number of games played 
    bool[2] playerReady;
    uint public round; // Number of games played 
    uint public move_ctr; // Incremented for every move in game 
    
    // Number of hits by a player
    mapping (address => uint) public water_hits; 
    mapping (address => uint) public ship_hits; 
    mapping (address => uint) public player_balance;
    mapping (address => uint) public bets; 
    mapping (address => bool) public cheated; 
    
    // Whose turn is it? And when do they need to respond by? 
    uint public turn; // The "attacker" i.e. whoever takes a shot. 
    uint public challengeTime;  // absolute deadline, set after every move. 
    uint public timer_challenge; // fixed time period for each response  
    
    // Attack co-ordinates 
    uint8 x; uint8 y;

    // Restrict access to players 
    modifier onlyPlayers() {
        require(msg.sender == players[0] || msg.sender == players[1]);
        _;
    }
    
    // Function can only be called in this state 
    modifier onlyState(GamePhase p) {
        require(phase == p);
        _;
    }
    
    event RevealAttack(address indexed player, uint8 x, uint8 y, uint move_ctr, uint round, bytes signature); 
    event RevealHit(address indexed player, uint8 x, uint8 y, bool hit, uint move_ctr, uint round, bytes signature);
    event RevealSunk(address indexed player, uint shipindex, uint8 x1, uint8 y1, uint8 x2, uint8 y2, uint _r, uint move_ctr, uint round, bytes signature);
    
    // Set up the battleship contract.
    // - Address of both parties
    // - Challenge timer i.e. parties must respond with their choice within a time period 
    // - Dispute timer i.e. used in the state channel 
    constructor (address _player0, address _player1, uint _timer_challenge, address _stateChannelFactory) public {
        players.push(_player0);
        players.push(_player1);
        phase = GamePhase.Setup;
        timer_challenge = _timer_challenge;
        stateChannelFactory = StateChannelFactory(_stateChannelFactory);
    }
    
    // Parties can deposit coins during the SETUP phase. 
    // Function MUST BE DISABLED if this contract is deployed via a private network
    function deposit() public onlyState(GamePhase.Setup) onlyPlayers disableForPrivateNetwork disableForStateChannel payable {
        player_balance[msg.sender] += msg.value; 
    }
    
    // Parties can deposit coins during the SETUP phase. 
    // Function MUST BE DISABLED if this contract is deployed via a private network
    function withdraw(uint toWithdraw) public onlyPlayers disableForPrivateNetwork disableForStateChannel {
        require(toWithdraw <= player_balance[msg.sender]);

        // Update state to reflect withdrawal 
        player_balance[msg.sender] -= toWithdraw; 
        
        // Send coins over
        msg.sender.transfer(toWithdraw);
    }
    
    // Place bet for this game. 
    // Assumption: bets can only be "increased" not "decreased" for now. Can be refunded by calling doNotPlay(); 
    function placeBet(uint bet) public onlyState(GamePhase.Setup) onlyPlayers disableForStateChannel { 
        require(player_balance[msg.sender] >= bet);
        
        player_balance[msg.sender] -= bet;
        bets[msg.sender] += bet; 
    }
    
    // Each party submits a ship commitment from the counterparty (and this must be signed for this round/contract!) 
    function storeShips(uint8[] _size, bytes32[] _ships, bytes _signature) public onlyState(GamePhase.Setup) onlyPlayers disableForStateChannel {
        
        // Who are the parties? 
        // msg.sender = party, counterparty is the other player. 
        uint counterparty = 0;
        
        // Transaction is signed by this party. Easy way to identify counterparty. 
        if(msg.sender == players[0]) {
            counterparty = 1;
        }
        
        // Only one shit of ships can be sent! 
        require(!playerShipsReceived[counterparty]);
        
        // Sanity check ships 
        checkShipList(_size, _ships); 
        
        // Hash the ship commitment 
        bytes32 sighash = keccak256(abi.encodePacked(_size, _ships, players[counterparty], round, address(this)));
        
        // Verify counterparty signed ship commitment
        // Thus, both parties have signed this commitment! (since party had to sign tx)
        require(recoverEthereumSignedMessage(sighash, _signature) == players[counterparty]);
        
        // All good? Store the counterparty's ships. 
        for(uint i=0; i<_size.length; i++) {
                
            // Format everything into a nice struct 
            // Gas-heavy, but easiesr for us to manage 
            ships[players[counterparty]][i] = Ship({hash: _ships[i], k: _size[i], x1: 0, y1: 0, x2: 0, y2: 0, sunk: false});
        }
        
        // Mark as ready 
        playerShipsReceived[counterparty] = true; 
    }
    
    // Declare ready to play the game (i.e. all remaining ship commitments were verified off-chain)  
    // Of course - this implies both players have "accepted" the other parties bet. 
    function readyToPlay() public onlyPlayers disableForStateChannel onlyState(GamePhase.Setup) { 
        if(msg.sender == players[0]) {
            playerReady[0] = true;
        } else {
            playerReady[1] = true;
        }
        
        // Both players happy to play? 
        if(playerReady[0] && playerReady[1]) {
            phase = GamePhase.Attack;
            
            // Whose turn is it? 
            turn = 0; // Could be some random beacon here.  
            
            // Reset values for later games. 
            playerReady[0] = false;
            playerReady[1] = false; 
        } 
    }
    
    // One player is not happy, and can simply decide not to play for whatever reason. Refunds all bets placed so far. 
    function doNotPlay() public onlyPlayers disableForStateChannel onlyState(GamePhase.Setup) {
        
        // Refund players bets 
        player_balance[players[0]] += bets[players[0]];
        bets[players[0]] = 0;
        player_balance[players[1]] += bets[players[1]];
        bets[players[1]] = 0;
        
        // Entire game must be reset. 
        reset();
    }
    
    // Player picks a slot position to attack. 
    // Must be completed within a time period 
    function attack(uint8 _x, uint8 _y, bytes _signature) public disableForStateChannel onlyState(GamePhase.Attack) {

        // We require an EXPLICIT signature to be used by fraud proof
        // Signed by the player and the function's caller doesn't matter. , caller of function doesn't matter. 
        // co-ordinates, move, round, this contract. 
        bytes32 sighash = keccak256(abi.encodePacked(_x, _y, move_ctr,round, address(this)));
        require(recoverEthereumSignedMessage(sighash, _signature) == players[turn]);
        
        // Valid slot? 
        if(checkValidSlot(_x, _y)) {
            
            // Store attack co-ordinates 
            x = _x;
            y = _y;
            
            // Publish to make it easy to fetch signed message 
            emit RevealAttack(players[turn], _x, _y, move_ctr, round, _signature); 
            
            // Transition to reveal phase 
            changeGamePlayPhase(); 
        }
    }
    
    // Counterparty reveals slot. Marked as water or ship. No ship was sunk. 
    function revealslot(bool _b, bytes _signature) public disableForStateChannel onlyState(GamePhase.Reveal) {
        
        // Who is the counterparty? 
        uint counterparty = (turn + 1) % 2; 
        
        // We require an explicit signature for later use by a fraud proof
        bytes32 sighash = keccak256(abi.encodePacked(x,y,_b, move_ctr, round, address(this)));
        require(recoverEthereumSignedMessage(sighash, _signature) == players[counterparty]);
 
        // Hit a ship or water? 
        if(_b) {
            ship_hits[players[turn]] += 1;
            
            // Sanity check number of shots 
            if(ship_hits[players[turn]] >= totalShipPositions) {
                fraudDetected(counterparty);
                return;
            }
            
        } else {
            water_hits[players[turn]] += 1;
            
            // Sanity check number of shots 
            if(water_hits[players[turn]] >= (100 - totalShipPositions)) {
                fraudDetected(counterparty);
                return; 
            }
        }
            
        // All good? Publish signed message (easy fetching)
        emit RevealHit(players[counterparty], x, y, _b, move_ctr, round, _signature);
        
        // Game not finished... 
        changeGamePlayPhase();
    }
        
    // Counterparty reveals slot + that a ship was sunk. 
    function revealsunk(uint _shipindex, uint8 _x1, uint8 _y1, uint8 _x2, uint8 _y2, uint _r, bytes _signature) public disableForStateChannel onlyState(GamePhase.Reveal) {
        
        // Who is the counterparty? 
        uint counterparty = (turn + 1) % 2; 
        
        // We require an explicit signature for later use by a fraud proof
        bytes32 sighash = keccak256(abi.encodePacked(_x1,_y1,_x2,_y2,_r,_shipindex,move_ctr,round, address(this)));
        require(recoverEthereumSignedMessage(sighash, _signature) == players[counterparty]);
        
        // Sanity check ships... 
        if(!checkShipQuality(_x1, _y1, _x2, _y2, _r, _shipindex, players[counterparty])) {
            // Not a valid ship opening (or the ship itself is invalid).
            // Counterparty should not have signed this statement; considered cheating
            fraudDetected(counterparty);
            return; 
        }
        
        // Player has hit more ships than expected 
        if(ship_hits[players[turn]] > totalShipPositions) {
            fraudDetected(counterparty);
            return;
        }
        
        // Is this ship actually on the attacked slot? 
        if(!checkAttackSlot(x,y, _x1, _y1, _x2, _y2)) {
            // Ship is not on this attack slot, but signed by counterparty
            // for this move. Considered cheating. 
            fraudDetected(counterparty);
            return; 
        }
        
        // Record that a ship location was hit 
        ship_hits[players[turn]] += 1;

        // record that it was sunk, and fill in it's coordinates
        ships[players[counterparty]][_shipindex].sunk = true;
        ships[players[counterparty]][_shipindex].x1 = _x1;
        ships[players[counterparty]][_shipindex].y1 = _y1;
        ships[players[counterparty]][_shipindex].x2 = _x2;
        ships[players[counterparty]][_shipindex].y2 = _y2;
        
        // Emit sunk ship. (Easy fetching)
        emit RevealSunk(players[counterparty], _shipindex, _x1, _y1, _x2, _y2, _r, move_ctr, round, _signature);
            
        // Check if all ships are now sunk (and if so, finish the game)! 
        if(sankAllShips(players[counterparty])) { 
            return; 
        } else { // Time to finish the game 
            changeGamePlayPhase();
        }
    }
    
    
    // Check whether all ships for a given player have been sank! 
    // Solidity rant: Should be in revealsunk(), but forced to create a new function due to callstack issues. 
    function sankAllShips(address player) internal returns (bool)  {
        require(phase == GamePhase.Attack || phase == GamePhase.Reveal); 
        
        // Check if all ships are sunk 
        for(uint i=0; i<ships[player].length; i++) {
            if(!ships[player][i].sunk) {
                return false;
            }
        }
        
        // Looks like all ships are sunk! 
        phase = GamePhase.Win; 
        winner = players[turn];
        
        return true; 
    }
    
    // Internal function to transition game phase after a move. 
    function changeGamePlayPhase() internal {
        require(phase == GamePhase.Attack || phase == GamePhase.Reveal);
        // Set a new challenge time
        // TODO: "now" relies on "block.timestamp" - problems in state channel and private network will occur
        challengeTime = now + timer_challenge; 
        move_ctr = move_ctr + 1;
        
        // Attacker always sign an even number "0,2,4"
        // Opener always signers an odd number "1,3,5"
        // There are 100 squares on a board, and two boards, each one takes 2 moves to open giving a possible
        // maximum of 400 moves, the last one being an open on 399. This function increments to 400
        // - which we should never reach (as that would allow 399 moves). 
        if(move_ctr == 400) {
            
            phase = GamePhase.Win;
            winner = players[turn];
            return;
        }
        
        // OK. Lets move to the next phase 
        if(GamePhase.Attack == phase) {
            phase = GamePhase.Reveal;
        } else {
            // We must change whose turn it is to "attack" 
            // Mod 2, allows it to go 0,1,0,1, etc.
            // So player 1 = 0, and player 2 = 1. 
            turn = (turn + 1) % 2; 
            phase = GamePhase.Attack;
        }
    }

    // Sanity check the claimed size of all ships 
    function checkShipList(uint8[] _size, bytes32[] _ships) internal {
        
        // We are expecting six ships 
        require(_size.length == sizes.length && sizes.length == _ships.length );
        
        // Battleship sizes from https://www.thesprucecrafts.com/the-basic-rules-of-battleship-411069
        for(uint i=0; i<sizes.length; i++) {
            require(_size[i] == sizes[i]);
        }
        
        // Total ship positions for each player 
        totalShipPositions = _size[0] + _size[1] + _size[2]  + _size[3] + _size[4];
    
        // No need for return. Require should break execution if any fail. 
    }
    
    // We must check that given the ship positions; that the attack was indeed on this ship
    function checkAttackSlot(uint8 _x, uint8 _y, uint8 _x1, uint8 _y1, uint8 _x2, uint8 _y2) internal pure returns (bool) {
        
        // Is the ship horizontal? 
        if(_x1 == _x2) {
            
            // Ship is horizontal - so attack slot _x must be the same. 
            if(_x != _x1) { return false; }
            
            // Example of valid position: _x can be between any of the slots 
            // 9 >= 8 => 7 
            // 7 <= 8 <= 9
            if((_y1 >= _y && _y >= _y2) || (_y1 <= _y && _y <= _y2)) {
                return true; 
            }
        }
        
        // Is the ship vertical? 
        if(_y1 == _y2) {
            
            // Ship is horizontal
            if(_y != _y1) { return false; }
            
            // Example of valid position: _x can be between any of the slots 
            // 9 >= 8 => 7 
            // 7 <= 8 <= 9
            if((_x1 >= _x  && _x >= _x2) || (_x1 <= _x && _x <= _x2)) {
                return true; 
            }
        }
        
        // Ship was not horizontal or vertical 
        return false; 
    }
    
    // We count from 0,...,9 for each grid position! 
    function checkValidSlot(uint8 _x, uint _y) internal pure returns(bool) {

        // Should be on the 10x10 Grid. 
        // We count from 0,...,9
        if(_x < 0 || _x >= 10) { return false; }
        if(_y < 0 || _y >= 10) { return false; }
        
        return true; 
    }
    
    // Check ship conditions. Should be in a straight line and on all valid slots. 
    function checkShipQuality(uint8 _x1, uint8 _y1, uint8 _x2, uint8 _y2, uint _r,  uint _shipindex, address _counterparty) internal view returns (bool) {
        
         // Look up counterparty's ship and check commitment
        uint8 k;
        
         // Is this the ship we are expecting? 
        if(ships[_counterparty][_shipindex].hash == keccak256(abi.encodePacked(_x1, _y1, _x2, _y2, _r,_counterparty, round, address(this)))) {
            k = ships[_counterparty][_shipindex].k;
        } else {
            return false; 
        }

        // Is this ship within the board?
        // Throws if not valid 
        if(!checkValidSlot(_x1, _y1)) { return false; }
        if(!checkValidSlot(_x2, _y2)) { return false; }
        return checkLine(_x1, _y1, _x2, _y2, k);
    }

    // Check whether a list of points are indeed in a straight line 
    function checkLine(uint8 _x1, uint8 _y1, uint8 _x2, uint8 _y2, uint8 k) internal pure returns (bool) {
        
        // Confirm if it is in a straight line or not. 
        bool line = false;
            
        // Is this ship veritcal? 
        if(_x1 == _x2) {
             // Vertical ships must always increment (0 top 9 bottom)
             // So we'd expect _y1 near top of board, and _y2 near bottom of board. 
            if(_y2 > _y1) {
                // OK it should be exactly k slots in length
                if(1 +_y2 - _y1 == k) {
                    
                    line = true;
                }
            }
        }
        
        //Is this ship horizontal? 
        if(_y1 == _y2) {
            // Horizontal ships must always increment (0 left, 9 right)
            if(_x2 > _x1) {
                // OK it should be exactly k slots in length
                if(1 +_x2 - _x1 == k) {
                    line = true;
                }
            } 
        }
        
        // Must be in a straight line 
        return line;
    }
    
    // Fraud was detected during the game. 
    // We already know one player cheated. So we can declare "non-cheater" as the winner, and require them to reveal their board.
    function fraudDetected(uint cheater) internal {
        uint noncheater = (cheater + 1) % 2;
        cheated[players[cheater]] = true; 
        winner = players[noncheater];
        phase = GamePhase.Win;
        challengeTime = now + timer_challenge; // Winner has a fixed time period to open ships 
    }
    
    // Winner must open their ships. 
    // We perform sanity checks on all opened ships.
    // However we cannot check for everything! Only basic things (i.e. straight line)
    // Counterparty is provided time to do a real check and submit fraud proof if necessary
    function openships(uint8[] _x1, uint8[] _y1, uint8[] _x2, uint8[] _y2, uint[] _r) public onlyPlayers disableForStateChannel onlyState(GamePhase.Win) {
        require(msg.sender == winner);        

        // We are expecting ALL ship openings! 
        // If a "ship" was already sunk, it can be filled with 0,0,0,0,0. 
        require(_x1.length == ships[winner].length && _y1.length == ships[winner].length && 
                _x2.length == ships[winner].length && _y2.length == ships[winner].length && 
                _r.length == ships[winner].length);
        // Go through each ship... store if necessary! 
        for(uint i=0; i<ships[winner].length; i++) {
            
            // Only store ships that have not yet been sunk 
            if(!ships[winner][i].sunk) {
                
                // Sanity check ships... 
                if(!checkShipQuality(_x1[i], _y1[i], _x2[i], _y2[i], _r[i], i, winner)) {
                    cheated[winner] = true;
                    // the winner cheated! gameOver
                    gameOver();
                    return;                    
                }
                
                // Store ship. Crucial: It cannot be declared as sunk! 
                ships[winner][i].x1 = _x1[i];
                ships[winner][i].y1 = _y1[i]; 
                ships[winner][i].x2 = _x2[i];
                ships[winner][i].y2 = _y2[i]; 
            }
        }

        // No fraud detected on opened ships. Let the counterparty have their turn. 
        phase = GamePhase.Fraud; 
        challengeTime = now + timer_challenge;
    }
    
    // Finish the game, send winner their coins, and go back to set up. 
    function finishGame() public onlyPlayers disableForStateChannel onlyState(GamePhase.Fraud)  {
        
        // Challenge period has expired? 
        if(now > challengeTime) {
            gameOver();
        }
        
    }
    
    // Both players cheated. Forfeit their bets (or do something here). 
    function gameOver() internal {
        
        // Sort of the "winnings" 
        uint winnings = bets[players[0]] + bets[players[1]]; 
        bets[players[0]] = 0;
        bets[players[1]] = 0;
        
        // Lets check if the winner cheated... 
        if(!cheated[winner]) {
            player_balance[winner] = player_balance[winner] + winnings; 
        } 
        
        // OK the winner cheated... 
        // Did the loser also cheat? 
        if(cheated[players[1]] && cheated[players[0]]) {
            charity_balance = charity_balance + winnings; // Send coins to a charity if both players cheated. 
        }
        
        // Loser didn't cheat... OK we should send them the coins
        if(winner == players[0]) {
             player_balance[players[1]] = player_balance[players[1]] + winnings; 
        } else {
            player_balance[players[0]] = player_balance[players[0]] + winnings; 
        }
        
        // Reset entire game 
        reset();
    
    }
    
    // Two ships claim to be at the same location. 
    function fraudShipsSameCell(uint _shipindex1, uint _shipindex2, uint8 _x, uint8 _y) public onlyPlayers disableForStateChannel {
        require(phase == GamePhase.Attack || phase == GamePhase.Reveal || phase == GamePhase.Fraud);
        
        // Who is the caller and the counterparty? 
        address counterparty; 
        if(msg.sender == players[0]) {
            counterparty = players[1];
        } else {
            counterparty = players[0];
        }

        // Check that both ships have been stored! 
        require(ships[counterparty][_shipindex1].x1 > 0 || ships[counterparty][_shipindex1].y1 > 0 || 
                ships[counterparty][_shipindex1].x2 > 0 || ships[counterparty][_shipindex1].y2 > 0);
        require(ships[counterparty][_shipindex2].x1 > 0 || ships[counterparty][_shipindex2].y1 > 0 || 
                ships[counterparty][_shipindex2].x2 > 0 || ships[counterparty][_shipindex2].y2 > 0);
        
        // Check that _x and _y is indeed a cell for ship1 
        require(checkAttackSlot(_x, _y, ships[counterparty][_shipindex1].x1, ships[counterparty][_shipindex1].y1, 
                                        ships[counterparty][_shipindex1].x2, ships[counterparty][_shipindex1].y2));
        // Check that _x and _y is indeed a cell for ship2
        require(checkAttackSlot(_x, _y, ships[counterparty][_shipindex2].x1, ships[counterparty][_shipindex2].y1, 
                                        ships[counterparty][_shipindex2].x2, ships[counterparty][_shipindex2].y2));
        
        cheated[counterparty] = true; 
        
        if(phase == GamePhase.Attack || phase == GamePhase.Reveal) {
            winner = msg.sender; 
            phase = GamePhase.Win;
            challengeTime = now + timer_challenge; // Winner has a fixed time period to open ships 
            
        } else {
            
            // Must be the "Fraud" phase... lets go into "gameover" mode. 
            gameOver(); 
        }
        
    }

    // A player has tried to take the same shot twice. This should not be allowed. 
    // Can be called at any point during the game
    function fraudAttackSameCell(uint _move1, uint _move2, uint8 _x, uint8 _y, bytes[] _signatures) public onlyPlayers disableForStateChannel {
        
        // Fraud can only be used during certain phases 
        require(phase == GamePhase.Attack || phase == GamePhase.Reveal || phase == GamePhase.Fraud);
        require(msg.sender != winner); 
        
        // Who is the caller and the counterparty? 
        address counterparty; 
        if(msg.sender == players[0]) {
            counterparty = players[1];
        } else {
            counterparty = players[0];
        }
        
        // Check first signed cell...
        bytes32 sighash = keccak256(abi.encodePacked(_x,_y, _move1, round, address(this)));
        require(recoverEthereumSignedMessage(sighash, _signatures[0]) == counterparty);

        // Check the second signed cell
        sighash = keccak256(abi.encodePacked(_x,_y, _move2, round, address(this)));
        require(recoverEthereumSignedMessage(sighash, _signatures[1]) == counterparty);
        

        cheated[counterparty] = true; 
        
        if(phase == GamePhase.Attack || phase == GamePhase.Reveal) {
            winner = msg.sender; 
            phase = GamePhase.Win;
            challengeTime = now + timer_challenge; // Winner has a fixed time period to open ships 
            
        } else {
            
            // Must be the "Fraud" phase... lets go into "gameover" mode. 
            gameOver(); 
        }
        
    }
    
    
    // All moves have a "time-out". If the player times out, we can finish the game early
    // "or" claim all the winnings! 
    function fraudChallengeExpired() public onlyPlayers disableForStateChannel {
        require(now >= challengeTime);
        
        // In ATTACK - we care about whose "turn" it is to play 
        if(phase == GamePhase.Attack) {
            
            // We have detected fraud! They should have finished their turn by now.  
            fraudDetected(turn);
        }
        // In REVEAL - we care about the counterparty of the turn 
        else if(phase == GamePhase.Reveal) {
            
            // Counterparty should have finished their  turn by now. 
            // So we consider it "fraud" if the time limit is up. 
            fraudDetected((turn + 1) % 2);
        }
        
        // In WIN - we care about the winner revealing their board!
        else if(phase == GamePhase.Win) {
            
            // Only the loser should call this fraud! 
            require(winner != msg.sender);
            
            // The winner didn't reveal their ships in time. 
            cheated[winner] = true; 
            gameOver();
        }
    }

    // did a counterparty declare a square as hit when it should have be revealed as a miss?
    // when the ships have been opened a party can check the opponents board to see if they cheated
    // for a given supplied square, check that it is not a hit on any of the opened ships
    // and check that the it was declared as a hit by the counterparty
    // can only be called during the FRAUD phase
    function fraudDeclaredNotMiss(uint8 _x, uint8 _y, uint _move_ctr, bytes _signature) public onlyPlayers disableForStateChannel {
        require(phase == GamePhase.Fraud);
        require(msg.sender != winner);

        address counterparty;
        if(msg.sender == players[0]) {
            counterparty = players[1];
        } else {
            counterparty = players[0];
        }

        // go through each of the ships and check to see if this square is part of onle of them
        bool isAHit = false;
        for(uint8 shipIndex = 0; shipIndex<sizes.length; shipIndex++) {
            // check each of the ships, of the square is hit on none of them the opponent cheated
            require(ships[counterparty][shipIndex].x1 > 0 || ships[counterparty][shipIndex].y1 > 0 || 
                                            ships[counterparty][shipIndex].x2 > 0 || ships[counterparty][shipIndex].y2 > 0);

            isAHit = isAHit && checkAttackSlot(_x,_y,ships[counterparty][shipIndex].x1, ships[counterparty][shipIndex].y1,
                                            ships[counterparty][shipIndex].x2, ships[counterparty][shipIndex].y2);
        }
        
        // not a hit on any ship
        if(!isAHit) {
            // Lets finally check if the counterparty marked this slot as hit during the game 
            bytes32 sighash = keccak256(abi.encodePacked(_x,_y,true, _move_ctr, round, address(this)));
            require(recoverEthereumSignedMessage(sighash, _signature) == counterparty);

            // Yup! Winner cheated! 
            cheated[counterparty] = true;
            
            // Time to close up shop 
            gameOver(); 
        }
    }

    // Did counterparty not declare a ship was hit? 
    // Requires: List of signed messages from counterparty on slots
    // Look up ship opening, identify its slots. Check if there is a signed message for each slot. Yup? Not declared as sunk.
    // Can only be used during the FRAUD Phase 
    function fraudDeclaredNotHit(uint _shipindex, uint8 _x, uint8 _y, uint _move_ctr, bytes _signature) public onlyPlayers disableForStateChannel {
        
        // We can check this fraud during the game or when it has finished.
        // In both cases; the ship opening must be in the contract 
        require(phase == GamePhase.Fraud);
        require(msg.sender != winner); 
        
        // Who is the caller and the counterparty? 
        address counterparty; 
        if(msg.sender == players[0]) {
            counterparty = players[1];
        } else {
            counterparty = players[0];
        }
        
        // Confirm a ship exists for this index 
        require(_shipindex >= 0 && _shipindex < ships[counterparty].length);
        
        // Check the ship was stored in the contract 
        // One position must be greater than 0....
        require(ships[counterparty][_shipindex].x1 > 0 || ships[counterparty][_shipindex].y1 > 0 || 
                ships[counterparty][_shipindex].x2 > 0 || ships[counterparty][_shipindex].y2 > 0);
        
        // If this represents a valid attack slot... lets see what counterparty signed. 
        bool valid = checkAttackSlot(_x,_y,ships[counterparty][_shipindex].x1, ships[counterparty][_shipindex].y1, 
                                           ships[counterparty][_shipindex].x2, ships[counterparty][_shipindex].y2);
        
        // Valid attack? (Split for readability)                                   
        if(valid) {
            
            // Lets finally check if the counterparty marked this slot as water during the game 
            bytes32 sighash = keccak256(abi.encodePacked(_x,_y,false, _move_ctr, round, address(this)));
            require(recoverEthereumSignedMessage(sighash, _signature) == counterparty);
            
            // Yup! Winner cheated! 
            cheated[counterparty] = true;
            
            // Time to close up shop 
            gameOver();
 
        }
    }
    
    // Only designed for end of game! 
    // *** Ship slot information ***
    // _shipindex refers to a ship already stored in this contract. 
    // _move_ctr refers to the "move counter" that was signed when each slot was revealed (order is important! from top to bottom, or left to right). 
    // _signatures refers to the signatures by the counterparty when revealing the ship slot. 
    // If the ship was not declared as sunk, but all slot locations are revealed as hit, then winner cheated. 
    // We do not need to check if any slot locations were revealed as water - as fraudDeclaredNotHit() can be used instead. 
    // 
    function fraudDeclaredNotSunk(uint _shipindex, uint[] _move_ctr, bytes[] _signatures) public onlyPlayers disableForStateChannel {
        
        // We can check this fraud during the game or when it has finished.
        // In both cases; the ship opening must be in the contract 
        require(phase == GamePhase.Fraud);
        require(msg.sender != winner); 
        
        
        // Confirm this is a real ship identifier
        require(_shipindex < ships[winner].length);
        
        // Has the ship been marked as sunk? 
        require(!ships[winner][_shipindex].sunk);
        
        // We know it is a line... so we just now check every signature 
        // Vertical
        if(ships[winner][_shipindex].x1 == ships[winner][_shipindex].x2) {
            
            // OK we need to now check that the winner signed a "reveal" message for every slot 
            // First - lets make sure we have enough signatures to check! 
            require(ships[winner][_shipindex].k == _signatures.length && ships[winner][_shipindex].k == _move_ctr.length);
             
            // Go through every slot. We know that "y" should be incremented as this is a veritical ship. 
            for(uint8 i=0; i<_signatures.length; i++) {
                bytes32 sighash = keccak256(abi.encodePacked(ships[winner][_shipindex].x1,ships[winner][_shipindex].y1+i,true,_move_ctr[i],round,address(this)));
                require(recoverEthereumSignedMessage(sighash, _signatures[i]) == winner);
            }
            
            // YUP! The winner did declare all ship slots as hit. But did not declare the ship as sunk.  
            
        } else { // The ship was must horizontal. It wouldn't be stored in contract unless we checked it well-formed! 
                        
            // OK we need to now check that the winner signed a "reveal" message for every slot 
            // First - lets make sure we have enough signatures to check! 
            require(ships[winner][_shipindex].k == _signatures.length && ships[winner][_shipindex].k == _move_ctr.length);
                
            // Go through every slot. We know that "x" should be incremented as this is a horizontal ship. 
            for(i=0; i<_signatures.length; i++) {
                sighash = keccak256(abi.encodePacked(ships[winner][_shipindex].x1+i,ships[winner][_shipindex].y1,true,_move_ctr[i],round,address(this)));
                require(recoverEthereumSignedMessage(sighash, _signatures[i]) == winner);
            }
            
            // Again yay! the winner did declare all ship slots as hit. But did not declare the ship as sunk. 
            
        }
        
        // We made it this far... so the winner must have cheated! 
        cheated[winner] = true;
         
        // Time to close up shop    
        gameOver();
  
    }
    
    // Reset and destory all variables in this game.
    function reset() internal {
        delete winner;
        delete ships[players[0]]; 
        delete ships[players[1]]; 
        delete totalShipPositions;
        delete playerShipsReceived;
        delete playerReady;
        delete move_ctr;
        delete water_hits[players[0]];
        delete water_hits[players[1]];
        delete ship_hits[players[0]];
        delete ship_hits[players[1]];
        delete cheated[players[0]];
        delete cheated[players[1]]; 
        delete turn;
        delete x;
        delete y; 
        round = round + 1; 
        phase = GamePhase.Setup; 
    }

    // Helper for adding the Ethereum Signed Message prefix, which is added when users sign via web3
    // There are proposals for changing this method - because frankly it's confusing and still remains
    // unsafe. This is possibly a better option: https://github.com/ethereum/EIPs/pull/712 but all these
    // methods rely on client implementation.
    function recoverEthereumSignedMessage(bytes32 _hash, bytes _signature) internal pure returns (address) {
        bytes memory prefix = "\x19Ethereum Signed Message:\n32";
        bytes32 prefixedHash = keccak256(prefix, _hash);
        return recover(prefixedHash, _signature);
    }
    
  
  // Borrowed from: https://raw.githubusercontent.com/OpenZeppelin/openzeppelin-solidity/master/contracts/ECRecovery.sol  
  /**
   * @dev Recover signer address from a message by using their signature
   * @param _hash bytes32 message, the hash is the signed message. What is recovered is the signer address.
   * @param _signature bytes signature, the signature is generated using web3.eth.sign()
   */
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
