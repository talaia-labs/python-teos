//  import { ActionsUnion, createAction } from "@martin_hotell/rex-tils";
import * as TypesafeActions from "typesafe-actions";
// TODO: remove circular dependency here
import { Contract } from "web3-eth-contract";
import { IShip, Reveal, IMove, PlayerStage, IStateChannelUpdate } from "./../entities/gameEntities";
import { IStateUpdate, IVerifyStateUpdate, IAcknowledgeStateUpdate, IProposeStateUpdate } from "../entities/stateUpdates";

export enum ActionType {
    // input from a user
    ATTACK_INPUT = "ATTACK_INPUT",
    ATTACK_INPUT_AWAIT = "ATTACK_INPUT_AWAIT",

    // broadcast attack to counterparty
    ATTACK_BROADCAST = "ATTACK_BROADCAST",
    ATTACK_BROADCAST_AWAIT = "ATTACK_BROADCAST_AWAIT",

    // attack accepted by counterparty
    ATTACK_ACCEPT = "ATTACK_ACCEPT",
    ATTACK_ACCEPT_AWAIT = "ATTACK_ACCEPT_AWAIT",

    // input from a user
    REVEAL_INPUT = "REVEAL_INPUT",
    REVEAL_INPUT_AWAIT = "REVEAL_INPUT_AWAIT",
    REVEAL_BROADCAST = "REVEAL_BROADCAST",
    REVEAL_BROADCAST_AWAIT = "REVEAL_BROADCAST_AWAIT",

    /// SETUP ////////////////////////////////////
    SETUP_DEPLOY = "SETUP_DEPLOY",
    SETUP_DEPLOY_AWAIT = "SETUP_DEPLOY_AWAIT",
    SETUP_DEPOSIT = "SETUP_DEPOSIT",
    SETUP_PLACE_BET = "SETUP_PLACE_BET",
    SETUP_STORE_SHIPS_AWAIT = "SETUP_AWAIT_SHIPS",
    SETUP_STORE_SHIPS = "SETUP_STORE_SHIPS",
    ADD_BATTLESHIP_ADDRESS = "ADD_BATTLESHIP_ADDRESS",

    /// STORE ////////////////////////////////////
    STORE_ON_CHAIN_BATTLESHIP_CONTRACT = "STORE_CONTRACT",
    STORE_OFF_CHAIN_BATTLESHIP_CONTRACT = "STORE_OFF_CHAIN_CONTRACT",
    ATTACK_CREATE = "ATTACK_CREATE_OR_UPDATE",
    UPDATE_CURRENT_ACTION_TYPE = "UPDATE_CURRENT_ACTION_TYPE",

    /// STATE CHANNEL ////////////////////////////
    LOCK = "LOCK",
    REQUEST_LOCK_SIG = "REQUEST_LOCK_SIG",
    LOCK_SIG = "LOCK_SIG",
    DEPLOY_OFF_CHAIN = "DEPLOY_OFF_CHAIN",
    OFF_CHAIN_BATTLESHIP_ADDRESS = "OFF_CHAIN_BATTLESHIP_ADDRESS",
    OFF_CHAIN_STATECHANNEL_ADDRESS = "OFF_CHAIN_STATECHANNEL_ADDRESS",
    REQUEST_STATE_SIG = "REQUEST_STATE_SIG",
    STATE_SIG = "STATE_SIG",

    /// COMUNICATION /////////////////////////////
    COUNTERPARTY_STAGE_UPDATE = "COUNTERPARTY_STAGE_UPDATE",
    STAGE_UPDATE = "STAGE_UPDATE",

    // OFF-CHAIN /////////////////////////////////
    BOTH_PLAYERS_READY_OFF_CHAIN = "BOTH_PLAYERS_READY_OFF_CHAIN",
    ACKNOWLEDGE_ATTACK_BROADCAST = "ACKNOWLEDGE_ATTACK_BROADCAST",
    ACKNOWLEDGE_REVEAL_BROADCAST = "ACKNOWLEDGE_REVEAL_BROADCAST",
    REVEAL_BROADCAST_OFF_CHAIN = "REVEAL_BROADCAST_OFF_CHAIN",

    VERIFY_STATE_UPDATE = "VERIFY_STATE_UPDATE",
    ACKNOWLEDGE_STATE_UPDATE = "ACKNOWLEDGE_STATE_UPDATE",
    PROPOSE_STATE_UPDATE = "PROPOSE_STATE_UPDATE",
    OPEN_SHIPS_INPUT_AWAIT = "OPEN_SHIPS_INPUT_AWAIT",
    FINISH_GAME_INPUT_AWAIT = "FINISH_GAME_INPUT_AWAIT",
    PLACE_BET_INPUT_AWAIT = "PLACE_BET_INPUT_AWAIT",
    STORE_SHIPS_INPUT_AWAIT = "STORE_SHIPS_INPUT_AWAIT",
    READY_TO_PLAY_INPUT_AWAIT = "READY_TO_PLAY_INPUT_AWAIT",
    PROPOSE_TRANSACTION_STATE_UPDATE = "PROPOSE_TRANSACTION_STATE_UPDATE",
    ACKNOWLEDGE_TRANSACTION_STATE_UPDATE = "ACKNOWLEDGE_TRANSACTION_STATE_UPDATE"
}

const createAction = <P>(type: string, payload: P) => {
    return {
        type,
        payload
    };
};

