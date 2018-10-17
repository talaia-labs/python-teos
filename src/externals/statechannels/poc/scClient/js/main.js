import { StateChannel } from "./stateChannel";
import Web3 from "web3";
//let web3;
// window.localWeb3 = 20;
// window.face = () => {
//     console.log(web3);
//     console.log(web3.currentProvider);
//     localWeb3 = new Web3("http://localhost:9545")
//     web3 = new Web3(web3.currentProvider);
//     console.log(localWeb3.currentProvider);
//     console.log(web3.currentProvider);
// };
// face();
web3 = new Web3("http://localhost:9545");
window.web3 = web3;

const ACCOUNT_TRANSACTING = "0x627306090abab3a6e1400e9345bc60c78a8bef57";
const PLAYER1ADDRESS = "0xf17f52151ebef6c7334fad080c5704d77216b732";
const PLAYER2ADDRESS = "0xc5fdf4076b8f3a5357c5e395ab970b5b54098fef";

const DISPUTE_PERIOD = 10;
const stateChannel = new StateChannel(web3);
let currentCounter = 1;
const alphabet = "abcdefghijklmnopqrstuvwxyz";

const deployButton = () => document.getElementById("deployContract");
const deployedContractAddress = () => document.getElementById("deployedContractAddress");
const incrementCounterButton = () => document.getElementById("counterButton");
const counterContent = () => document.getElementById("counterContent");

const player1Round = () => document.getElementById("player1Round");
const player1State = () => document.getElementById("player1State");
const player1SignButton = () => document.getElementById("player1SignButton");
const player1Signatures = () => document.getElementById("player1Signatures");
const player2Round = () => document.getElementById("player2Round");
const player2State = () => document.getElementById("player2State");
const player2SignButton = () => document.getElementById("player2SignButton");
const player2Signatures = () => document.getElementById("player2Signatures");
const player1RoundH = () => document.getElementById("player1RoundH");
const player1StateH = () => document.getElementById("player1StateH");
const player1SignButtonH = () => document.getElementById("player1SignButtonH");
const player2RoundH = () => document.getElementById("player2RoundH");
const player2StateH = () => document.getElementById("player2StateH");
const player2SignButtonH = () => document.getElementById("player2SignButtonH");
const triggerDisputeButton = () => document.getElementById("triggerDisputeButton");
const disputingPlayerAddress = () => document.getElementById("disputingPlayerAddress");
const triggerDisputeFeedback = () => document.getElementById("triggerDisputeFeedback");
const setStatePlayer1Sig = () => document.getElementById("setStatePlayer1Sig");
const setStatePlayer2Sig = () => document.getElementById("setStatePlayer2Sig");
const setStateRound = () => document.getElementById("setStateRound");
const setStateHState = () => document.getElementById("setStateHState");
const setStateButton = () => document.getElementById("setStateButton");
const setStatePlayer = () => document.getElementById("setStatePlayer");
const setStateFeedback = () => document.getElementById("setStateFeedback");
const blockCounter = () => document.getElementById("blockCounter");
const mineBlockButton = () => document.getElementById("mineBlockButton");
const resolvePlayerAddress = () => document.getElementById("resolvePlayerAddress");
const resolveButton = () => document.getElementById("resolveButton");
const resolveFeedback = () => document.getElementById("resolveFeedback");

const deployHandler = async () => {
    let deployedStateChannel = await stateChannel.deploy(
        ACCOUNT_TRANSACTING,
        [PLAYER1ADDRESS, PLAYER2ADDRESS],
        DISPUTE_PERIOD
    );
    deployedContractAddress().innerHTML = `<div>State channel deployed at: ${
        deployedStateChannel.options.address
    }<br/>Participants: ${PLAYER1ADDRESS}, ${PLAYER2ADDRESS}<br/>Dispute period: ${DISPUTE_PERIOD}</div>`;
};

const chopUpSig = sig => {
    const removedHexNotation = sig.slice(2);
    var r = `0x${removedHexNotation.slice(0, 64)}`;
    var s = `0x${removedHexNotation.slice(64, 128)}`;
    var v = `0x${removedHexNotation.slice(128, 130)}`;
    return [v, r, s];
};

