const BattleShipWithoutBoard = artifacts.require("./BattleShipWithoutBoard.sol");
const BattleShipWithoutBoardInChannel = artifacts.require("./BattleShipWithoutBoardInChannel.sol");
const StateChannelFactory = artifacts.require("./StateChannelFactory.sol");
const StateChannel = artifacts.require("./StateChannel.sol");
const Web3Util = require("web3-utils");
const Web3 = require("web3");
const web32 = new Web3(new Web3.providers.HttpProvider("http://localhost:8545"));
const { createGasProxy, logGasLib } = require("./gasProxy");

const deposit = async (contract, player, amount, expectedContractBalance) => {
    const deposit = await contract.deposit({ from: player, value: amount });
    const balance = await contract.player_balance(player);
    assert.equal(balance, amount);
    assert.equal(await web32.eth.getBalance(contract.address), expectedContractBalance);
};

const placeBet = async (contract, player, amount) => {
    const pastDeposit = await contract.player_balance(player);
    const bet0 = await contract.placeBet(amount, { from: player });
    const balance = await contract.player_balance(player);
    assert.equal(pastDeposit - balance, amount);
    const bet = await contract.bets(player);
    assert.equal(bet, amount);
};

const committedShip = (id, size, x1, y1, x2, y2, r, player, round, gameAddress) => {
    // ship is commitment to...
    // x1, y1, x2, y2, random, player, game round, contract address(this)
    const commitment = Web3Util.soliditySha3(
        { t: "uint8", v: x1 },
        { t: "uint8", v: y1 },
        { t: "uint8", v: x2 },
        { t: "uint8", v: y2 },
        { t: "uint", v: r },
        { t: "address", v: player },
        { t: "uint", v: round },
        { t: "address", v: gameAddress }
    );

    return {
        id,
        size,
        x1,
        y1,
        x2,
        y2,
        r,
        player,
        round,
        gameAddress,
        commitment,
        hits: 0
    };
};

// ASIDE on how to construct a board
// at any given point(x).
// can I go <dir> <size> spots?
// answer this by by asking question of point(<dir> + 1), then ask can I go <dir> (<size> - 1) spots.
// when <size> - (i) == 0, and answer is yes, then total answer is yes
// if answer is ever no? then total answer is no.

let createArray = (size, elementCreator) => Array.apply(null, Array(size)).map(elementCreator);
let createEmptyBoard = () => createArray(10, () => createArray(10, () => 0));
const alphabet = "abcde";

const addShipToBoard = (id, x1, y1, x2, y2, board) => {
    for (i = x1; i <= x2; i++) {
        for (j = y1; j <= y2; j++) {
            board[i][j] = id;
        }
    }
};

const shipSizes = [5, 4, 3, 3, 2];
const random = "0x61";

const constructBasicShips = async (contract, player) => {
    const round = await contract.round();
    const emptyBoard = createEmptyBoard();

    const ships = shipSizes.map((element, index) => {
        const id = alphabet[index];
        const size = element;
        const x1 = index;
        const y1 = 0;
        const x2 = index;
        const y2 = element - 1;

        addShipToBoard(id, x1, y1, x2, y2, emptyBoard);

        return committedShip(id, size, x1, y1, x2, y2, random, player, round, contract.address);
    });

    return { sizes: shipSizes, ships, board: emptyBoard };
};

const constructSameCellShips = async (contract, player) => {
    const round = await contract.round();
    const emptyBoard = createEmptyBoard();
    // reverse the ships so that the largest one is placed last

    const reversedShipSizes = [...shipSizes].reverse();
    const ships = reversedShipSizes.map((element, index) => {
        const id = alphabet[index];
        const size = element;
        const x1 = 0;
        const y1 = 0;
        const x2 = 0;
        const y2 = element - 1;

        addShipToBoard(id, x1, y1, x2, y2, emptyBoard);

        return committedShip(id, size, x1, y1, x2, y2, random, player, round, contract.address);
    });

    // reverse the ships back into their original order
    ships.reverse();
    return { sizes: shipSizes, ships, board: emptyBoard };
};

const committedShips = async (contract, size, ships, player) => {
    const round = await contract.round();
    const commitment = Web3Util.soliditySha3(
        { t: "uint[]", v: size },
        { t: "bytes32[]", v: ships },
        { t: "address", v: player },
        { t: "uint", v: round },
        { t: "address", v: contract.address }
    );

    return {
        size,
        ships,
        player,
        round: round,
        gameAddress: contract.address,
        commitment
    };
};

const signShips = async (contract, size, ships, player) => {
    const shipsCommitment = await committedShips(contract, size, ships, player);
    const signature = await web32.eth.sign(shipsCommitment.commitment, player);
    return { shipsCommitment, signature };
};

const storeShips = async (
    contract,
    sizes,
    shipCommitments,
    signature,
    player,
    counterPartyIndex,
    shipsTotalCommitment
) => {
    await contract.storeShips(sizes, shipCommitments, signature, { from: player, gas: 2000000 });
    const playerShipsRecieved = await contract.playerShipsReceived(counterPartyIndex);
    assert.equal(playerShipsRecieved, true);
};

const doNotPlay = async (contract, player) => {
    await contract.doNotPlay({ from: player });
    let phase = await contract.phase();
    assert.equal(phase, Phase.Setup);
};

const playerReady = async (contract, player, expectedPhase) => {
    await contract.readyToPlay({ from: player });
    let phase = await contract.phase();
    assert.equal(phase, expectedPhase);
};

const attack = async (contract, player, x, y) => {
    let moveCtr = await contract.move_ctr();
    console.log(`\t${player} move ${moveCtr} attack (${x}, ${y})`);

    let round = await contract.round();

    const attackHash = Web3Util.soliditySha3(
        { t: "uint8", v: x },
        { t: "uint8", v: y },
        { t: "uint", v: moveCtr },
        { t: "uint", v: round },
        { t: "address", v: contract.address }
    );

    let sig = await web32.eth.sign(attackHash, player);
    await contract.attack(x, y, sig, { from: player });
    const phase = await contract.phase();
    assert.equal(phase.toNumber(), 2);
    return sig;
};