export const Action = {
    attackInput: (x: number, y: number) => createAction(ActionType.ATTACK_INPUT, { x, y }),
    attackBroadcast: (
        x: number,
        y: number,
        counterpartyAttackSig: string,
        onChainAttackSig: string,
        hashState: string,
        channelSig?: string
    ) =>
        createAction(ActionType.ATTACK_BROADCAST, {
            x,
            y,
            counterpartyAttackSig,
            onChainAttackSig,
            hashState,
            channelSig
        }),
    moveCreate: (payload: IMove) => createAction(ActionType.ATTACK_CREATE, payload),
    attackAccept: (hashStateSignature: string) => createAction(ActionType.ATTACK_ACCEPT, { hashStateSignature }),

    // TODO: IShipCoordinates ?
    // TODO: split this reveal into two different actions, reveal and reveal sunk
    revealInput: (reveal: Reveal, r?: number, x1?: number, y1?: number, x2?: number, y2?: number, shipIndex?: number) =>
        createAction(ActionType.REVEAL_INPUT, { reveal, x1, y1, x2, y2, shipIndex, r }),
    revealBroadcast: (reveal: Reveal) => createAction(ActionType.REVEAL_BROADCAST, { reveal }),

    /// SETUP /////////////////////////////////////////////
    setupDeploy: (timerChallenge: number) => createAction(ActionType.SETUP_DEPLOY, { timerChallenge }),
    setupAddBattleshipAddress: (battleshipContractAddress: string) =>
        createAction(ActionType.ADD_BATTLESHIP_ADDRESS, { battleshipContractAddress }),
    setupDeposit: (amount: number) => createAction(ActionType.SETUP_DEPOSIT, { amount }),
    setupPlaceBet: (amount: number) => createAction(ActionType.SETUP_PLACE_BET, { amount }),
    setupStoreShips: (ships: IShip[], board: string[][]) =>
        createAction(ActionType.SETUP_STORE_SHIPS, { ships, board }),

    /// STORE /////////////////////////////////////////////
    storeOnChainBattleshipContract: (battleshipContract: Contract) =>
        createAction(ActionType.STORE_ON_CHAIN_BATTLESHIP_CONTRACT, { battleshipContract }),
    storeOffChainBattleshipContract: (battleshipContract: Contract) =>
        createAction(ActionType.STORE_OFF_CHAIN_BATTLESHIP_CONTRACT, { battleshipContract }),
    updateCurrentActionType: (actionType: ActionType) =>
        createAction(ActionType.UPDATE_CURRENT_ACTION_TYPE, { actionType }),

    // STATE CHANNEL
    lock: (address: string) => createAction(ActionType.LOCK, { address }),
    requestLockSig: (address: string, channelCounter: number, round: number) =>
        createAction(ActionType.REQUEST_LOCK_SIG, { address, round, channelCounter }),
    lockSig: (address: string, sig: string) => createAction(ActionType.LOCK_SIG, { address, sig }),

    deployOffChain: () => createAction(ActionType.DEPLOY_OFF_CHAIN, {}),
    offChainBattleshipAddress: (address: string) => createAction(ActionType.OFF_CHAIN_BATTLESHIP_ADDRESS, { address }),
    offChainStateChannelAddress: (address: string) =>
        createAction(ActionType.OFF_CHAIN_STATECHANNEL_ADDRESS, { address }),
    requestStateSig: (stateChannelAddress: string) =>
        createAction(ActionType.REQUEST_STATE_SIG, { stateChannelAddress }),
    stateSig: (sig: string) => createAction(ActionType.STATE_SIG, { sig }),

    // COMMUNICATION
    counterpartyStageUpdate: (stage: PlayerStage) => createAction(ActionType.COUNTERPARTY_STAGE_UPDATE, { stage }),
    stageUpdate: (stage: PlayerStage) => createAction(ActionType.STAGE_UPDATE, { stage }),

    // OFF-CHAIN
    acknowledgeAttackBroadcast: (channelSig: string) =>
        createAction(ActionType.ACKNOWLEDGE_ATTACK_BROADCAST, { channelSig }),
    acknowledgeRevealBroadcast: (channelSig: string) =>
        createAction(ActionType.ACKNOWLEDGE_REVEAL_BROADCAST, { channelSig }),
    revealBroadcastOffChain: (payload: IStateChannelUpdate<{ reveal: Reveal; x: number; y: number }>) =>
        createAction(ActionType.REVEAL_BROADCAST, payload),

    verifyState: (payload: IVerifyStateUpdate) => createAction(ActionType.VERIFY_STATE_UPDATE, payload),
    acknowledgeStateUpdate: (payload: IAcknowledgeStateUpdate) =>
        createAction(ActionType.ACKNOWLEDGE_STATE_UPDATE, payload),
    proposeState: (payload: IProposeStateUpdate) => createAction(ActionType.PROPOSE_STATE_UPDATE, payload),

    proposeTransactionState: (payload: IProposeStateUpdate) => createAction(ActionType.PROPOSE_TRANSACTION_STATE_UPDATE, payload),
    acknowledgeTransactionState: (payload: IAcknowledgeStateUpdate) => createAction(ActionType.ACKNOWLEDGE_TRANSACTION_STATE_UPDATE, payload)
};

export type Action = TypesafeActions.ActionType<typeof Action>;