const setStateHandler = async () => {
    const sigs = chopUpSig(setStatePlayer1Sig().value).concat(chopUpSig(setStatePlayer2Sig().value));

    const setState = await stateChannel.setState(
        setStatePlayer().value,
        sigs,
        setStateRound().value,
        setStateHState().value
    );

    const stateItem = document.createElement("li");
    stateItem.innerHTML = `bestround: ${setState.bestRound}, hstate: ${setState.hState}`;

    setStateFeedback().appendChild(stateItem);
};

const triggerDisputeHandler = async () => {
    const deadline = await stateChannel.triggerDispute(disputingPlayerAddress().value);

    triggerDisputeFeedback().innerHTML = "Dispute triggered. Deadline: " + deadline;
};

const incrementCounterHandler = () => {
    const text = `round: ${currentCounter}, state: ${alphabet[currentCounter - 1]}`;

    let div = document.createElement("div");
    div.appendChild(document.createElement("div").appendChild(document.createTextNode(text)));

    counterContent().appendChild(div);
    currentCounter++;
};

const signAndRecord = async (round, state, sigContentsBox, stateChannelAddress, playerAddress) => {
    const hStateAndSig = await hashAndSign(round, state, stateChannelAddress, playerAddress);

    const roundItem = document.createElement("li");
    roundItem.innerHTML = "round: " + round;

    const stateItem = document.createElement("li");
    stateItem.innerHTML = "state: " + state;

    const hStateItem = document.createElement("li");
    hStateItem.innerHTML = "hState: " + hStateAndSig.hState;

    const sigItem = document.createElement("li");
    sigItem.innerHTML = "sig: " + hStateAndSig.sig;

    const list = document.createElement("ul");
    list.appendChild(roundItem);
    list.appendChild(stateItem);
    list.appendChild(hStateItem);
    list.appendChild(sigItem);
    sigContentsBox.appendChild(list);
};

const hashAndSign = async (round, hState, channelAddress, playerAddress) => {
    let msg = web3.utils.soliditySha3(
        {
            t: "bytes32",
            v: hState
        },
        {
            t: "uint256",
            v: round
        },
        {
            t: "address",
            v: channelAddress
        }
    );
    const sig = await web3.eth.sign(msg, playerAddress);
    return { hState, sig };
};

const resolveHandler = async () => {
    const round = await stateChannel.resolve(resolvePlayerAddress().value);

    resolveFeedback().innerHTML = "Resolve occured. Round: " + round;
};

const startBlockCounterClock = () => {
    setInterval(async () => {
        const blockNumber = await web3.eth.getBlockNumber();

        blockCounter().innerHTML = blockNumber;
    }, 100);
};

// dummy method for mining a block
const mineABlock = () => {
    // make any transaction
    web3.eth.sendTransaction({ to: PLAYER1ADDRESS, from: PLAYER2ADDRESS, value: web3.utils.toWei("0.001", "ether") });
};

// TODO: //
// what happens when we try to re-use the state channel for multiple contracts?
// TODO: //

// initialise
document.addEventListener("DOMContentLoaded", () => {
    startBlockCounterClock();

    mineBlockButton().addEventListener("click", mineABlock);
    deployButton().addEventListener("click", deployHandler);
    triggerDisputeButton().addEventListener("click", triggerDisputeHandler);
    setStateButton().addEventListener("click", setStateHandler);

    incrementCounterButton().addEventListener("click", incrementCounterHandler);
    player1SignButton().addEventListener("click", async () => {
        await signAndRecord(
            player1Round().value,
            web3.utils.sha3(player1State().value),
            player1Signatures(),
            stateChannel.address(),
            PLAYER1ADDRESS
        );
    });
    player1SignButtonH().addEventListener("click", async () => {
        await signAndRecord(
            player1RoundH().value,
            player1StateH().value,
            player1Signatures(),
            stateChannel.address(),
            PLAYER1ADDRESS
        );
    });
    player2SignButton().addEventListener("click", async () => {
        await signAndRecord(
            player2Round().value,
            web3.utils.sha3(player2State().value),
            player2Signatures(),
            stateChannel.address(),
            PLAYER2ADDRESS
        );
    });
    player2SignButtonH().addEventListener("click", async () => {
        await signAndRecord(
            player2RoundH().value,
            player2StateH().value,
            player2Signatures(),
            stateChannel.address(),
            PLAYER2ADDRESS
        );
    });
    resolveButton().addEventListener("click", resolveHandler);
});