const reveal = async (contract, player, x, y, hit) => {
    let moveCtr = await contract.move_ctr();
    console.log(`\t${player} move ${moveCtr} reveal (${x}, ${y}) as ${hit ? "hit" : "miss"}`);
    let round = await contract.round();
    let turnBefore = await contract.turn();

    const revealHash = Web3Util.soliditySha3(
        { t: "uint8", v: x },
        { t: "uint8", v: y },
        { t: "bool", v: hit },
        { t: "uint", v: moveCtr },
        { t: "uint", v: round },
        { t: "address", v: contract.address }
    );

    let sig = await web32.eth.sign(revealHash, player);
    await contract.revealslot(hit, sig, { from: player });

    // check that phase is now attack, and that turn has incremented
    const turnAfter = await contract.turn();
    const phase = await contract.phase();
    assert.equal(phase.toNumber(), 1);
    assert.equal(turnAfter.toNumber(), (turnBefore.toNumber() + 1) % 2);
    return { x, y, hit, moveCtr, round, gameAddress: contract.address, revealHash, sig };
};

const revealSunk = async (contract, player, shipIndex, x1, y1, x2, y2, r, isWin) => {
    let moveCtr = await contract.move_ctr();
    console.log(`\t${player} move ${moveCtr} reveal sunk at (${x}, ${y})`);
    let round = await contract.round();
    let turnBefore = await contract.turn();

    const revealHash = Web3Util.soliditySha3(
        { t: "uint8", v: x1 },
        { t: "uint8", v: y1 },
        { t: "uint8", v: x2 },
        { t: "uint8", v: y2 },
        { t: "uint", v: r },
        { t: "uint", v: shipIndex },
        { t: "uint", v: moveCtr },
        { t: "uint", v: round },
        { t: "address", v: contract.address }
    );

    let sig = await web32.eth.sign(revealHash, player);
    await contract.revealsunk(shipIndex, x1, y1, x2, y2, r, sig, { from: player });

    // check that phase is now attack, and that turn has incremented
    const turnAfter = await contract.turn();
    const phase = await contract.phase();
    assert.equal(phase.toNumber(), isWin ? 3 : 1);
    assert.equal(turnAfter.toNumber(), isWin ? turnBefore.toNumber() : (turnBefore.toNumber() + 1) % 2);
};

const recordHitAndTestForSink = (shipId, ships) => {
    const shipIndex = ships.findIndex(s => s.id === shipId);
    const hitShip = ships[shipIndex];
    hitShip.hits = hitShip.hits + 1;

    // we've hit all the spots
    return hitShip.size === hitShip.hits ? { shipIndex, shipId } : false;
};

const testForHitAndReveal = async (contract, player, board, x, y, ships, currentSinks, overrides) => {
    let hit;
    if (overrides && overrides.hitSupplied) {
        hit = overrides.hit;
    } else if (overrides && overrides.invertBoardHitSupplied) {
        hit = board[x][4 - y];
    } else {
        hit = board[x][y];
    }

    if (hit === 0) {
        // miss, reveal it
        const sig = await reveal(contract, player, x, y, false);
        return sig;
    } else {
        const indexAndId = recordHitAndTestForSink(hit, ships);
        let sink;
        if (overrides && overrides.sunkSupplied) {
            sink = overrides.sunk;
        } else sink = indexAndId;

        if (sink) {
            // sunk, reveal it
            const ship = ships[indexAndId.shipIndex];
            await revealSunk(
                contract,
                player,
                indexAndId.shipIndex,
                ship.x1,
                ship.y1,
                ship.x2,
                ship.y2,
                ship.r,
                currentSinks == 4
            );
            return "sink";
        } else {
            // hit but not sunk, reveal it
            const sig = await reveal(contract, player, x, y, true);
            return sig;
        }
    }
};

const openShips = async (contract, winner, winnerShips) => {
    let returnVals = await contract.openships(
        winnerShips.map(s => s.x1),
        winnerShips.map(s => s.y1),
        winnerShips.map(s => s.x2),
        winnerShips.map(s => s.y2),
        winnerShips.map(s => s.r),
        { from: winner }
    );

    const phase = await contract.phase();
    assert.equal(phase.toNumber(), Phase.Fraud);
};

const finishGame = async (contract, player) => {
    await contract.finishGame({ from: player });
    const phase = await contract.phase();
    assert.equal(phase.toNumber(), 0);
};

const increaseTimeStamp = seconds => {
    return new Promise((resolve, reject) => {
        web32.currentProvider.send(
            {
                jsonrpc: "2.0",
                method: "evm_increaseTime",
                params: [seconds],
                id: new Date().getSeconds()
            },
            (err, rep) => {
                if (err) {
                    reject(err);
                } else {
                    resolve(rep);
                }
            }
        );
    });
};

const withdraw = async (contract, player, amount) => {
    const playerBalanceBefore = await contract.player_balance(player);
    const contractBalanceBefore = await web32.eth.getBalance(contract.address);
    await contract.withdraw(amount, { from: player });
    const playerBalanceAfter = await contract.player_balance(player);
    const contractBalanceAfter = await web32.eth.getBalance(contract.address);

    assert.equal(playerBalanceBefore - playerBalanceAfter, amount);
    assert.equal(contractBalanceBefore - contractBalanceAfter, amount);
};

const timerChallenge = 20;
const depositValue = Web3Util.toWei("0.1", "ether");

const setupGame = async (contract, player0, player1, boardBuilder0, boardBuilder1, cancelSetup) => {
    console.log("\t// SETUP //");

    assert.equal(await web32.eth.getBalance(contract.address), 0);

    console.log("\tdeposit");
    await deposit(contract, player0, depositValue, depositValue);
    await deposit(contract, player1, depositValue, 2 * depositValue);

    console.log("\tplace bet");
    await placeBet(contract, player0, depositValue);
    await placeBet(contract, player1, depositValue);

    console.log("\tconstruct and sign ships");
    const player0Ships = await boardBuilder0(contract, player0);
    const player1Ships = await boardBuilder1(contract, player1);
    const player0Sigs = await signShips(
        contract,
        player0Ships.sizes,
        player0Ships.ships.map(s => s.commitment),
        player0
    );
    const player1Sigs = await signShips(
        contract,
        player1Ships.sizes,
        player1Ships.ships.map(s => s.commitment),
        player1
    );

    console.log("\tstore ships");
    // submit each others ships
    await storeShips(
        contract,
        player1Ships.sizes,
        player1Ships.ships.map(s => s.commitment),
        player1Sigs.signature,
        player0,
        1,
        player1Sigs.shipsCommitment
    );
    await storeShips(
        contract,
        player0Ships.sizes,
        player0Ships.ships.map(s => s.commitment),
        player0Sigs.signature,
        player1,
        0,
        player0Sigs.shipsCommitment
    );

    if (cancelSetup) {
        console.log("\tcancel setup");
        await doNotPlay(contract, player0);
        await doNotPlay(contract, player1);
    } else {
        console.log("\tstart play");
        await playerReady(contract, player0, 0);
        await playerReady(contract, player1, 1);
    }
    console.log("\t// SETUP //\n");
    return { player0: player0Ships, player1: player1Ships };
};

