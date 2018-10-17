import { takeEvery, select, call, put, fork, spawn } from "redux-saga/effects";
import { Selector } from "./../store";
import { PlayerStage } from "./../entities/gameEntities";
import { ActionType, Action } from "./../action/rootAction";
import { TimeLogger } from "./../utils/TimeLogger"
const BattleShipWithoutBoard = require("./../../build/contracts/BattleShipWithoutBoard.json");
const StateChannelFactory = require("./../../build/contracts/StateChannelFactory.json");
import { checkCurrentActionType } from "./checkCurrentActionType";
const Web3Util = require("web3-utils");
import { committedShips } from "./../utils/shipTools";

const depositAmount = Web3Util.toWei("1", "ether");
const betAmount = Web3Util.toWei("0.01", "ether");

export default function* setup() {
    yield takeEvery(ActionType.SETUP_DEPLOY, deployBattleship);
    yield takeEvery(ActionType.ADD_BATTLESHIP_ADDRESS, addBattleshipAddress);
    yield takeEvery(ActionType.SETUP_STORE_SHIPS, storeShips);
    yield takeEvery(ActionType.COUNTERPARTY_STAGE_UPDATE, counterpartyStageUpdate);
}

// deploy a game
export function* deployBattleship(action: ReturnType<typeof Action.setupDeploy>) {
    // TODO: we should also set the goesFirst in here and in addBattleshipAddress - or it should be taken account of

    yield call(checkCurrentActionType, ActionType.SETUP_DEPLOY_AWAIT);
    
    // get web3 from the store
    const web3: ReturnType<typeof Selector.web3> = yield select(Selector.web3);
    const player: ReturnType<typeof Selector.player> = yield select(Selector.player);
    TimeLogger.theLogger.messageLog(player.address)("beginSetup");
    const counterparty: ReturnType<typeof Selector.counterparty> = yield select(Selector.counterparty);

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
    const contract = new web3.eth.Contract(BattleShipWithoutBoard.abi);
    const deployedContract: ReturnType<typeof Selector.onChainBattleshipContract> = yield call(
        contract.deploy({
            data: BattleShipWithoutBoard.bytecode,
            arguments: [
                player.address,
                counterparty.address,
                action.payload.timerChallenge,
                deployedStateChannelFactory.options.address
            ]
        }).send,
        { from: player.address, gas: 14000000 }
    );

    // store the deployed contract, and pass the information to the counterparty
    yield put(Action.storeOnChainBattleshipContract(deployedContract));
    // TODO: should be a fork
    TimeLogger.theLogger.messageLog(player.address)("sendContract")
    yield call(counterparty.sendContract, Action.setupAddBattleshipAddress(deployedContract.options.address));

    // complete the rest of the setup
    yield call(completeSetup);
}

export function* addBattleshipAddress(action: ReturnType<typeof Action.setupAddBattleshipAddress>) {
    yield call(checkCurrentActionType, ActionType.SETUP_DEPLOY_AWAIT);
    // create a battleship contract from the given address and store it
    const web3: ReturnType<typeof Selector.web3> = yield select(Selector.web3);

    // TODO: check the existance of the contract at this address?
    const contract = new web3.eth.Contract(BattleShipWithoutBoard.abi, action.payload.battleshipContractAddress);
    yield put(Action.storeOnChainBattleshipContract(contract));

    // move on to the deposit phase
    yield call(completeSetup);
}

export function* completeSetup() {
    // TODO: phase check

    // deposit
    yield call(deposit, Action.setupDeposit(depositAmount));
    // place bet
    yield call(placeBet, Action.setupPlaceBet(betAmount));
    // now wait for ship input
    const player : ReturnType<typeof Selector.player> = yield select(Selector.player)
    TimeLogger.theLogger.messageLog(player.address)("requestShips")
    yield put(Action.updateCurrentActionType(ActionType.SETUP_STORE_SHIPS_AWAIT));

}

export function* deposit(action: ReturnType<typeof Action.setupDeposit>) {
    // TODO: check that all phases are being correctly set and checked
    // TODO: phase check

    const player: ReturnType<typeof Selector.player> = yield select(Selector.player);
    const battleshipContract: ReturnType<typeof Selector.onChainBattleshipContract> = yield select(
        Selector.onChainBattleshipContract
    );

    yield call(battleshipContract.methods.deposit().send, { from: player.address, value: action.payload.amount });
    TimeLogger.theLogger.messageLog(player.address)("deposit");
}

