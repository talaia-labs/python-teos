import { call, takeEvery, select, put } from "redux-saga/effects";
import { Action, ActionType } from "../action/rootAction";
import { Contract } from "web3-eth-contract";
import Web3 = require("web3");
const BattleShipWithoutBoardInChannel = require("./../../build/contracts/BattleShipWithoutBoardInChannel.json");
const StateChannelFactory = require("./../../build/contracts/StateChannelFactory.json");
const StateChannel = require("./../../build/contracts/StateChannel.json");
import { TimeLogger } from "./../utils/TimeLogger";
import { BigNumber } from "bignumber.js";
import Web3Util from "web3-utils";
import { Selector } from "../store";
import { PlayerStage } from "../entities/gameEntities";

export default function* stateChannel() {
    yield takeEvery(ActionType.LOCK, lock);
    yield takeEvery(ActionType.REQUEST_LOCK_SIG, requestLockSig);
    yield takeEvery(ActionType.LOCK_SIG, lockSig);
    yield takeEvery(ActionType.DEPLOY_OFF_CHAIN, deployOffChain);
    yield takeEvery(ActionType.REQUEST_STATE_SIG, requestStateSig);
    yield takeEvery(ActionType.STATE_SIG, stateSig);
}

// start the locking process
export function* lock(action: ReturnType<typeof Action.lock>) {
    // TODO: this function should be removed, it doesnt serve much use
    // get the battleship contract
    const battleshipContract: Contract = yield select(Selector.getBattleshipContractByAddress(action.payload.address));
    const player: ReturnType<typeof Selector.player> = yield select(Selector.player);
    
    const channelCounter = yield call(battleshipContract.methods.channelCounter().call);
    const round = yield call(battleshipContract.methods.round().call);

    // pass this to the counterparty for countersignature

    const counterparty: ReturnType<typeof Selector.counterparty> = yield select(Selector.counterparty);
    TimeLogger.theLogger.messageLog(player.address)("Request lock sig");
    yield call(counterparty.sendRequestLockSig, Action.requestLockSig(action.payload.address, channelCounter, round));
}

function* requestLockSig(action: ReturnType<typeof Action.requestLockSig>) {
    // received a sig on a lock
    // should a) verify - not for now, only saves gas costs
    // b) create a hash ourselves and sign
    
    const player: ReturnType<typeof Selector.player> = yield select(Selector.player);
    TimeLogger.theLogger.messageLog(player.address)("Received lock sig request");
    // get the battleship contract
    const web3: ReturnType<typeof Selector.web3> = yield select(Selector.web3);
    const sig: string = yield call(
        getLockMessageAndSign,
        web3,
        action.payload.address,
        player.address,
        action.payload.channelCounter,
        action.payload.round
    );

    // send the sig back
    const counterparty: ReturnType<typeof Selector.counterparty> = yield select(Selector.counterparty);
    TimeLogger.theLogger.messageLog(player.address)("Send lock sig");
    yield call(counterparty.sendLockSig, Action.lockSig(action.payload.address, sig));
}

function* lockSig(action: ReturnType<typeof Action.lockSig>) {
    // we've received a sig for the requested lock, so go ahead and complete the lock
    // get the relevant contract
    const battleshipContract: Contract = yield select(Selector.getBattleshipContractByAddress(action.payload.address));
    const web3: ReturnType<typeof Selector.web3> = yield select(Selector.web3);
    const player: ReturnType<typeof Selector.player> = yield select(Selector.player);
    TimeLogger.theLogger.messageLog(player.address)("Receive lock sig");
    const channelCounter = yield call(battleshipContract.methods.channelCounter().call);
    const round = yield call(battleshipContract.methods.round().call);
    const sig: string = yield call(
        getLockMessageAndSign,
        web3,
        action.payload.address,
        player.address,
        channelCounter,
        round
    );

    // lock the contract
    // now that we have both sigs call lock on the contract
    yield call(
        battleshipContract.methods.lock([
            player.goesFirst ? sig : action.payload.sig,
            player.goesFirst ? action.payload.sig : sig
        ]).send,
        {
            from: player.address,
            gas: 13000000
        }
    );
    
    TimeLogger.theLogger.messageLog(player.address)("Contract locked")

    // we've locked the contract, what do we want to do now?
    let onChainBattleshipContract: Contract = yield select(Selector.onChainBattleshipContract);
    if (onChainBattleshipContract && onChainBattleshipContract.options.address === action.payload.address) {
        // if we just locked the on chain contract, then we want to deploy an off chain contract and signal to the counterparty to deploy off chain
        const counterparty: ReturnType<typeof Selector.counterparty> = yield select(Selector.counterparty);
        TimeLogger.theLogger.messageLog("Signal deploy off chain");
        yield call(counterparty.sendDeployOffChain, Action.deployOffChain());
        // deploy ourselves
        yield call(deployOffChain);
    } else {
        // if we just locked an off chain contract, then we want to instantly unlock it with new state
        // get the state channel address
        const stateChannelAddress = yield call(battleshipContract.methods.stateChannel().call);
        const counterparty: ReturnType<typeof Selector.counterparty> = yield select(Selector.counterparty);
        TimeLogger.theLogger.messageLog("Request close sig")
        yield call(counterparty.sendRequestStateSig, Action.requestStateSig(stateChannelAddress));
    }
}