const attackAndReveal = async (
    contract,
    attackPlayer,
    attackPlayerCurrentSinks,
    x,
    y,
    revealPlayer,
    revealPlayerBoard,
    revealPlayerShips,
    overrides
) => {
    let attackSig = await attack(contract, attackPlayer, x, y);
    let attackMoveCtr = await contract.move_ctr();
    let revealSink = await testForHitAndReveal(
        contract,
        revealPlayer,
        revealPlayerBoard,
        x,
        y,
        revealPlayerShips,
        attackPlayerCurrentSinks,
        overrides
    );
    if (revealSink === "sink") {
        return { sink: true, attackSig };
    } else {
        assert.equal(attackMoveCtr.toNumber(), revealSink.moveCtr.toNumber());
        return { ...revealSink, attackSig };
    }
};

const playThrough5x5 = async (
    contract,
    player0,
    player1,
    gameState,
    neverRevealPlayer0,
    neverSinkPlayer0,
    maxPlays,
    invertRevealsPlayer0
) => {
    console.log("\t// PLAY //");
    let player0Sinks = 0;
    let player1Sinks = 0;
    let winner;
    const reveals = [];
    let plays = 0;

    for (x = 0; x < 5; x++) {
        for (y = 0; y < 5; y++) {
            //console.log(plays);
            if (maxPlays && plays >= maxPlays) {
                return {
                    winner,
                    reveal
                };
            }
            plays = plays + 2;
            let player0Move = await attackAndReveal(
                contract,
                player0,
                player0Sinks,
                x,
                y,
                player1,
                gameState.player1.board,
                gameState.player1.ships,
                {}
            );
            if (player0Move.sink) player0Sinks++;
            else {
                reveals[player0Move.moveCtr] = player0Move;
            }
            if (player0Sinks === 5) {
                winner = player0;
                break;
            }

            let player0Overrides = {};
            if (neverRevealPlayer0) player0Overrides = { ...player0Overrides, ...{ hit: 0, hitSupplied: true } };
            if (neverSinkPlayer0) player0Overrides = { ...player0Overrides, ...{ sunk: false, sunkSupplied: true } };
            if (invertRevealsPlayer0) player0Overrides = { ...player0Overrides, ...{ invertBoardHitSupplied: true } };

            // now switch over and reveal the other player
            let player1Move = await attackAndReveal(
                contract,
                player1,
                player1Sinks,
                x,
                y,
                player0,
                gameState.player0.board,
                gameState.player0.ships,
                player0Overrides
            );
            if (player1Move.sink) player1Sinks++;
            else {
                reveals[player1Move.moveCtr] = player1Move;
            }
            if (player1Sinks === 5) {
                winner = player1;
                break;
            }
        }
    }
    if (!winner) throw new Error("No winner reached!");
    console.log("\t// PLAY //\n");
    return { winner, reveals };
};

const sigTools = {
    hashWithAddress: (hState, address) => {
        return web3.utils.soliditySha3({ t: "bytes32", v: hState }, { t: "address", v: address });
    },

    hashAndSignState: async (hState, round, channelAddress, playerAddress) => {
        let msg = web3.utils.soliditySha3(
            { t: "bytes32", v: hState },
            { t: "uint256", v: round },
            { t: "address", v: channelAddress }
        );
        const sig = await web3.eth.sign(msg, playerAddress);
        return sig;
    },

    hashAndSignClose: async (hState, round, channelAddress, playerAddress) => {
        let msg = web3.utils.soliditySha3(
            { t: "string", v: "close" },
            { t: "bytes32", v: hState },
            { t: "uint256", v: round },
            { t: "address", v: channelAddress }
        );
        const sig = await web3.eth.sign(msg, playerAddress);
        return sig;
    },

    hashAndSignLock: async (channelCounter, round, battleShipAddress, playerAddress) => {
        let msg = web3.utils.soliditySha3(
            { t: "string", v: "lock" },
            { t: "uint256", v: channelCounter },
            { t: "uint256", v: round },
            { t: "address", v: battleShipAddress }
        );
        const sig = await web3.eth.sign(msg, playerAddress);
        return sig;
    },

    chopUpSig: sig => {
        const removedHexNotation = sig.slice(2);
        var r = `0x${removedHexNotation.slice(0, 64)}`;
        var s = `0x${removedHexNotation.slice(64, 128)}`;
        var v = `0x${removedHexNotation.slice(128, 130)}`;
        return [v, r, s];
    }
};

