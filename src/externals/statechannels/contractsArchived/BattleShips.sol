pragma solidity ^0.4.24;

import "./StateChannel.sol";

contract BattleShips {
   
    /*
    After game is Created, both players commit to their boards
    During the game, the state is either Attack or Reveal
    */
    enum GameState { Created, Attack, Reveal, WinClaimed, Finished }
    
    uint8 public turn; //0 if players[0] turn, 1 if players[1] turn
    GameState public gameState;
    
    address[2] players;
    address public winner;
    Board[2] public boards;
    Ships[2] ships;
    
    uint256 public lastUpdateHeight;
    
    /*
    coordinates of the last tile that has been attacked
    */
    uint8 public lastX;
    uint8 public lastY;
 
    /*
    commitment is hash of (randomness, x1, y1, x2, y2) 
    where (x1, y1) is the starting coordinate and (x2,y2) is the end coordinate
    x1 <= x2, y1 <= y2
    */
    struct Ships {
        bytes32[10] commitments;
//        uint128[10] randomness;
        uint8[10] x1;
        uint8[10] y1;
        uint8[10] x2;
        uint8[10] y2;
        bool[10] sunk;
    }
    
    struct Board {
        /*
        commitment is a hash of (randomness,shipTile)
        randomness, ship are revealed during the game if Tile is hit
        */
        bytes32[10][10] commitments;
//        uint128[10][10] randomness;
        bool[10][10] shipTile;
        bool[10][10] revealed;
        bool committed;
    }
    
    StateChannel stateChannel;
    
    /*
    restrict access to players
    */ 
    modifier onlyPlayers() {
        require(msg.sender == players[0] || msg.sender == players[1]);
        _;
    }
    
    /*
    restrict access to player whose turn it is
    */
    modifier onlyPlayerTurn() {
        require(msg.sender == players[turn]);
        _;
    }
    
    /*
    only allow in `state`
    */
    modifier onlyState(GameState state) {
        require(gameState == state);
        _;
    }
    
    /*
    only allow if the channel is off
    */
    // modifier onlyChannelOff() {
    //     require(stateChannel == address(0x0) || stateChannel.status() == StateChannel.Status.OFF);
    //     _;
    // }
    
    event BoardCommit(address indexed player);
    event Attack(address indexed player, uint8 x, uint8 y);
    event Reveal(address indexed player, bool hit);
    event Winner(address indexed player);
    event RevealSink(address indexed player, uint8 shipidx);

    mapping (address => uint8) playerIndex;

    constructor (address player0, address player1, StateChannel _stateChannel) public {
        players[0] = player0;
        players[1] = player1;
        stateChannel = _stateChannel;
        playerIndex[player0] = 0;
        playerIndex[player1] = 1;
        gameState = GameState.Created;
    }
    
    
    function declareWinner(uint8 idx) internal {
        winner = players[idx];
        gameState = GameState.Finished;
        emit Winner(winner);
    }
    
    /*
    attacks tile at coordinate (x,y)
    */ 
    function attack(uint8 x, uint8 y) onlyPlayerTurn /*onlyChannelOff*/ onlyState(GameState.Attack) public {
        require(0<=x && x<10 && 0<=y && y<10);
        lastY = y;
        lastX = x;
        turn = 1 - turn;
        gameState = GameState.Reveal;
        lastUpdateHeight = block.number;
        emit Attack(msg.sender, x, y); 
    }
    
    /*
    reveal last attacked tile if no ship has been sunk by a hit
    */ 
    function reveal(uint128 randomness, bool ship) onlyPlayerTurn /*onlyChannelOff*/ onlyState(GameState.Reveal) public {
        if (keccak256(abi.encodePacked(randomness, ship)) == boards[turn].commitments[lastX][lastY]) {
            boards[turn].shipTile[lastX][lastY] = ship;
//            boards[turn].randomness[lastX][lastY] = randomness;
            boards[turn].revealed[lastX][lastY] = true;
            if (ship) {
                turn = 1 - turn;
            }
            gameState = GameState.Attack;
            lastUpdateHeight = block.number;
            emit Reveal(msg.sender, ship);
        } else {
            declareWinner(1 - turn);
        }
    }
    
//    function isSunk(uint8 player, uint8 shipidx, uint8 x1, uint8 x2, uint8 y1, uint8 y2) public view returns (bool) {
//        require(ships[player].x1[shipidx] == x1);
//        require(ships[player].y1[shipidx] == y1);
//        require(ships[player].x2[shipidx] == x2);
//        require(ships[player].y2[shipidx] == y2);
//
//        return ships[player].sunk[shipidx];
//    }

    /*
    reveal last attacked tile if a ship has been sunk by a hit
    in that case, the ship also has to be revealed
    */ 
    function revealSink(uint128 fieldRandomness, uint128 shipRandomness, uint8 shipIdx, uint8 shipx1, uint8 shipy1, uint8 shipx2, uint8 shipy2) onlyPlayerTurn /*onlyChannelOff*/ onlyState(GameState.Reveal) public {
        if (keccak256(abi.encodePacked(fieldRandomness, true)) == boards[turn].commitments[lastX][lastY]
                 && keccak256(abi.encodePacked(shipRandomness, shipx1, shipy1, shipx2, shipy2)) == ships[turn].commitments[shipIdx]
                 && lastX >= shipx1 && lastX <= shipx2
                 && lastY >= shipy1 && lastY <= shipy2
                 && (shipx1 == shipx2 || shipy1 == shipy2)) {
            boards[turn].shipTile[lastX][lastY] = true;
//            boards[turn].randomness[lastX][lastY] = fieldRandomness;
            boards[turn].revealed[lastX][lastY] = true;
             
//            ships[turn].randomness[shipIdx] = shipRandomness;
            ships[turn].x1[shipIdx] = shipx1;
            ships[turn].y1[shipIdx] = shipy1;
            ships[turn].x2[shipIdx] = shipx2;
            ships[turn].y2[shipIdx] = shipy2;
            ships[turn].sunk[shipIdx] = true;
            
            emit RevealSink(msg.sender, shipIdx);
 
            // check that all tiles of the ship have been hit and contain a ship
            for (uint8 x = shipx1; x <= shipx2; x++){
                for (uint8 y = shipy1; y <= shipy2; y++){
                    if (!boards[turn].shipTile[x][y]) {
                        // cheating, either tile hasn't been revealed or indicated water
                        declareWinner(1-turn);
                        return;
                    }
                }
            }   
             
            turn = 1 - turn;
            gameState = GameState.Attack;
            lastUpdateHeight = block.number;
        } else {
            declareWinner(1 - turn);
        }
    }
    
    function claimWin(uint128[16] shipFieldRandomness, uint128[10] shipRandomness, uint8[10] shipX1, uint8[10] shipY1, uint8[10] shipX2, uint8[10] shipY2) onlyPlayers /*onlyChannelOff*/  public {
        uint8 idx = playerIndex[msg.sender];
        for (uint8 i = 0; i<10; i++) {
            require(ships[1-idx].sunk[i]);
        }
        if (checkBoard(idx, shipFieldRandomness, shipRandomness, shipX1, shipY1, shipX2, shipY2)) {
            // set winner, but do not finalize yet, other player can still submit fraud proof
            winner = players[idx];
            gameState = GameState.WinClaimed;
            lastUpdateHeight = block.number;
        }
    }


    function isCommitted(uint8 _player) public view returns (bool) {
        return boards[_player].committed;
    }
   
    /* currently allows players to change the commitments to their board until the other player has also committed */
    function commitBoard(bytes32[10][10] boardCommitments, bytes32[10] shipCommitments) onlyPlayers /*onlyChannelOff*/ onlyState(GameState.Created) public {
        uint8 idx = playerIndex[msg.sender];
        boards[idx].commitments = boardCommitments;
        ships[idx].commitments = shipCommitments;
        boards[idx].committed = true;
        if (boards[0].committed && boards[1].committed) {
            gameState = GameState.Attack;
            lastUpdateHeight = block.number;
        }

        emit BoardCommit(msg.sender);
    }
   

    /*
    checks whether a player has actually placed all ships on the committed board
    the player reveals the ship locations and the blinding factors for all commitments for tiles that contain a ship
    */
    function checkBoard(uint8 idx, uint128[16] shipFieldRandomness, uint128[10] shipRandomness, uint8[10] shipX1, uint8[10] shipY1, uint8[10] shipX2, uint8[10] shipY2) /*onlyChannelOff*/  public returns (bool) {
        uint8 size;
        uint8 revealed;
        uint8 x;
        uint8 y;
        for (uint8 i = 0; i<10; i++) {
            if (!ships[idx].sunk[i]) {
                // if the ship has been sunk, the locations have already been checked, otherwise check that they are actually on the board
                size = 0;
                revealed = 0;
                
                // ship has to be tiles in a line, second coordinate has to be larger
                if (!(shipX1[i] <= shipX2[i] && shipY1[i] <= shipY2[i] && (shipX1[i] == shipX2[i] || shipY1[i] == shipY2[i]))) {
                    //cheating
                    declareWinner(1-idx);
                    return false;
                }
                // check ship commitment
                if (keccak256(abi.encodePacked(shipRandomness[i], shipX1[i], shipY1[i], shipX2[i], shipY2[i])) != ships[idx].commitments[i]) {
                    //cheating
                    declareWinner(1-idx);
                    return false;
                }
                // check tile commitments for each ship size and check that at least one tile per ship was not revealed during the game
                if (i < 4) { 
                    //size 1
                    if (boards[idx].revealed[shipX1[i]][shipY1[i]] || !(shipX1[i] == shipX2[i] && shipY1[i] == shipY2[i] && keccak256(abi.encodePacked(shipFieldRandomness[i], true)) == boards[idx].commitments[shipX1[i]][shipY1[i]])) {
                        //cheating
                        declareWinner(1-idx);
                        return false;
                    }
                    size++;
                } else { //if (i < 7) {
                    // ship of size 2
                    for (x = shipX1[i]; x <= shipX2[i]; x++){
                        for (y = shipY1[i]; y <= shipY2[i]; y++){
                            if (boards[idx].revealed[x][y]) {
                                // count number of tiles revealed during the game
                                revealed++;
                                if (!boards[idx].shipTile[x][y]) {
                                    // one of the tiles indicated water
                                    declareWinner(1-idx);
                                    return false;
                                }
                            }
                            if (keccak256(abi.encodePacked(shipFieldRandomness[4+(i-4)*2+size], true)) != boards[idx].commitments[x][y]){
                                //cheating
                                declareWinner(1-idx);
                                return false;
                            }
                            size++;
                        }   
                    }
                    if (size != 2) {
                        //cheating
                        declareWinner(1-idx);
                        return false;
                    }
                }
                 //} else if (i < 9) {
                 //    // ship of size 3
                 //    for (x = shipX1[i]; x <= shipX2[i]; x++){
                 //        for (y = shipY1[i]; y <= shipY2[i]; y++){
                 //            if (boards[idx].revealed[x][y]) {
                 //                // count number of tiles revealed during the game
                 //                revealed++;
                 //                if (!boards[idx].shipTile[x][y]) {
                 //                    // one of the tiles indicated water
                 //                    declareWinner(1-idx);
                 //                    return false;
                 //                }
                 //            }
                 //            if (keccak256(abi.encodePacked(shipFieldRandomness[10+(i-7)*3+size], true)) != boards[idx].commitments[x][y]){
                 //                //cheating
                 //                declareWinner(1-idx);
                 //                return false;
                 //             }
                 //             size++;
                 //         }   
                 //     }
                 //     if (size != 3) {
                 //        //cheating
                 //        declareWinner(1-idx);
                 //        return false;
                 //     }
                 //} else {
                 //     // ship of size 4
                 //    for (x = shipX1[i]; x <= shipX2[i]; x++){
                 //        for (y = shipY1[i]; y <= shipY2[i]; y++){
                 //            if (boards[idx].revealed[x][y]) {
                 //                // count number of tiles revealed during the game
                 //                revealed++;
                 //                if (!boards[idx].shipTile[x][y]) {
                 //                    // one of the tiles indicated water
                 //                    declareWinner(1-idx);
                 //                    return false;
                 //                }
                 //            }
                 //            if (keccak256(abi.encodePacked(shipFieldRandomness[16+size], true)) != boards[idx].commitments[x][y]){
                 //                //cheating
                 //                declareWinner(1-idx);
                 //                return false;
                 //             }
                 //             size++;
                 //         }   
                 //     }
                 //     if (size != 4) {
                 //        //cheating
                 //        declareWinner(1-idx);
                 //        return false;
                 //    }
                 //}
                if (revealed == size) {
                    // the ship should have been revealed during the game but wasn't
                    declareWinner(1-idx);
                    return false;
                }
                // add ship coordinates to contract
                ships[idx].x1[i] = shipX1[i];
                ships[idx].y1[i] = shipY1[i];
                ships[idx].x2[i] = shipX2[i];
                ships[idx].y2[i] = shipY2[i];
            }
        }
        return true;
    }
    
    /*
    Fraud proof for adjacent or overlapping ships
    Can be called during the game or once one player has claimed to win the game
    */
    
//    function adjacentOrOverlapping(uint8 shipIdx1, uint8 shipIdx2) onlyChannelOff onlyPlayers() public {
//        require(gameState != GameState.Finished);
//        
//        // idx of other player
//        uint8 playerIdx = 1 - playerIndex[msg.sender];
//        require(gameState == GameState.WinClaimed || (ships[playerIdx].sunk[shipIdx1] && ships[playerIdx].sunk[shipIdx2]));
//        bool cheated = (ships[playerIdx].x1[shipIdx2] >= ships[playerIdx].x1[shipIdx1] - 1
//                    &&  ships[playerIdx].x1[shipIdx2] <= ships[playerIdx].x1[shipIdx1] + 1
//                    &&  ships[playerIdx].y1[shipIdx2] >= ships[playerIdx].y1[shipIdx1] - 1
//                    &&  ships[playerIdx].y1[shipIdx2] <= ships[playerIdx].y1[shipIdx1] + 1);
//        cheated = cheated ||
//                       (ships[playerIdx].x1[shipIdx2] >= ships[playerIdx].x2[shipIdx1] - 1
//                    &&  ships[playerIdx].x1[shipIdx2] <= ships[playerIdx].x2[shipIdx1] + 1
//                    &&  ships[playerIdx].y1[shipIdx2] >= ships[playerIdx].y2[shipIdx1] - 1
//                    &&  ships[playerIdx].y1[shipIdx2] <= ships[playerIdx].y2[shipIdx1] + 1);
//        cheated = cheated ||                                                
//                       (ships[playerIdx].x2[shipIdx2] >= ships[playerIdx].x1[shipIdx1] - 1
//                    &&  ships[playerIdx].x2[shipIdx2] <= ships[playerIdx].x1[shipIdx1] + 1
//                    &&  ships[playerIdx].y2[shipIdx2] >= ships[playerIdx].y1[shipIdx1] - 1
//                    &&  ships[playerIdx].y2[shipIdx2] <= ships[playerIdx].y1[shipIdx1] + 1);
//        cheated = cheated ||                                                
//                       (ships[playerIdx].x2[shipIdx2] >= ships[playerIdx].x2[shipIdx1] - 1
//                    &&  ships[playerIdx].x2[shipIdx2] <= ships[playerIdx].x2[shipIdx1] + 1
//                    &&  ships[playerIdx].y2[shipIdx2] >= ships[playerIdx].y2[shipIdx1] - 1
//                    &&  ships[playerIdx].y2[shipIdx2] <= ships[playerIdx].y2[shipIdx1] + 1);
//        if (cheated) {
//            declareWinner(1-playerIdx);
//        }
//        
//    } 
    
    /*
    Allows the players to claim the win if the other player takes too long to take his turn
    */
    function timeout() public /*onlyChannelOff*/ onlyPlayers() {
        require(gameState == GameState.Attack || gameState == GameState.Reveal);
        if (block.number > lastUpdateHeight + 20) {
            declareWinner(1-turn);
        }
    }
    
    /*
    Allows the players to finalize the game after the period for fraud proof submission is over
    */

    function finishGame() public /*onlyChannelOff*/ onlyPlayers() onlyState(GameState.WinClaimed) {
        if (block.number > lastUpdateHeight + 20) {
            gameState = GameState.Finished;
            emit Winner(winner);
        }
    }
    
    function setState(uint8 _turn, GameState _state, address _winner, bytes32[2][10][10] boardCommitments, 
            bool[2][10][10] shiptiles, bool[2][10][10] revealedtiles,
            bytes32[2][10] shipCommitments, uint8[2][2][10] shipX, uint8[2][2][10] shipY, 
            bool[2][10] sunk, uint8 _lastX, uint8 _lastY) /*onlyChannelOff*/ public  {
        turn = _turn;
        gameState = _state;
        winner = _winner;
        lastX = _lastX;
        lastY = _lastY;
        boards[0].commitments = boardCommitments[0];
//        boards[0].randomness = fieldRandomness[0];
        boards[0].shipTile = shiptiles[0];
        boards[0].revealed = revealedtiles[0];
        boards[1].commitments = boardCommitments[1];
//        boards[1].randomness = fieldRandomness[1];
        boards[1].shipTile = shiptiles[1];
        boards[1].revealed = revealedtiles[1];
        ships[0].commitments = shipCommitments[0];
//        ships[0].randomness = shipRandomness[0];
        ships[0].x1 = shipX[0][0];
        ships[0].y1 = shipY[0][0];
        ships[0].x2 = shipX[0][1];
        ships[0].y2 = shipY[0][1];
        ships[0].sunk = sunk[0];
            
        ships[1].commitments = shipCommitments[1];
//        ships[1].randomness = shipRandomness[1];
        ships[1].x1 = shipX[1][0];
        ships[1].y1 = shipY[1][0];
        ships[1].x2 = shipX[1][1];
        ships[1].y2 = shipY[1][1];
        ships[1].sunk = sunk[1];
        lastUpdateHeight = block.number;
        require(getStateHash() == stateChannel.hstate());
    }
    
//    function getState() public view returns (uint8 _turn, GameState _state, address _winner, bytes32[2][10][10] boardCommitments, 
//            uint128[2][10][10] fieldRandomness, bool[2][10][10] shiptiles, bool[2][10][10] revealedtiles,
//            bytes32[2][10] shipCommitments, uint128[2][10] shipRandomness ,uint8[2][2][10] shipX, uint8[2][2][10] shipY, 
//            bool[2][10] sunk, uint8 _lastX, uint8 _lastY) {
//                
//        _turn = turn;
//        _state = gameState;
//        _winner = winner;
//        _lastX = lastX;
//        _lastY = lastY;
//        for (uint8 i = 0; i < 10; i++) {
//            for (uint8 j = 0; j < 10; j++) {
//                boardCommitments[0][i][j] = boards[0].commitments[i][j];
//                fieldRandomness[0][i][j] = boards[0].randomness[i][j];
//                shiptiles[0][i][j] = boards[0].shipTile[i][j];
//                revealedtiles[0][i][j] = boards[0].revealed[i][j];
//                boardCommitments[1][i][j] = boards[1].commitments[i][j];
//                fieldRandomness[1][i][j] = boards[1].randomness[i][j];
//                shiptiles[1][i][j] = boards[1].shipTile[i][j];
//                revealedtiles[1][i][j] = boards[1].revealed[i][j];
//            }
//            shipCommitments[0][i] = ships[0].commitments[i];
//            shipRandomness[0][i] = ships[0].randomness[i];
//            shipX[0][0][i] = ships[0].x1[i];
//            shipY[0][0][i] = ships[0].y1[i];
//            shipX[0][1][i] = ships[0].x2[i];
//            shipY[0][1][i] = ships[0].y2[i];
//            sunk[0][i] = ships[0].sunk[i];
//            
//            shipCommitments[1][i] = ships[1].commitments[i];
//            shipRandomness[1][i] = ships[1].randomness[i];
//            shipX[1][0][i] = ships[1].x1[i];
//            shipY[1][0][i] = ships[1].y1[i];
//            shipX[1][1][i] = ships[1].x2[i];
//            shipY[1][1][i] = ships[1].y2[i];
//            sunk[1][i] = ships[1].sunk[i];
//        }
//    }
    
    function getStateHash() public view returns (bytes32) {
        return keccak256(abi.encodePacked(
            turn,
            gameState,
            winner,
            lastX,
            lastY,
            getBoardsEncoded(),
            getShipsEncoded()
            ));
    }
  
    function getBoardsEncoded() internal view returns (bytes) {
        return abi.encodePacked(
            boards[0].commitments,
//            boards[0].randomness,
            boards[0].shipTile,
            boards[0].revealed,
            boards[0].committed,
            boards[1].commitments,
//            boards[1].randomness,
            boards[1].shipTile,
            boards[1].revealed,
            boards[1].committed
            );
    }
  
    function getShipsEncoded() internal view returns (bytes) {
        return abi.encodePacked(
            ships[0].commitments,
//            ships[0].randomness,
            ships[0].x1,
            ships[0].y1,
            ships[0].x2,
            ships[0].y2,
            ships[0].sunk,
            ships[1].commitments,
//            ships[1].randomness,
            ships[1].x1,
            ships[1].y1,
            ships[1].x2,
            ships[1].y2,
            ships[1].sunk
            );
    }
    
}