// request state sig
const dummyRandom = 137;

function* requestStateSig(action: ReturnType<typeof Action.requestStateSig>) {
    // a sig has been requested for current state, hashed with the address of the counterparty address

    // get the on chain contract
    const onChainBattleshipContract: Contract = yield select(Selector.onChainBattleshipContract);
    const player: ReturnType<typeof Selector.player> = yield select(Selector.player);
    TimeLogger.theLogger.messageLog(player.address)("Received close sig request")
    const stateHash = yield call(onChainBattleshipContract.methods.getState(dummyRandom).call, {
        from: player.address
    });
    const counterparty: ReturnType<typeof Selector.counterparty> = yield select(Selector.counterparty);
    const hashedWithAddress = hashWithAddress(stateHash._h, counterparty.offChainBattleshipAddress!);

    // TODO: hard coded to zero for this?
    const hashedWithClose = hashWithClose(hashedWithAddress, 0, action.payload.stateChannelAddress);
    const web3: ReturnType<typeof Selector.web3> = yield select(Selector.web3);

    // now sign it with the player address and send it back
    const stateSig: string = yield call(web3.eth.sign, hashedWithClose, player.address);
    TimeLogger.theLogger.messageLog(player.address)("Send close sig")
    yield call(counterparty.sendStateSig, Action.stateSig(stateSig));
}

function* stateSig(action: ReturnType<typeof Action.stateSig>) {
    // received a state sig, get the hash and sign it ourselves, then close the state channel and call unlock

    const onChainBattleshipContract: Contract = yield select(Selector.onChainBattleshipContract);
    const offChainBattleshipContract: Contract = yield select(Selector.offChainBattleshipContract);
    const player: ReturnType<typeof Selector.player> = yield select(Selector.player);
    TimeLogger.theLogger.messageLog(player.address)("Receive close sig")
    let stateChannelAddress = yield call(offChainBattleshipContract.methods.stateChannel().call);

    // get the state hash
    const stateHash = yield call(onChainBattleshipContract.methods.getState(dummyRandom).call, {
        from: player.address
    });

    // hash the state hash with the address
    const hashedWithAddress = hashWithAddress(stateHash._h, offChainBattleshipContract.options.address);

    // TODO: hard coded to zero for this?
    // hash it again with close

    const hashedWithClose = hashWithClose(hashedWithAddress, 0, stateChannelAddress);
    const web3: ReturnType<typeof Selector.web3> = yield select(Selector.web3);

    // now sign it with the player, and call close
    const stateSig: string = yield call(web3.eth.sign, hashedWithClose, player.address);
    const offChainStateChannelContract = new web3.eth.Contract(StateChannel.abi, stateChannelAddress);

    yield call(
        offChainStateChannelContract.methods.close(
            [
                ...chopUpSig(player.goesFirst ? stateSig : action.payload.sig),
                ...chopUpSig(player.goesFirst ? action.payload.sig : stateSig)
            ],
            0,
            hashedWithAddress
        ).send,
        {
            from: player.address,
            gas: 13000000
        }
    );
    
    TimeLogger.theLogger.messageLog(player.address)("Channel closed");
    // now unlock
    const state: IBattleShipState = yield call(onChainBattleshipContract.methods.getState(dummyRandom).call);
    yield call(
        offChainBattleshipContract.methods.unlock(
            state._bool,
            state._uints8,
            state._uints,
            state._winner,
            state._maps,
            state._shiphash,
            state._x1,
            state._y1,
            state._x2,
            state._y2,
            state._sunk
        ).send,
        { from: player.address, gas: 13000000 }
    );
    TimeLogger.theLogger.messageLog(player.address)("Off chain unlocked")
    // now we're ready to play off chain
    yield put(Action.stageUpdate(PlayerStage.READY_TO_PLAY_OFFCHAIN));

    const counterparty: ReturnType<typeof Selector.counterparty> = yield select(Selector.counterparty);
    TimeLogger.theLogger.messageLog(player.address)("Send ready to play off chain")
    yield call(counterparty.sendStageUpdate, Action.counterpartyStageUpdate(PlayerStage.READY_TO_PLAY_OFFCHAIN));

    // if both us and the counter pary are ready, then lets play off chain
    if (counterparty.stage === PlayerStage.READY_TO_PLAY_OFFCHAIN) {
        yield put({ type: ActionType.BOTH_PLAYERS_READY_OFF_CHAIN });
    }
}

