// setup and state
let web3 = new Web3(new Web3.providers.HttpProvider("http://127.0.0.1:9545/"));

let rps;
const DEPOSIT_AMOUNT = 25;
const BET_AMOUNT = 100;
const REVEAL_SPAN = 10;
const applicationState = {
    stage: async () => {
        return await rps.methods.stage().call();
    },
    locked: async () => {
        return await rps.methods.locked().call();
    },
    players: async () => {
        let player0 = await rps.methods.players(0).call();
        let player1 = await rps.methods.players(1).call();
        return [player0, player1];
    },
    gameState: async () => {
        return await rps.methods.getStateHash().call();
    },
    resetGameState: async () => {
        let currentGameState = await applicationState.gameState();
        gameState().innerHTML = `Current game state: ${currentGameState}`;
    },
    resetLock: lockStatusValue => {
        lockStatus().innerHTML = lockStatusValue ? "Locked" : "Unlocked";
    },
    resetLockFromContract: async () => {
        applicationState.resetLock(await applicationState.locked());
    },
    resetCommitments: async () => {
        commitmentsMade().innerHTML = "";
        let players = await applicationState.players();
        players.forEach(player => {
            if (player.commitment != 0) {
                let li = document.createElement("li");
                li.appendChild(
                    document.createTextNode(`Player: ${player.playerAddress} made commitment: ${player.commitment}`)
                );
                commitmentsMade().appendChild(li);
            }
        });
    },
    resetReveals: async () => {
        revealsMade().innerHTML = "";
        let players = await applicationState.players();
        players.forEach(player => {
            if (player.choice != 0) {
                let li = document.createElement("li");
                li.appendChild(
                    document.createTextNode(`Player: ${player.playerAddress} revealed choice: ${player.choice}`)
                );
                revealsMade().appendChild(li);
            }
        });
    },
    resetAllState: async () => {
        await applicationState.resetGameState();
        await applicationState.resetLockFromContract();
        await applicationState.resetCommitments();
        await applicationState.resetReveals();
    }
};

// selectors
let stateChannelAddress = () => document.getElementById("state-channel-address");
let deployButton = () => document.getElementById("deploy-contract");
let addressDropDown = () => document.getElementById("address-selector");
let connectContractInput = () => document.getElementById("connect-contract-address");
let connectContractButton = () => document.getElementById("connect-contract-button");
let deployedContractAddress = () => document.getElementById("deployed-contract-address");
let lock = () => document.getElementById("lock");
let unlock = () => document.getElementById("unlock");
let lockStatus = () => document.getElementById("lock-status");
let unlockStage = () => document.getElementById("unlock-stage");
let unlockAddress0 = () => document.getElementById("unlock-address0");
let unlockCommitment0 = () => document.getElementById("unlock-commitment0");
let unlockChoice0 = () => document.getElementById("unlock-choice0");
let unlockAddress1 = () => document.getElementById("unlock-address1");
let unlockCommitment1 = () => document.getElementById("unlock-commitment1");
let unlockChoice1 = () => document.getElementById("unlock-choice1");

let gameContainer = () => document.getElementById("game-container");
let gameState = () => document.getElementById("game-state");
let playerSelector = () => document.getElementById("player-selector");
let commitmentChoice = () => document.getElementById("commitment-choice");
let commitmentRand = () => document.getElementById("commit-random-number");
let commitButton = () => document.getElementById("commit");
let commitmentsMade = () => document.getElementById("commitments-made");
let revealChoice = () => document.getElementById("reveal-choice");
let revealRand = () => document.getElementById("reveal-random-number");
let revealButton = () => document.getElementById("reveal");
let revealsMade = () => document.getElementById("reveals-made");
let distributeButton = () => document.getElementById("distribute");
let distributeResults = () => document.getElementById("distribute-results");

// initial population
let populateAddresses = async element => {
    let accounts = await web3.eth.getAccounts();
    element.innerHTML = accounts.map(a => createAddressOption(a)).reduce((a, b) => a + b);
};

let createAddressOption = address => {
    return `<option value=${address}>${address}</option>`;
};

// util
let choiceToNumber = choiceString => {
    if (choiceString == "rock") return 1;
    if (choiceString == "paper") return 2;
    if (choiceString == "scissors") return 3;
    throw new Error("unrecognised choice");
};

// event handlers
async function deployNewContract(bytecode, abi, betAmount, depositAmount, revealSpan, deployingAccount, stateChannel) {
    let rockPaperScissors = new web3.eth.Contract(abi);
    return await rockPaperScissors
        .deploy({
            data: bytecode,
            arguments: [betAmount, depositAmount, revealSpan, stateChannel]
        })
        .send({
            from: deployingAccount,
            gas: 2000000,
            gasPrice: 1
        });
}