contract("BattleShips", function(accounts) {
    const player0 = accounts[0];
    const player1 = accounts[1];
    const gasLibs = [];
    const config = {
        endToEnd: false,
        fraudShipsSameCell: false,
        fraudAttackSameCell: false,
        fraudDeclaredNotHit: false,
        fraudDeclaredNotMiss: false,
        fraudDeclaredNotSunk: false,
        doNotPlay: false,
        stateChannelFactoryEndToEnd: false,
        stateChannelEndToEndDispute: false,
        stateChannelEndToEndCoop: false,
        battleshipAndStateChannel: false,
        fraudChallengePeriodExpired: false,
        battleshipNoUpdate: true,
        battleshipAndStateChannelMidwayExit: false
    };
    let theStateChannelFactory;

    before(async () => {
        // populate the state channel factory
        theStateChannelFactory = await StateChannelFactory.new();
    });

    it("deploys", async () => {
        return;
        const gasLib = [];
        const BattleShipGamePre = createGasProxy(BattleShipWithoutBoard, gasLib, web32);
        const BattleShipGame = await BattleShipGamePre.new(
            player0,
            player1,
            timerChallenge,
            theStateChannelFactory.address
        );
        gasLibs.push({ test: "deploys", gasLib });
    });

    it("simple end to end", async () => {
        if (!config.endToEnd) return;

        console.log("\tconstruct");
        const gasLib = [];
        const BattleShipGamePre = createGasProxy(BattleShipWithoutBoard, gasLib, web32);
        const BattleShipGame = await BattleShipGamePre.new(
            player0,
            player1,
            timerChallenge,
            theStateChannelFactory.address
        );

        // setup with basic boards
        let gameState = await setupGame(BattleShipGame, player0, player1, constructBasicShips, constructBasicShips);

        // play
        let { winner } = await playThrough5x5(BattleShipGame, player0, player1, gameState);

        console.log("\t// FINALISE //");

        console.log(`\twinner ${winner} opening ships`);
        await openShips(BattleShipGame, winner, winner === player0 ? gameState.player0.ships : gameState.player1.ships);
        console.log("\tfinish game");
        await increaseTimeStamp(30);
        await finishGame(BattleShipGame, winner);
        console.log("\twinner withdraws");
        await withdraw(BattleShipGame, winner, depositValue);

        console.log("\t// FINALISE //");
        gasLibs.push({ test: "end-to-end", gasLib });
    });

    it("do not play", async () => {
        if (!config.doNotPlay) return;

        console.log("\tconstruct");
        const gasLib = [];
        const BattleShipGamePre = createGasProxy(BattleShipWithoutBoard, gasLib, web32);
        const BattleShipGame = await BattleShipGamePre.new(
            player0,
            player1,
            timerChallenge,
            theStateChannelFactory.address
        );

        // setup with basic boards
        let gameState = await setupGame(
            BattleShipGame,
            player0,
            player1,
            constructBasicShips,
            constructBasicShips,
            true
        );
        gasLibs.push({ test: "do-not-play", gasLib });
    });

    it("statechannelfactory end-to-end", async () => {
        if (!config.stateChannelFactoryEndToEnd) return;

        console.log("\tconstruct");
        const gasLib = [];
        const StatechannelFactoryInstance = await createGasProxy(StateChannelFactory, gasLib, web32).new();
        const StateChannelTx = await StatechannelFactoryInstance.createStateChannel([player0, player1], timerChallenge);

        gasLibs.push({ test: "statechannel-factory-end-to-end", gasLib });
    });

    // quick
    it("statechannel end-to-end dispute", async () => {
        if (!config.stateChannelEndToEndDispute) return;

        console.log("\tconstruct");
        const gasLib = [];
        const StatechannelInstance = await createGasProxy(StateChannel, gasLib, web32).new([player0, player1], 0);

        // dispute
        await StatechannelInstance.triggerDispute({ from: player0 });

        // sign some state
        const dummyHstate = "0x00";
        const dummyRound = 1;
        const player0Sig = sigTools.chopUpSig(
            await sigTools.hashAndSignState(dummyHstate, dummyRound, StatechannelInstance.address, player0)
        );
        const player1Sig = sigTools.chopUpSig(
            await sigTools.hashAndSignState(dummyHstate, dummyRound, StatechannelInstance.address, player1)
        );

        // set state
        await StatechannelInstance.setstate([...player0Sig, ...player1Sig], dummyRound, dummyHstate);

        // resolve
        await StatechannelInstance.resolve();

        gasLibs.push({ test: "statechannel-end-to-end-dispute", gasLib });
    });

    it("statechannel end-to-end coop", async () => {
        if (!config.stateChannelEndToEndCoop) return;

        console.log("\tconstruct");
        const gasLib = [];
        const StatechannelInstance = await createGasProxy(StateChannel, gasLib, web32).new([player0, player1], 0);

        // sign some state
        const dummyHstate = "0x00";
        const dummyRound = 1;
        const player0Sig = sigTools.chopUpSig(
            await sigTools.hashAndSignClose(dummyHstate, dummyRound, StatechannelInstance.address, player0)
        );
        const player1Sig = sigTools.chopUpSig(
            await sigTools.hashAndSignClose(dummyHstate, dummyRound, StatechannelInstance.address, player1)
        );

        // set state
        await StatechannelInstance.close([...player0Sig, ...player1Sig], dummyRound, dummyHstate);

        gasLibs.push({ test: "statechannel-end-to-end-coop", gasLib });
    });

    it("battleship end-to-end with lock unlock", async () => {
        if (!config.battleshipAndStateChannel) return;

        console.log("\tconstruct");
        const gasLib = [];
        const BattleShipGamePre = createGasProxy(BattleShipWithoutBoard, gasLib, web32);
        const BattleShipGame = await BattleShipGamePre.new(
            player0,
            player1,
            timerChallenge,
            theStateChannelFactory.address
        );

        // setup with basic boards
        let gameState = await setupGame(BattleShipGame, player0, player1, constructBasicShips, constructBasicShips);

        // now lockup
        let channelCounter = await BattleShipGame.channelCounter();
        let round = await BattleShipGame.round();

        let sig0 = await sigTools.hashAndSignLock(channelCounter, round, BattleShipGame.address, player0);
        let sig1 = await sigTools.hashAndSignLock(channelCounter, round, BattleShipGame.address, player1);

        // await BattleShipGame.lock([sig0, sig1]);
        let battleshipWeb3Contract = new web32.eth.Contract(BattleShipGame.abi, BattleShipGame.address);
        let lockTx = await battleshipWeb3Contract.methods.lock([sig0, sig1]).send({ from: player0, gas: 13000000 });
        gasLib.push({ method: "lock", gasUsed: lockTx.gasUsed });
        let channelOn = await BattleShipGame.statechannelon();
        assert.equal(channelOn, true);

        const stateChannelAddress = await BattleShipGame.stateChannel();
        let BattleshipStateChannel = await StateChannel.at(stateChannelAddress);

        const offChainGasLib = [];
        const OffchainBattleship = await createGasProxy(BattleShipWithoutBoardInChannel, offChainGasLib, web32).new(
            player0,
            player1,
            timerChallenge,
            theStateChannelFactory.address,
            BattleShipGame.address
        );

        // move it off chain

        let offChainChannelCounter = await OffchainBattleship.channelCounter();
        let offChainRound = await OffchainBattleship.round();
        let offChainSig0 = await sigTools.hashAndSignLock(
            offChainChannelCounter,
            offChainRound,
            OffchainBattleship.address,
            player0
        );
        let offChainSig1 = await sigTools.hashAndSignLock(
            offChainChannelCounter,
            offChainRound,
            OffchainBattleship.address,
            player1
        );

        let offChainBattleshipWeb3Contract = new web32.eth.Contract(OffchainBattleship.abi, OffchainBattleship.address);
        let offchainLockTx = await offChainBattleshipWeb3Contract.methods
            .lock([offChainSig0, offChainSig1])
            .send({ from: player0, gas: 13000000 });
        const offchainStateChannelAddress = await OffchainBattleship.stateChannel();
        let offChainBattleshipStateChannel = await StateChannel.at(offchainStateChannelAddress);

        let dummyRandom = 1;
        let onChainState = await BattleShipGame.getState(dummyRandom);
        console.log(onChainState._h);

        let onChainHashStateWithAddress = sigTools.hashWithAddress(onChainState._h, OffchainBattleship.address);
        console.log(onChainHashStateWithAddress);
        // resolve coop
        const dummyRound = 1;
        const offchainPlayer0Sig = sigTools.chopUpSig(
            await sigTools.hashAndSignClose(
                onChainHashStateWithAddress,
                dummyRound,
                offChainBattleshipStateChannel.address,
                player0
            )
        );
        const offchainPlayer1Sig = sigTools.chopUpSig(
            await sigTools.hashAndSignClose(
                onChainHashStateWithAddress,
                dummyRound,
                offChainBattleshipStateChannel.address,
                player1
            )
        );
        // set state and close up
        await offChainBattleshipStateChannel.close(
            [...offchainPlayer0Sig, ...offchainPlayer1Sig],
            dummyRound,
            onChainHashStateWithAddress
        );
        console.log("here");
        let unlockOutput = await OffchainBattleship.unlock(
            onChainState._bool,
            onChainState._uints8,
            onChainState._uints,
            onChainState._winner,
            onChainState._maps,
            onChainState._shiphash,
            onChainState._x1,
            onChainState._y1,
            onChainState._x2,
            onChainState._y2,
            onChainState._sunk,
            { from: player0, gas: 3000000 }
        );

        console.log(unlockOutput.logs);
        console.log("no here");
        //assert.equal(true, false);
        // ///////////////////////

        // let offChainGameState = await setupGame(
        //     OffchainBattleship,
        //     player0,
        //     player1,
        //     constructBasicShips,
        //     constructBasicShips
        // );
        let { winner } = await playThrough5x5(OffchainBattleship, player0, player1, gameState);

        // now get the state and move it onto the state channel

        let {
            _bool,
            _uints8,
            _uints,
            _winner,
            _maps,
            _shiphash,
            _x1,
            _y1,
            _x2,
            _y2,
            _sunk,
            _h,
            preHash
        } = await OffchainBattleship.getState(dummyRandom);

        // hash the offchain state with the address of the on chain battleship contract
        let hashStateWithAddress = sigTools.hashWithAddress(_h, BattleShipGame.address);

        // resolve coop

        const player0Sig = sigTools.chopUpSig(
            await sigTools.hashAndSignClose(hashStateWithAddress, dummyRound, BattleshipStateChannel.address, player0)
        );
        const player1Sig = sigTools.chopUpSig(
            await sigTools.hashAndSignClose(hashStateWithAddress, dummyRound, BattleshipStateChannel.address, player1)
        );

        // set state and close up
        await BattleshipStateChannel.close([...player0Sig, ...player1Sig], dummyRound, hashStateWithAddress);

        // unlock the offchain state
        let output = await BattleShipGame.unlock(
            _bool,
            _uints8,
            _uints,
            _winner,
            _maps,
            _shiphash,
            _x1,
            _y1,
            _x2,
            _y2,
            _sunk,
            { from: player0, gas: 3000000 }
        );
        const unlockedWinner = await BattleShipGame.winner();
        assert.equal(unlockedWinner, winner);

        console.log("\t// FINALISE //");

        console.log(`\twinner ${winner} opening ships`);
        // get the ships

        await openShips(BattleShipGame, winner, winner === player0 ? gameState.player0.ships : gameState.player1.ships);

        console.log("\tfinish game");
        await increaseTimeStamp(30);
        await finishGame(BattleShipGame, winner);
        console.log("\twinner withdraws");
        await withdraw(BattleShipGame, winner, depositValue);

        // console.log("\t// FINALISE //");
        gasLibs.push({ test: "end-to-end-lock-unlock", gasLib });
        gasLibs.push({ test: "end-to-end-lock-unlock-off-chain", gasLib: offChainGasLib });
    });

    it("battleship end-to-end with lock unlock midway exit", async () => {
        if (!config.battleshipAndStateChannelMidwayExit) return;

        console.log("\tconstruct");
        const gasLib = [];
        const BattleShipGamePre = createGasProxy(BattleShipWithoutBoard, gasLib, web32);
        const BattleShipGame = await BattleShipGamePre.new(
            player0,
            player1,
            timerChallenge,
            theStateChannelFactory.address
        );

        // setup with basic boards
        let gameState = await setupGame(BattleShipGame, player0, player1, constructBasicShips, constructBasicShips);

        // now lockup
        let channelCounter = await BattleShipGame.channelCounter();
        let round = await BattleShipGame.round();

        let sig0 = await sigTools.hashAndSignLock(channelCounter, round, BattleShipGame.address, player0);
        let sig1 = await sigTools.hashAndSignLock(channelCounter, round, BattleShipGame.address, player1);

        // await BattleShipGame.lock([sig0, sig1]);
        let battleshipWeb3Contract = new web32.eth.Contract(BattleShipGame.abi, BattleShipGame.address);
        let lockTx = await battleshipWeb3Contract.methods.lock([sig0, sig1]).send({ from: player0, gas: 13000000 });
        gasLib.push({ method: "lock", gasUsed: lockTx.gasUsed });
        let channelOn = await BattleShipGame.statechannelon();
        assert.equal(channelOn, true);

        const stateChannelAddress = await BattleShipGame.stateChannel();
        let BattleshipStateChannel = await StateChannel.at(stateChannelAddress);

        const offChainGasLib = [];
        const OffchainBattleship = await createGasProxy(BattleShipWithoutBoard, offChainGasLib, web32).new(
            player0,
            player1,
            timerChallenge,
            theStateChannelFactory.address
        );
        let offChainGameState = await setupGame(
            OffchainBattleship,
            player0,
            player1,
            constructBasicShips,
            constructBasicShips
        );
        let { winner } = await playThrough5x5(OffchainBattleship, player0, player1, gameState, false, false, 30);

        // now get the state and move it onto the state channel
        let dummyRandom = 1;
        let {
            _bool,
            _uints8,
            _uints,
            _winner,
            _maps,
            _shiphash,
            _x1,
            _y1,
            _x2,
            _y2,
            _sunk,
            _h
        } = await OffchainBattleship.getState(dummyRandom);

        // hash the offchain state with the address of the on chain battleship contract
        let hashStateWithAddress = sigTools.hashWithAddress(_h, BattleShipGame.address);

        // resolve coop
        const dummyRound = 1;
        const player0Sig = sigTools.chopUpSig(
            await sigTools.hashAndSignClose(hashStateWithAddress, dummyRound, BattleshipStateChannel.address, player0)
        );
        const player1Sig = sigTools.chopUpSig(
            await sigTools.hashAndSignClose(hashStateWithAddress, dummyRound, BattleshipStateChannel.address, player1)
        );

        // set state and close up
        await BattleshipStateChannel.close([...player0Sig, ...player1Sig], dummyRound, hashStateWithAddress);

        // unlock the offchain state
        let output = await BattleShipGame.unlock(
            _bool,
            _uints8,
            _uints,
            _winner,
            _maps,
            _shiphash,
            _x1,
            _y1,
            _x2,
            _y2,
            _sunk,
            { from: player0, gas: 3000000 }
        );
        const onchainState = await BattleShipGame.getState(1);
        const offchainState = await OffchainBattleship.getState(1);
        assert.equal(offchainState._h, onchainState._h);

        console.log("\t// FINALISE //");

        // get the ships

        // await openShips(BattleShipGame, winner, winner === player0 ? offChainGameState.player0.ships : offChainGameState.player1.ships);

        // console.log("\tfinish game");
        // await increaseTimeStamp(30);
        // await finishGame(BattleShipGame, winner);
        // console.log("\twinner withdraws");
        // await withdraw(BattleShipGame, winner, depositValue);

        // console.log("\t// FINALISE //");
        gasLibs.push({ test: "end-to-end-lock-unlock-midway-exit", gasLib });
    });

    it("battleship lock unlock no update", async () => {
        if (!config.battleshipNoUpdate) return;

        console.log("\tconstruct");
        const gasLib = [];
        const BattleShipGamePre = createGasProxy(BattleShipWithoutBoard, gasLib, web32);
        const BattleShipGame = await BattleShipGamePre.new(
            player0,
            player1,
            timerChallenge,
            theStateChannelFactory.address
        );

        // setup with basic boards
        let gameState = await setupGame(BattleShipGame, player0, player1, constructBasicShips, constructBasicShips);

        // now lockup
        let channelCounter = await BattleShipGame.channelCounter();
        let round = await BattleShipGame.round();

        let sig0 = await sigTools.hashAndSignLock(channelCounter, round, BattleShipGame.address, player0);
        let sig1 = await sigTools.hashAndSignLock(channelCounter, round, BattleShipGame.address, player1);

        // await BattleShipGame.lock([sig0, sig1]);
        let battleshipWeb3Contract = new web32.eth.Contract(BattleShipGame.abi, BattleShipGame.address);
        let lockTx = await battleshipWeb3Contract.methods.lock([sig0, sig1]).send({ from: player0, gas: 13000000 });
        gasLib.push({ method: "lock", gasUsed: lockTx.gasUsed });
        let channelOn = await BattleShipGame.statechannelon();
        assert.equal(channelOn, true);

        const stateChannelAddress = await BattleShipGame.stateChannel();
        let BattleshipStateChannel = await StateChannel.at(stateChannelAddress);

        // // set state and close up
        await BattleshipStateChannel.triggerDispute({ from: player0 });

        // pass some time
        await web32.eth.sendTransaction({ from: player0, to: player1, value: 10 });
        await web32.eth.sendTransaction({ from: player0, to: player1, value: 10 });
        await web32.eth.sendTransaction({ from: player0, to: player1, value: 10 });
        await web32.eth.sendTransaction({ from: player0, to: player1, value: 10 });
        await web32.eth.sendTransaction({ from: player0, to: player1, value: 10 });
        await web32.eth.sendTransaction({ from: player0, to: player1, value: 10 });
        await web32.eth.sendTransaction({ from: player0, to: player1, value: 10 });
        await web32.eth.sendTransaction({ from: player0, to: player1, value: 10 });
        await web32.eth.sendTransaction({ from: player0, to: player1, value: 10 });
        await web32.eth.sendTransaction({ from: player0, to: player1, value: 10 });
        await web32.eth.sendTransaction({ from: player0, to: player1, value: 10 });
        await web32.eth.sendTransaction({ from: player0, to: player1, value: 10 });
        await web32.eth.sendTransaction({ from: player0, to: player1, value: 10 });
        await web32.eth.sendTransaction({ from: player0, to: player1, value: 10 });
        await web32.eth.sendTransaction({ from: player0, to: player1, value: 10 });
        await web32.eth.sendTransaction({ from: player0, to: player1, value: 10 });
        await web32.eth.sendTransaction({ from: player0, to: player1, value: 10 });
        await web32.eth.sendTransaction({ from: player0, to: player1, value: 10 });
        await web32.eth.sendTransaction({ from: player0, to: player1, value: 10 });
        await web32.eth.sendTransaction({ from: player0, to: player1, value: 10 });
        await web32.eth.sendTransaction({ from: player0, to: player1, value: 10 });

        //resolve
        await BattleshipStateChannel.resolve({ from: player0 });

        // unlock the offchain state
        let _bool = [0, 0, 0, 0, 0, 0],
            _uints8 = [0, 0],
            _uints = [0, 0, 0, 0, 0, 0],
            _winner = "0x0000000000000000000000000000000000000000",
            _maps = [0, 0, 0, 0, 0, 0, 0, 0],
            _shiphash = [
                "0x0000000000000000000000000000000000000000",
                "0x0000000000000000000000000000000000000000",
                "0x0000000000000000000000000000000000000000",
                "0x0000000000000000000000000000000000000000",
                "0x0000000000000000000000000000000000000000",
                "0x0000000000000000000000000000000000000000",
                "0x0000000000000000000000000000000000000000",
                "0x0000000000000000000000000000000000000000",
                "0x0000000000000000000000000000000000000000",
                "0x0000000000000000000000000000000000000000"
            ],
            _x1 = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            _y1 = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            _x2 = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            _y2 = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            _sunk = [false, false, false, false, false, false, false, false, false, false];

        await BattleShipGame.unlock(_bool, _uints8, _uints, _winner, _maps, _shiphash, _x1, _y1, _x2, _y2, _sunk, {
            from: player0,
            gas: 3000000
        });
        let sChannelOn = await BattleShipGame.statechannelon();
        assert.equal(sChannelOn, false);

        gasLibs.push({ test: "unlock-no-update", gasLib });
    });

    it("fraud challenge period expired", async () => {
        if (!config.fraudChallengePeriodExpired) return;
        const gasLib = [];
        const BattleShipGamePre = createGasProxy(BattleShipWithoutBoard, gasLib, web32);
        const BattleShipGame = await BattleShipGamePre.new(
            player0,
            player1,
            // 0 challenge period to simulate time
            timerChallenge,
            theStateChannelFactory.address
        );

        // setup with basic boards
        let gameState = await setupGame(BattleShipGame, player0, player1, constructBasicShips, constructBasicShips);

        let move0 = await attackAndReveal(
            BattleShipGame,
            player0,
            0,
            0,
            0,
            player1,
            gameState.player1.board,
            gameState.player1.ships,
            {}
        );

        // call the challenge expired
        await increaseTimeStamp(30);
        await increaseTimeStamp(30);
        await BattleShipGame.fraudChallengeExpired();
        let phase = await BattleShipGame.phase();
        assert.equal(phase.toNumber(), Phase.Win);

        gasLibs.push({ test: "fraud-challenge-period-expired", gasLib });
    });

    it("simple test fraud ships same cell", async () => {
        if (!config.fraudShipsSameCell) return;
        console.log("\tconstruct");
        const gasLib = [];
        const BattleShipGame = await createGasProxy(BattleShipWithoutBoard, gasLib, web32).new(
            player0,
            player1,
            timerChallenge,
            theStateChannelFactory.address
        );

        // player 0 puts all ships on top of each other, so player 1 will not be able to win
        // they should be able to commit a fraud proof after though
        let gameState = await setupGame(BattleShipGame, player0, player1, constructSameCellShips, constructBasicShips);
        let { winner } = await playThrough5x5(BattleShipGame, player0, player1, gameState);
        assert.equal(winner, player0);
        console.log("\t// FINALISE //");

        let notWinner = winner === player0 ? player1 : player0;
        console.log(`\twinner ${winner} opening ships`);
        await openShips(BattleShipGame, winner, winner === player0 ? gameState.player0.ships : gameState.player1.ships);

        console.log("\tpresent fraud at (0, 0)");
        await fraudShipsSameCell(BattleShipGame, notWinner, 0, 1, 0, 0);

        console.log("\tfinish game");
        console.log("\twinner withdraws");
        await withdraw(BattleShipGame, notWinner, depositValue);

        console.log("\t// FINALISE //");
        gasLibs.push({ test: "fraud-ships-same-cell", gasLib });
    });

    it("simple test fraud attack same cell", async () => {
        if (!config.fraudAttackSameCell) return;
        console.log("\tconstruct");
        const gasLib = [];
        const BattleShipGamePre = createGasProxy(BattleShipWithoutBoard, gasLib, web32);
        const BattleShipGame = await BattleShipGamePre.new(
            player0,
            player1,
            timerChallenge,
            theStateChannelFactory.address
        );

        // setup with basic boards
        let gameState = await setupGame(BattleShipGame, player0, player1, constructBasicShips, constructBasicShips);

        let move0 = await attackAndReveal(
            BattleShipGame,
            player0,
            0,
            0,
            0,
            player1,
            gameState.player1.board,
            gameState.player1.ships,
            {}
        );
        let move1 = await attackAndReveal(
            BattleShipGame,
            player1,
            0,
            0,
            0,
            player0,
            gameState.player0.board,
            gameState.player0.ships,
            {}
        );
        let move2 = await attackAndReveal(
            BattleShipGame,
            player0,
            0,
            0,
            0,
            player1,
            gameState.player1.board,
            gameState.player1.ships,
            {}
        );

        console.log("\t// FINALISE //");
        // player 0 has no played at the same location twice, fraud
        console.log("player 1 calls fraudAttackSameCell");

        let fraud = await fraudAttackSameCell(BattleShipGame, player1, 0, 4, 0, 0, move0.attackSig, move2.attackSig);
        gasLib.push(fraud);
        console.log("\twinner withdraws");
        // await withdraw(BattleShipGame, player1, depositValue);

        console.log("\t// FINALISE //");
        gasLibs.push({ test: "fraud-attack-same-cell", gasLib });
    });

    it("simple test fraud declared not miss", async () => {
        if (!config.fraudDeclaredNotMiss) return;
        console.log("\tconstruct");
        const gasLib = [];
        const BattleShipGame = await createGasProxy(BattleShipWithoutBoard, gasLib, web32).new(
            player0,
            player1,
            timerChallenge,
            theStateChannelFactory.address
        );

        // player 0 inverts their board when revealing, this means they sometimes declare things as a hit which should be a miss
        let gameState = await setupGame(BattleShipGame, player0, player1, constructBasicShips, constructBasicShips);
        let { winner, reveals } = await playThrough5x5(
            BattleShipGame,
            player0,
            player1,
            gameState,
            false,
            true,
            400,
            true
        );
        assert.equal(winner, player0);
        console.log("\t// FINALISE //");

        let notWinner = winner === player0 ? player1 : player0;
        console.log(`\twinner ${winner} opening ships`);
        await openShips(BattleShipGame, winner, winner === player0 ? gameState.player0.ships : gameState.player1.ships);

        // move 39, (1, 4) was declared as a hit, but should be a miss
        console.log("\tpresent fraud at move 39");
        await fraudDeclaredNotMiss(BattleShipGame, notWinner, 1, 4, 39, reveals[39].sig);

        console.log("\tfinish game");
        console.log("\twinner withdraws");
        await withdraw(BattleShipGame, notWinner, depositValue);

        console.log("\t// FINALISE //");
        gasLibs.push({ test: "fraud-declared-not-miss", gasLib });
    });

    it("simple test fraud declared not hit", async () => {
        if (!config.fraudDeclaredNotHit) return;
        console.log("\tconstruct");
        const gasLib = [];
        const BattleShipGame = await createGasProxy(BattleShipWithoutBoard, gasLib, web32).new(
            player0,
            player1,
            timerChallenge,
            theStateChannelFactory.address
        );

        // player 0 puts all ships on top of each other, so player 1 will not be able to win
        // they should be able to commit a fraud proof after though
        let gameState = await setupGame(BattleShipGame, player0, player1, constructSameCellShips, constructBasicShips);
        let { winner, reveals } = await playThrough5x5(BattleShipGame, player0, player1, gameState, true);
        assert.equal(winner, player0);
        console.log("\t// FINALISE //");

        let notWinner = winner === player0 ? player1 : player0;
        console.log(`\twinner ${winner} opening ships`);
        await openShips(BattleShipGame, winner, winner === player0 ? gameState.player0.ships : gameState.player1.ships);

        console.log("\tpresent fraud at move 1");
        await fraudDeclaredNotHit(BattleShipGame, notWinner, 0, 0, 0, 3, reveals[3].sig);

        console.log("\tfinish game");
        console.log("\twinner withdraws");
        await withdraw(BattleShipGame, notWinner, depositValue);

        console.log("\t// FINALISE //");
        gasLibs.push({ test: "fraud-declared-not-hit", gasLib });
    });

    it("simple test fraud declared not sunk", async () => {
        // we need web3 1.0.0-beta.36 to run this test, as we need abiencoderv2 support
        if (!config.fraudDeclaredNotSunk) return;
        console.log("\tconstruct");
        const gasLib = [];
        const BattleShipGame = await createGasProxy(BattleShipWithoutBoard, gasLib, web32).new(
            player0,
            player1,
            timerChallenge,
            theStateChannelFactory.address
        );

        // player 0 puts all ships on top of each other, so player 1 will not be able to win
        // they should be able to commit a fraud proof after though
        let gameState = await setupGame(BattleShipGame, player0, player1, constructBasicShips, constructBasicShips);
        let { winner, reveals } = await playThrough5x5(BattleShipGame, player0, player1, gameState, false, true);

        assert.equal(winner, player0);
        console.log("\t// FINALISE //");

        let notWinner = winner === player0 ? player1 : player0;
        console.log(`\twinner ${winner} opening ships`);
        await openShips(BattleShipGame, winner, winner === player0 ? gameState.player0.ships : gameState.player1.ships);

        console.log("\tpresent fraud at move 3, 7, 11, 15, 19");
        let moves = [3, 7, 11, 15, 19];
        let fraudMove = await fraudDeclaredNotSunk(BattleShipGame, notWinner, 0, moves, moves.map(m => reveals[m].sig));
        gasLib.push(fraudMove);

        console.log("\tfinish game");
        console.log("\twinner withdraws");
        await withdraw(BattleShipGame, notWinner, depositValue);

        console.log("\t// FINALISE //");
        gasLibs.push({ test: "fraud-declared-not-sunk", gasLib });
    });
    after(() => {
        gasLibs.forEach(g => {
            console.log();
            console.log(g.test);
            logGasLib(g.gasLib);
            console.log();
        });
    });
});

