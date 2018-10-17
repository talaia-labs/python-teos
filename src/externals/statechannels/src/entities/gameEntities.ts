import { Contract } from "web3-eth-contract";
import { Action, ActionType } from "./../action/rootAction";
import Web3 = require("web3");
import Web3Util from "web3-utils";

export interface IShip {
    id: string;
    size: number;
    x1: number;
    y1: number;
    x2: number;
    y2: number;
    r: number;
    player: string;
    round: number;
    gameAddress: string;
    hits: number;
    commitment: string;
}
export interface IStore {
    currentActionType: ActionType;
    web3: Web3;
    opponent: ICounterpartyClient;
    game: IGame;
    shipSizes: number[];
}

export interface IGame {
    onChainBattleshipContract?: Contract;
    offChainBattleshipContract?: Contract;
    player: IPlayer;
    moves: IMove[];
    // TODO: any
    ships?: IShip[];
    round: number;
}

export interface IPlayer {
    address: string;
    stage: PlayerStage;
    // isReadyToPlay: boolean;
    goesFirst: boolean;
}

export enum PlayerStage {
    NONE = 0,
    READY_TO_PLAY = 1,
    READY_TO_PLAY_OFFCHAIN = 2
}

export enum Phase {
    SETUP = 0,
    ATTACK = 1,
    REVEAL = 2,
    WIN = 3,
    FRAUD = 4
}

export enum Reveal {
    Miss = 1,
    Hit = 2,
    Sink = 3
}

export interface IMove {
    x: number;
    y: number;
    round: number;
    moveCtr: number;
    moveSig: string;
    hashState: string;
    channelSig: string;
    counterPartyChannelSig?: string;
    reveal?: Reveal;
}


export interface IStateChannelUpdate<T> {
    data: T;
    counterpartyDataSig: string;
    onChainDataSig: string;
    onChainStateHash: string;
    onChainStateHashSig: string
}


export interface ICounterpartyClient extends IPlayer {
    sendAttack(action: ReturnType<typeof Action.attackBroadcast>): void;
    sendReveal(action: ReturnType<typeof Action.revealBroadcast>): void;
    sendSig(action: ReturnType<typeof Action.attackAccept>);
    sendRequestLockSig(action: ReturnType<typeof Action.requestLockSig>): void;
    sendLockSig(action: ReturnType<typeof Action.lockSig>): void;
    sendDeployOffChain(action: ReturnType<typeof Action.deployOffChain>): void;
    sendOffChainBattleshipAddress(action: ReturnType<typeof Action.offChainBattleshipAddress>): void;
    sendOffChainStateChannelAddress(action: ReturnType<typeof Action.offChainStateChannelAddress>): void;
    sendRequestStateSig(action: ReturnType<typeof Action.requestStateSig>): void;
    sendStateSig(action: ReturnType<typeof Action.stateSig>): void;
    sendAction<T extends Action>(action: T);
    sendContract(action: ReturnType<typeof Action.setupAddBattleshipAddress>);
    sendStageUpdate(action: ReturnType<typeof Action.counterpartyStageUpdate>);
    offChainBattleshipAddress?: string;
    offChainStateChannelAddress?: string;
}
