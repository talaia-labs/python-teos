const BattleShipWithoutBoard = artifacts.require("./BattleShipBoardTest.sol");
const { createGasProxy, logGasLib } = require("./gasProxy");
const Web3Util = require("web3-utils");
const Web3 = require("web3");
const web32 = new Web3(new Web3.providers.HttpProvider("http://localhost:8545"));

contract("BattleShipWithBoard", function(accounts) {
    it("stores board", async () => {
        let gasLib = [];
        const battleshipBoard = await createGasProxy(BattleShipWithoutBoard, gasLib, web32).new();

        // create a board
        const board0 = createBoard(accounts[0], battleshipBoard.address);
        const board1 = createBoard(accounts[1], battleshipBoard.address);
        await battleshipBoard.storeBoard(board0, 0);
        await battleshipBoard.storeBoard(board1, 1);

        await battleshipBoard.openBoard(board0.map((a, index) => index), board0.map((a, index) => index % 2 == 0), 0, {
            from: accounts[0]
        });
        await battleshipBoard.openBoard(board1.map((a, index) => index), board1.map((a, index) => index % 2 == 0), 1, {
            from: accounts[1]
        });

        logGasLib(gasLib);
    });
});

const createSize100Array = () => {
    const numbers = [];
    for (let index = 0; index < 100; index++) {
        numbers.push(index);
    }
    return numbers;
};

const createBoard = (player, contractAddress) => {
    const commitments = [];

    for (let index = 0; index < 100; index++) {
        const commitment = Web3Util.soliditySha3(
            { t: "uint", v: index },
            // index as random
            { t: "uint", v: index },
            // a hit is an even number
            { t: "bool", v: index % 2 == 0 },
            { t: "address", v: player },
            { t: "address", v: contractAddress }
        );

        commitments[index] = commitment;
    }

    return commitments;
};