const Phase = Object.freeze({
    Setup: 0,
    Attack: 1,
    Reveal: 2,
    Win: 3,
    Fraud: 4
});

const fraudAttackSameCell = async (contract, player, move1, move2, x, y, move1Sig, move2Sig) => {
    let abiV2Battleship = new web32.eth.Contract(BattleShipWithoutBoard.abi, contract.address);
    const attack = await abiV2Battleship.methods
        .fraudAttackSameCell(move1, move2, x, y, [move1Sig, move2Sig])
        .send({ from: player, gas: 13000000 });
    let phase = await contract.phase();
    assert.equal(phase.toNumber(), Phase.Win);
    return { method: "fraudAttackSameCell", gasUsed: attack.gasUsed };
};

const fraudShipsSameCell = async (contract, player, shipIndex1, shipIndex2, x, y) => {
    await contract.fraudShipsSameCell(shipIndex1, shipIndex2, x, y, { from: player });
    let phase = await contract.phase();
    // after fraud is declard we expect to have reset
    assert.equal(phase.toNumber(), Phase.Setup);
};

const fraudDeclaredNotHit = async (contract, player, shipIndex1, x, y, moveCtr, signature) => {
    await contract.fraudDeclaredNotHit(shipIndex1, x, y, moveCtr, signature, { from: player });
    let phase = await contract.phase();
    // after fraud is declard we expect to have reset
    assert.equal(phase.toNumber(), Phase.Setup);
};

const fraudDeclaredNotMiss = async (contract, player, x, y, moveCtr, signature) => {
    await contract.fraudDeclaredNotMiss(x, y, moveCtr, signature, { from: player });
    let phase = await contract.phase();
    // after fraud is declard we expect to have reset
    assert.equal(phase.toNumber(), Phase.Setup);
};

const fraudDeclaredNotSunk = async (contract, player, shipIndex, moves, signatures) => {
    let abiV2Battleship = new web32.eth.Contract(BattleShipWithoutBoard.abi, contract.address);

    const fraud = await abiV2Battleship.methods
        .fraudDeclaredNotSunk(shipIndex, moves, signatures)
        .send({ from: player, gas: 3000000 });

    let phase = await contract.phase();
    // after fraud is declard we expect to have reset
    assert.equal(phase.toNumber(), Phase.Setup);

    return { method: "fraudDeclaredNotSunk", gasUsed: fraud.gasUsed };
};
