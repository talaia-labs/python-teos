import { call, takeEvery, select, put } from "redux-saga/effects";
import { Action, ActionType } from "../action/rootAction";
import { Contract } from "web3-eth-contract";
import Web3 = require("web3");
import { BigNumber } from "bignumber.js";
import Web3Util from "web3-utils";
import { Selector } from "../store";
import { Reveal } from "./../entities/gameEntities";

export default function* attackReveal() {
    yield takeEvery(ActionType.ATTACK_INPUT, attackInput);
    yield takeEvery(ActionType.ATTACK_BROADCAST, attackBroadcast);
    yield takeEvery(ActionType.REVEAL_INPUT, revealInput);
    yield takeEvery(ActionType.REVEAL_BROADCAST, revealBroadcast);
}

export function* attackInput(action: ReturnType<typeof Action.attackInput>) {
    // TODO: transition current action type to 'attacking' or something?
    const battleshipContract: ReturnType<typeof Selector.onChainBattleshipContract> = yield select(
        Selector.onChainBattleshipContract
    );
    const player: ReturnType<typeof Selector.player> = yield select(Selector.player);

    // sign the x,y,move_ctr,round,address hash
    const moveCtr: BigNumber = yield call(battleshipContract.methods.move_ctr().call);
    const round: BigNumber = yield call(battleshipContract.methods.round().call);
    const web3: ReturnType<typeof Selector.web3> = yield select(Selector.web3);

    const sig: string = yield call(
        hashAndSignAttack,
        action.payload.x,
        action.payload.y,
        moveCtr,
        round,
        player.address,
        battleshipContract.options.address,
        web3
    );

    // TODO: dont do get hash state for just an attack
    const { hashState, hashStateSig } = yield call(
        attackApplyAndGetHashState,
        battleshipContract,
        action.payload.x,
        action.payload.y,
        sig,
        player.address,
        web3
    );

    // inform the opponent
    // TODO: it isnt strictly necessary to have any communication during the blockchain phase
    const counterparty: ReturnType<typeof Selector.counterparty> = yield select(Selector.counterparty);
    const attackBroadcastAction = Action.attackBroadcast(
        action.payload.x,
        action.payload.y,
        sig,
        hashState,
        hashStateSig
    );

    yield call(counterparty.sendAttack, attackBroadcastAction);

    // TODO: reducer for this
    // yield put(Action.updateCurrentActionType(ActionType.REVEAL_BROADCAST_AWAIT));

    // TODO: all "call" can throw errors
}

export function* attackBroadcast(action: ReturnType<typeof Action.attackBroadcast>) {
    // store the attack locally
    yield put(
        Action.moveCreate({
            x: action.payload.x,
            y: action.payload.y,
            // TODO: hack below -get actual values
            moveCtr: 0,
            round: 0,
            hashState: action.payload.hashState,
            moveSig: action.payload.onChainAttackSig,
            // TODO: hack below, needs removing
            channelSig: ""
            // TODO: this should be the counterparty sig!
            //hashStateCounterPartySig: action.payload.hashStateSig
        })
    );

    // transition to the awaiting the reveal input
    yield put(Action.updateCurrentActionType(ActionType.REVEAL_INPUT_AWAIT));
}

export function* revealInput(action: ReturnType<typeof Action.revealInput>) {
    // reveal in the contract
    const battleshipContract: ReturnType<typeof Selector.onChainBattleshipContract> = yield select(
        Selector.onChainBattleshipContract
    );
    const player: ReturnType<typeof Selector.player> = yield select(Selector.player);
    const latestMove: ReturnType<typeof Selector.latestMove> = yield select(Selector.latestMove);

    // sign the x,y,move_ctr,round,address hash
    const moveCtr: BigNumber = yield call(battleshipContract.methods.move_ctr().call);
    const round: BigNumber = yield call(battleshipContract.methods.round().call);
    const web3: ReturnType<typeof Selector.web3> = yield select(Selector.web3);
    // if reveal is a hit or miss
    if (action.payload.reveal === Reveal.Hit || action.payload.reveal === Reveal.Miss) {
        const sig: string = yield call(
            hashAndSignReveal,
            latestMove.x,
            latestMove.y,
            moveCtr,
            round,
            player.address,
            action.payload.reveal === Reveal.Hit,
            battleshipContract.options.address,
            web3
        );

        const hit = action.payload.reveal === Reveal.Hit;
        yield call(battleshipContract.methods.revealslot(hit, sig).send, { from: player.address, gas: 300000 });
    } else {
        // it was a sink
        const sig: string = yield call(
            hashAndSignRevealSunk,
            action.payload.x1 as number,
            action.payload.y1 as number,
            action.payload.x2 as number,
            action.payload.y2 as number,
            action.payload.r as number,
            moveCtr,
            round,
            player.address,
            action.payload.shipIndex,
            battleshipContract.options.address,
            web3
        );
        yield call(
            battleshipContract.methods.revealsunk(
                action.payload.shipIndex,
                action.payload.x1,
                action.payload.y1,
                action.payload.x2,
                action.payload.y2,
                action.payload.r,
                sig
            ).send,
            { from: player.address, gas: 300000 }
        );
    }

    // boradcast the reveal
    const revealBroadcastAction = Action.revealBroadcast(action.payload.reveal);
    const counterparty: ReturnType<typeof Selector.counterparty> = yield select(Selector.counterparty);
    yield call(counterparty.sendReveal, revealBroadcastAction);

    // TODO: if we're not checking the state - I dont think we need have an await broadcast action type

    // we've sent the reveal - no wait for attack input
    yield put(Action.updateCurrentActionType(ActionType.ATTACK_INPUT_AWAIT));
}

