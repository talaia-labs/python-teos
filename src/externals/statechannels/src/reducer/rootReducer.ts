import { combineReducers } from "redux";
import { ActionType, Action } from "./../action/rootAction";
import { IMove, IGame, ICounterpartyClient, PlayerStage, Reveal } from "./../entities/gameEntities";
import Web3 = require("web3");
const defaultWeb3 = new Web3("ws://localhost:8545");

// TODO: the "any" in this reducer is bad - start using the typesafe actions, with getType

const currentActionTypeReducer = (
    state: ActionType = ActionType.SETUP_DEPLOY_AWAIT,
    action: ReturnType<typeof Action.updateCurrentActionType>
) => {
    if (action.type === ActionType.UPDATE_CURRENT_ACTION_TYPE) {
        return action.payload.actionType;
    }
    // TODO: subscribers need to update as the first thing they atm
    // TODO: this because they potentially call dispatch in subscribe()
    else if (
        action.type === ActionType.SETUP_STORE_SHIPS ||
        action.type === ActionType.ATTACK_INPUT ||
        action.type === ActionType.REVEAL_INPUT || 
        action.type === ActionType.PROPOSE_STATE_UPDATE ||
        action.type === ActionType.PROPOSE_TRANSACTION_STATE_UPDATE
    ) {
        return action.type;
    } else return state;
};

const web3Reducer = (state: Web3 = defaultWeb3, action) => {
    return state;
};

// TODO: all these defaults in here are bad, remove as many as possble and populate them later

const opponentReducer = (
    state: ICounterpartyClient = {
        sendAttack: () => {},
        sendContract: () => {},
        sendReveal: () => {},
        sendSig: () => {},
        sendRequestLockSig: () => {},
        sendLockSig: () => {},
        sendOffChainBattleshipAddress: () => {},
        sendOffChainStateChannelAddress: () => {},
        sendRequestStateSig: () => {},
        sendStateSig: () => {},
        sendAction: () => {},
        sendDeployOffChain: () => {},
        sendStageUpdate: () => {},
        address: "0xffcf8fdee72ac11b5c542428b35eef5769c409f0",
        stage: PlayerStage.NONE,
        goesFirst: false
    },
    action
): ICounterpartyClient => {
    if (action.type === ActionType.COUNTERPARTY_STAGE_UPDATE) {
        return {
            ...state,
            stage: action.payload.stage
        };
    } else if (action.type === ActionType.OFF_CHAIN_BATTLESHIP_ADDRESS) {
        return {
            ...state,
            offChainBattleshipAddress: action.payload.address
        };
    } else if (action.type === ActionType.OFF_CHAIN_STATECHANNEL_ADDRESS) {
        return {
            ...state,
            offChainStateChannelAddress: action.payload.address
        };
    } else return state;
};

const moves: IMove[] = [];

// TODO: Initialise here instead of in the preloaded state?
const gameReducer = (
    state: IGame = {
        player: { address: "never should show", stage: PlayerStage.NONE, goesFirst: false },
        moves,
        round: 0
    },
    action
) => {
    if (action.type === ActionType.ATTACK_CREATE) {
        return { ...state, moves: [...state.moves, action.payload] };
    } else if (action.type === ActionType.STORE_ON_CHAIN_BATTLESHIP_CONTRACT) {
        return { ...state, onChainBattleshipContract: action.payload.battleshipContract };
    } else if (action.type === ActionType.STORE_OFF_CHAIN_BATTLESHIP_CONTRACT) {
        return { ...state, offChainBattleshipContract: action.payload.battleshipContract };
    } else if (action.type === ActionType.SETUP_STORE_SHIPS) {
        return { ...state, ships: [action.payload.message] };
    } else if (action.type === ActionType.STAGE_UPDATE) {
        return { ...state, player: { ...state.player, stage: action.payload.stage } };
    } else return state;
};

const shipSizesReducer = (state: number[] = [5, 4, 3, 3, 2], action) => {
    return state;
};

const reducer = combineReducers({
    currentActionType: currentActionTypeReducer,
    web3: web3Reducer,
    game: gameReducer,
    opponent: opponentReducer,
    shipSizes: shipSizesReducer
});

export default reducer;
