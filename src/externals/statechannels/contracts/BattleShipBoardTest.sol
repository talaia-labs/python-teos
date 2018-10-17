pragma solidity ^0.4.24;


// testing gas costs of storing and opening full boards
contract BattleShipBoardTest {
    bytes32[100][2] boards;
    //uint[100][2] randoms;
    
    function storeBoard(bytes32[100] board, uint8 playerIndex) public {
        boards[playerIndex] = board;
    }

    function openBoard(uint[100] _randoms, bool[100] hits, uint8 playerIndex) public {
        // verify that the random is correct
        for(uint index; index < 100; index++) {
            
            require(boards[playerIndex][index] == keccak256(abi.encodePacked(index, _randoms[index], hits[index], msg.sender, address(this))), "Incorrect hash");
            
           // randoms[playerIndex][index] = _randoms[index];
        }
    }
}