export function* revealBroadcast(action: ReturnType<typeof Action.revealBroadcast>) {
    // they've reveal to us, lets transition to awaiting an attack broadcast
    //
    // TODO: no need to update the current action type atm - just make a record of the reveal
}

export function hashAttack(x: number, y: number, moveCtr: BigNumber, round: BigNumber, contractAddress: string) {
    return Web3Util.soliditySha3(
        { t: "uint8", v: x },
        { t: "uint8", v: y },
        { t: "uint", v: moveCtr },
        { t: "uint", v: round },
        { t: "address", v: contractAddress }
    );
}

export function* hashAndSignAttack(
    x: number,
    y: number,
    moveCtr: BigNumber,
    round: BigNumber,
    playerAddress: string,
    contractAddress: string,
    web3: Web3
) {
    const attackHash = hashAttack(x, y, moveCtr, round, contractAddress);
    const sig = yield call(web3.eth.sign, attackHash, playerAddress);
    return sig;
}

export function hashReveal(
    x: number,
    y: number,
    moveCtr: BigNumber | number,
    round: BigNumber | number,
    hit: Boolean,
    contractAddress: string
) {
    return Web3Util.soliditySha3(
        { t: "uint8", v: x },
        { t: "uint8", v: y },
        { t: "bool", v: hit },
        { t: "uint", v: moveCtr },
        { t: "uint", v: round },
        { t: "address", v: contractAddress }
    );
}

export function* hashAndSignReveal(
    x: number,
    y: number,
    moveCtr: BigNumber,
    round: BigNumber,
    player: string,
    hit: Boolean,
    contractAddress: string,
    web3: Web3
) {
    const revealHash = hashReveal(x, y, moveCtr, round, hit, contractAddress);
    return yield call(web3.eth.sign, revealHash, player);
}

export function hashRevealSunk(
    x1: number,
    y1: number,
    x2: number,
    y2: number,
    r: number,
    moveCtr: BigNumber,
    round: BigNumber,
    shipIndex: number,
    contractAddress: string
) {
    return Web3Util.soliditySha3(
        { t: "uint8", v: x1 },
        { t: "uint8", v: y1 },
        { t: "uint8", v: x2 },
        { t: "uint8", v: y2 },
        { t: "uint", v: r },
        { t: "uint", v: shipIndex },
        { t: "uint", v: moveCtr },
        { t: "uint", v: round },
        { t: "address", v: contractAddress }
    );
}

export function* hashAndSignRevealSunk(
    x1: number,
    y1: number,
    x2: number,
    y2: number,
    r: number,
    moveCtr: BigNumber,
    round: BigNumber,
    player: string,
    shipIndex: number,
    contractAddress: string,
    web3: Web3
) {
    const revealHash = hashRevealSunk(x1, y1, x2, y2, r, moveCtr, round, shipIndex, contractAddress);
    return yield call(web3.eth.sign, revealHash, player);
}

function* attackApplyAndGetHashState(
    contract: Contract,
    x: number,
    y: number,
    sig: string,
    player: string,
    web3: Web3
) {
    const attack = contract.methods.attack(x, y, sig);
    // TODO: this has TransactionReceipt type
    // TODO: this could throw exception
    yield call(attack.send, { from: player, gas: 300000 });
    // get the state hash
    // TODO: this should be properly random
    const dummyRandom = 1;
    // TODO: this should have a 'hash' type
    const { _h } = yield call(contract.methods.getState(dummyRandom).call);
    // sign this hash
    const hashStateSig: string = yield call(web3.eth.sign, _h, player);
    return { hashState: _h, hashStateSig };
}