export function* placeBet(action: ReturnType<typeof Action.setupPlaceBet>) {
    const player: ReturnType<typeof Selector.player> = yield select(Selector.player);
    const battleshipContract: ReturnType<typeof Selector.onChainBattleshipContract> = yield select(
        Selector.onChainBattleshipContract
    );

    yield call(battleshipContract.methods.placeBet(action.payload.amount).send, { from: player.address });
    TimeLogger.theLogger.messageLog(player.address)("placeBet");
}

export function* storeShips(action: ReturnType<typeof Action.setupStoreShips>) {
    // TODO: check game phase
    
    const battleshipContract: ReturnType<typeof Selector.onChainBattleshipContract> = yield select(
        Selector.onChainBattleshipContract
    );
    const shipSizes: ReturnType<typeof Selector.shipSizes> = yield select(Selector.shipSizes);
    const round: ReturnType<typeof Selector.round> = yield select(Selector.round);
    const player: ReturnType<typeof Selector.player> = yield select(Selector.player);
    const counterparty: ReturnType<typeof Selector.counterparty> = yield select(Selector.counterparty);
    TimeLogger.theLogger.messageLog(player.address)("beginStoreShips")
    //create a commitment and update attack
    const ships = committedShips(
        battleshipContract.options.address,
        shipSizes,
        action.payload.ships.map(s => s.commitment),
        round,
        player.address
    );
    // TODO: ths section should be the other way round - i sign my own boards then pass them to the counterparty for submission
    // sign the commitment
    const web3: ReturnType<typeof Selector.web3> = yield select(Selector.web3);
    //  console.log(ships.commitment);
    const commitmentSig = yield call(web3.eth.sign, ships.commitment, player.address);

    yield call(
        battleshipContract.methods.storeShips(shipSizes, action.payload.ships.map(s => s.commitment), commitmentSig)
            .send,
        { from: counterparty.address, gas: 2000000 }
    );

    // signal that the player is ready
    yield call(readyToPlay);
}

// TODO: no error handling in any of the sagas
// TODO: no handling of failure midway through

export function* readyToPlay() {
    const battleshipContract: ReturnType<typeof Selector.onChainBattleshipContract> = yield select(
        Selector.onChainBattleshipContract
    );
    const player: ReturnType<typeof Selector.player> = yield select(Selector.player);
    yield call(battleshipContract.methods.readyToPlay().send, { from: player.address });
    // success, record that we were able to
    yield put(Action.stageUpdate(PlayerStage.READY_TO_PLAY));

    // signal to the counterparty that we are ready to play
    const counterparty: ReturnType<typeof Selector.counterparty> = yield select(Selector.counterparty);
    TimeLogger.theLogger.messageLog(player.address)("Send ready to play")
    yield call(counterparty.sendStageUpdate, Action.counterpartyStageUpdate(PlayerStage.READY_TO_PLAY));

    // also check to see if the counteryparty is already ready to play, if so then we're ready to start
    if (counterparty.stage === PlayerStage.READY_TO_PLAY) {
        yield call(bothPlayersReadyToPlay, player.goesFirst);
    }
    // else, do nothing, when the counterparty is ready we'll try to set state again
}

export function* counterpartyStageUpdate(action: ReturnType<typeof Action.counterpartyStageUpdate>) {
    const player: ReturnType<typeof Selector.player> = yield select(Selector.player);
    switch (action.payload.stage) {
        case PlayerStage.READY_TO_PLAY: {
            if (player.stage === PlayerStage.READY_TO_PLAY) {
                // both players are ready
                TimeLogger.theLogger.messageLog(player.address)("Receive ready to play")
                yield call(bothPlayersReadyToPlay, player.goesFirst);
            }
            break;
        }
        case PlayerStage.READY_TO_PLAY_OFFCHAIN: {
            if (player.stage === PlayerStage.READY_TO_PLAY_OFFCHAIN) {
                // both players ready offline
                TimeLogger.theLogger.messageLog(player.address)("Receive ready to play off chain")
                yield put({ type: ActionType.BOTH_PLAYERS_READY_OFF_CHAIN });
            }
            break;
        }
        default:
            throw new Error("Unknown stage: " + action.payload.stage);
    }
}

export function* bothPlayersReadyToPlay(playerGoesFirst: boolean) {
    if (playerGoesFirst) {
        // lock up the contract
        const battleshipContract: ReturnType<typeof Selector.onChainBattleshipContract> = yield select(
            Selector.onChainBattleshipContract
        );
        yield put(Action.lock(battleshipContract.options.address));
        // // transition to await attack
        // yield put(Action.updateCurrentActionType(ActionType.ATTACK_INPUT_AWAIT));
    } else {
        // // transition to await attack accept
        // yield put(Action.updateCurrentActionType(ActionType.ATTACK_BROADCAST_AWAIT));
    }
}