interface IBattleShipState {
    _bool: boolean[];
    _uints8: number[];
    _uints: number[];
    _winner: string;
    _maps: number[];
    _shiphash: string[];
    _x1: number[];
    _y1: number[];
    _x2: number[];
    _y2: number[];
    _sunk: boolean[];
    _h: string;
}

export function hashWithAddress(hash: string, address: string) {
    return Web3Util.soliditySha3({ t: "bytes32", v: hash }, { t: "address", v: address });
}

function chopUpSig(sig) {
    const removedHexNotation = sig.slice(2);
    var r = `0x${removedHexNotation.slice(0, 64)}`;
    var s = `0x${removedHexNotation.slice(64, 128)}`;
    var v = `0x${removedHexNotation.slice(128, 130)}`;
    return [v, r, s];
}

function hashWithClose(hash: string, round: number, stateChannelAddress: string) {
    return Web3Util.soliditySha3(
        { t: "string", v: "close" },
        { t: "bytes32", v: hash },
        { t: "uint256", v: round },
        { t: "address", v: stateChannelAddress }
    );
}

function* getLockMessageAndSign(
    web3: Web3,
    battleshipContractAddress: string,
    playerAddress: string,
    channelCounter: number,
    round: number
) {
    let msg = Web3Util.soliditySha3(
        { t: "string", v: "lock" },
        { t: "uint256", v: channelCounter },
        { t: "uint256", v: round },
        { t: "address", v: battleshipContractAddress }
    );
    const sig: string = yield call(web3.eth.sign, msg, playerAddress);
    return sig;
}

// deploy an offchain contract,
// lock it up
// resolve a shared state in the statechannel
// then unlock it

function* deployOffChain() {
    // TODO: this should require a different web3, but one will do for now

    // get web3 from the store
    const web3: ReturnType<typeof Selector.web3> = yield select(Selector.web3);
    const player: ReturnType<typeof Selector.player> = yield select(Selector.player);
    TimeLogger.theLogger.messageLog(player.address)("Begin deploy off chain");
    const counterparty: ReturnType<typeof Selector.counterparty> = yield select(Selector.counterparty);
    const onChainBattleshipContract: ReturnType<typeof Selector.onChainBattleshipContract> = yield select(
        Selector.onChainBattleshipContract
    );

    // we need to deploy a state channel factory for use by the application
    const stateChannelFactory = new web3.eth.Contract(StateChannelFactory.abi);
    const deployedStateChannelFactory = yield call(
        stateChannelFactory.deploy({
            data: StateChannelFactory.bytecode,
            arguments: []
        }).send,
        { from: player.address, gas: 10000000 }
    );

    // we need the abi
    const contract = new web3.eth.Contract(BattleShipWithoutBoardInChannel.abi);
    const deployedContract: ReturnType<typeof Selector.offChainBattleshipContract> = yield call(
        contract.deploy({
            data: BattleShipWithoutBoardInChannel.bytecode,
            arguments: [
                player.goesFirst ? player.address : counterparty.address,
                player.goesFirst ? counterparty.address : player.address,
                // TODO: this should be timer_challenge + timer_dispute + time_toPlayInchannel
                10,
                deployedStateChannelFactory.options.address,
                onChainBattleshipContract.options.address
            ]
        }).send,
        { from: player.address, gas: 14000000 }
    );

    yield put(Action.storeOffChainBattleshipContract(deployedContract));

    // inform the other party of the off chain contract addess
    TimeLogger.theLogger.messageLog(player.address)("Send off chain address")
    yield call(
        counterparty.sendOffChainBattleshipAddress,
        Action.offChainBattleshipAddress(deployedContract.options.address)
    );

    // lock up the off chain contract
    yield call(lock, Action.lock(deployedContract.options.address));
}