let deployHandler = async () => {
    let addressSelection = addressDropDown().value;
    console.log("Address selected for deployment:", addressSelection);
    let stateChannel = stateChannelAddress().value;

    let deployedContract = await deployNewContract(
        RPS_BYTECODE,
        RPS_ABI,
        BET_AMOUNT,
        DEPOSIT_AMOUNT,
        REVEAL_SPAN,
        addressSelection,
        stateChannel
    );
    console.log(`Contract deployed at: ${deployedContract.options.address} with state channel ${stateChannel}`);

    rps = deployedContract;
    deployedContractAddress().innerHTML = `Contract deployed at: <b>${
        rps.options.address
    }</b> with state channel <b>${stateChannel}</b>`;
    gameContainer().hidden = false;

    await applicationState.resetAllState();
};

let connectHandler = async () => {
    //0xF12b5dd4EAD5F743C6BaA640B0216200e89B60Da
    let contractAddress = connectContractInput().value;
    let deployedContract = new web3.eth.Contract(RPS_ABI, contractAddress);
    console.log("Contract connected at: ", deployedContract.options.address);

    rps = deployedContract;

    let channel = await rps.methods.stateChannel().call();

    deployedContractAddress().innerHTML = `Contract deployed at: <b>${
        rps.options.address
    }</b> with state channel <b>${channel}</b>`;
    gameContainer().hidden = false;

    await applicationState.resetAllState();
};

let lockHandler = async () => {
    let receipt = await rps.methods.lock().send({
        from: addressDropDown().value
    });

    console.log("Game locked");

    // reset the lock status
    await applicationState.resetLockFromContract();
};

let unlockHandler = async () => {
    let receipt = await rps.methods
        .unlock(
            unlockStage().value,
            unlockAddress0().value,
            unlockCommitment0().value,
            unlockChoice0().value,
            unlockAddress1().value,
            unlockCommitment1().value,
            unlockChoice1().value
        )
        .send({
            from: addressDropDown().value,
            gas: 2000000
        });

    console.log("Game unlocked");

    await applicationState.resetAllState();
};

let commitHandler = async () => {
    // get the player
    let player = playerSelector().value;

    // get the choice and the rand
    let choice = choiceToNumber(commitmentChoice().value);
    let rand = web3.utils.fromAscii(commitmentRand().value);

    let commitment = web3.utils.soliditySha3(
        { t: "address", v: player },
        { t: "uint8", v: choice },
        { t: "bytes32", v: rand }
    );
    console.log(`Player: ${player} making commitment : ${commitment}`);

    // make the commitment
    let transactionReceipt = await rps.methods
        .commit(commitment)
        .send({ from: player, value: BET_AMOUNT + DEPOSIT_AMOUNT, gas: 200000 });
    console.log("Commitment mined in transaction: ", transactionReceipt);

    // wipe the selections
    commitmentChoice().value = -1;
    commitmentRand().value = "";

    await applicationState.resetGameState();
    await applicationState.resetCommitments();
};

let revealHandler = async () => {
    // get the player
    let player = playerSelector().value;

    // get the choice and the rand
    let choice = choiceToNumber(revealChoice().value);
    let rand = web3.utils.fromAscii(revealRand().value);

    //TODO: interesting constraint on the ordering here:
    console.log(`Player: ${player} revealing choice: ${choice} with blinding factor: ${rand}`);

    // make the commitment
    let transactionReceipt = await rps.methods.reveal(choice, rand).send({ from: player });
    console.log("Reveal mined in transaction: ", transactionReceipt);

    // wipe the selections
    revealChoice().value = -1;
    revealRand().value = "";

    await applicationState.resetGameState();
    await applicationState.resetReveals();
};

let distributeHandler = async () => {
    // get the player
    let player = playerSelector().value;
    // call distribute
    let transactionReceipt = await rps.methods.distribute().send({ from: player, gas: 200000 });
    console.log("Distribute mined in transaction: ", transactionReceipt);
    let balances = transactionReceipt.events["Payout"].map(e => {
        return {
            player: e.returnValues.player,
            amount: e.returnValues.amount
        };
    });

    balances.forEach(b => {
        let li = document.createElement("li");
        li.appendChild(document.createTextNode(`Player: ${b.player} has received: ${b.amount}.`));
        distributeResults().appendChild(li);
    });

    await applicationState.resetGameState();
};

// initialise
document.addEventListener("DOMContentLoaded", function(event) {
    // populate the address list
    populateAddresses(addressDropDown());

    // set the handler on the deploy
    deployButton().addEventListener("click", deployHandler);

    // set the handler on the connect
    connectContractButton().addEventListener("click", connectHandler);

    // set the current lock status
    applicationState.resetLock(false);

    // set th lock and unlock handlers
    lock().addEventListener("click", lockHandler);
    unlock().addEventListener("click", unlockHandler);

    // populate the players
    populateAddresses(playerSelector());

    // commit handler
    commitButton().addEventListener("click", commitHandler);

    // reveal handler
    revealButton().addEventListener("click", revealHandler);

    // distribute handler
    distributeButton().addEventListener("click", distributeHandler);
});
