import * as chai from "chai";
import fs from "fs";
import util from "util";
import "mocha";
const chaiAsPromised = require("chai-as-promised");
chai.use(chaiAsPromised);
const expect = chai.expect;
import { expectSaga } from "redux-saga-test-plan";
import rootReducer from "./../../reducer/rootReducer";
import { BoardBuilder } from "../../utils/boardBuilder";

import { deployBattleship } from "./../setupSaga";
import { Action, ActionType } from "./../../action/rootAction";
import { IShip, IStore, IPlayer, Reveal, PlayerStage } from "./../../entities/gameEntities";
import { generateStore } from "./../../store";
import Web3 = require("web3");

import { TimeLogger } from "../../utils/TimeLogger";
import {
    RevealSlotProposeStateUpdate,
    RevealSunkProposeStateUpdate,
    AttackProposeStateUpdate,
    OpenShipsProposeStateUpdate,
    FinishGameProposeStateUpdate,
    PlaceBetProposeStateUpdate,
    StoreShipsProposeStateUpdate,
    ReadyToPlayProposeStateUpdate
} from "../../entities/stateUpdates";
import { committedShips } from "../../utils/shipTools";

const shipSizes = [5, 4, 3, 3, 2];

// TODO: why is the state necessary? why not simply
const state1: IStore = {
    currentActionType: ActionType.SETUP_DEPLOY_AWAIT,
    web3: new Web3("ws://localhost:8545"),
    game: {
        player: { address: "0x90f8bf6a479f320ead074411a4b0e7944ea8c9c1", stage: PlayerStage.NONE, goesFirst: true },
        moves: [],
        round: 0
    },
    opponent: {
        address: "0xffcf8fdee72ac11b5c542428b35eef5769c409f0",
        sendAttack: (action: ReturnType<typeof Action.attackBroadcast>) => {
            store2.dispatch(action);
        },
        sendReveal: (action: ReturnType<typeof Action.revealBroadcast>) => {
            store2.dispatch(action);
        },
        sendSig: () => {},

        sendRequestLockSig: (action: ReturnType<typeof Action.requestLockSig>) => {
            store2.dispatch(action);
        },
        sendLockSig: (action: ReturnType<typeof Action.lockSig>) => {
            store2.dispatch(action);
        },
        sendDeployOffChain: (action: ReturnType<typeof Action.deployOffChain>) => {
            store2.dispatch(action);
        },
        sendOffChainBattleshipAddress: (action: ReturnType<typeof Action.offChainBattleshipAddress>) => {
            store2.dispatch(action);
        },
        sendOffChainStateChannelAddress: (action: ReturnType<typeof Action.offChainStateChannelAddress>) => {
            store2.dispatch(action);
        },
        sendRequestStateSig: (action: ReturnType<typeof Action.requestStateSig>) => {
            store2.dispatch(action);
        },
        sendStateSig: (action: ReturnType<typeof Action.stateSig>) => {
            store2.dispatch(action);
        },
        sendContract: (action: ReturnType<typeof Action.setupAddBattleshipAddress>) => {
            store2.dispatch(action);
        },
        sendAction: action => {
            store2.dispatch(action);
        },
        sendStageUpdate: (action: ReturnType<typeof Action.counterpartyStageUpdate>) => {
            store2.dispatch(action);
        },
        stage: PlayerStage.NONE,
        goesFirst: false
    },
    shipSizes
};

let store1 = generateStore(state1);

const state2: IStore = {
    currentActionType: ActionType.SETUP_DEPLOY_AWAIT,
    web3: new Web3("ws://localhost:8545"),
    game: {
        player: { address: "0xffcf8fdee72ac11b5c542428b35eef5769c409f0", stage: PlayerStage.NONE, goesFirst: false },
        moves: [],
        round: 0
    },
    opponent: {
        address: "0x90f8bf6a479f320ead074411a4b0e7944ea8c9c1",
        sendAttack: (action: ReturnType<typeof Action.attackBroadcast>) => {
            store1.dispatch(action);
        },
        // TODO: rename these to broadcast
        sendReveal: (action: ReturnType<typeof Action.revealBroadcast>) => {
            store1.dispatch(action);
        },
        sendSig: () => {},
        sendRequestLockSig: (action: ReturnType<typeof Action.requestLockSig>) => {
            store1.dispatch(action);
        },
        sendLockSig: (action: ReturnType<typeof Action.lockSig>) => {
            store1.dispatch(action);
        },
        sendDeployOffChain: (action: ReturnType<typeof Action.deployOffChain>) => {
            store1.dispatch(action);
        },
        sendOffChainBattleshipAddress: (action: ReturnType<typeof Action.offChainBattleshipAddress>) => {
            store1.dispatch(action);
        },
        sendOffChainStateChannelAddress: (action: ReturnType<typeof Action.offChainStateChannelAddress>) => {
            store1.dispatch(action);
        },
        sendRequestStateSig: (action: ReturnType<typeof Action.requestStateSig>) => {
            store1.dispatch(action);
        },
        sendStateSig: (action: ReturnType<typeof Action.stateSig>) => {
            store1.dispatch(action);
        },
        sendAction: action => {
            store1.dispatch(action);
        },
        sendContract: (action: ReturnType<typeof Action.setupAddBattleshipAddress>) => {
            store1.dispatch(action);
        },
        sendStageUpdate: action => {
            store1.dispatch(action);
        },
        stage: PlayerStage.NONE,
        goesFirst: true
    },
    shipSizes
};

let store2 = generateStore(state2);

class TestBot {
    private mUnsubsribe;
    public complete: boolean = false;
    public FINAL_STATE = ActionType.OPEN_SHIPS_INPUT_AWAIT;
    private readonly player: IPlayer;
    // TODO: we should be reading this dynamically from the contract
    public readonly round = 0;

    constructor(public readonly store, id: number) {
        const initialState: IStore = store.getState();
        this.player = initialState.game.player;

        this.FINAL_STATE = ActionType.OPEN_SHIPS_INPUT_AWAIT;

        // initialState.game.player.goesFirst
        //     ? ActionType.REVEAL_BROADCAST_AWAIT
        //     : ActionType.ATTACK_ACCEPT_AWAIT;

        // TODO: this should be a class not a function
        let gameState: GameState;
        let attackIterator;
        let sinks = 0;
        let attacks = 0;
        let completedGames = 0;
        //let attackCount = 0;
        // we need to subscribe to the store to watch for certain events
        this.mUnsubsribe = store.subscribe(() => {
            // if (this.complete) {
            //     const log_file = fs.createWriteStream(__dirname + "/" + id + "-timings.log", { flags: "w" });
            //     TimeLogger.theLogger.timeSpanDataLogs.map(l => log_file.write(util.format(l.serialise()) + "\n"));
            // }

            const state: IStore = store.getState();
            switch (state.currentActionType) {
                case ActionType.SETUP_STORE_SHIPS_AWAIT: {
                    const contractAddress = state.game.onChainBattleshipContract!.options.address;
                    const boardAndShips = BoardBuilder.constructBasicShips(
                        contractAddress,
                        this.player.address,
                        this.round
                    );

                    // TODO: should the game state, and the associated decisions be in the store?
                    // TODO: they could be, but they should be in a seperate part - as really a user should
                    // TODO: get to decide whatever game state they want
                    gameState = new GameState(boardAndShips.board, boardAndShips.ships);
                    attackIterator = gameState.nextAttack();
                    store.dispatch(Action.setupStoreShips(boardAndShips.ships, boardAndShips.board));
                    break;
                }
                case ActionType.ATTACK_INPUT_AWAIT: {
                    // we're awaiting an attack, so lets make one
                    let attack = attackIterator.next().value;
                    console.log("attack", attack);
                    store.dispatch(Action.proposeTransactionState(new AttackProposeStateUpdate(attack.x, attack.y, 0)));

                    break;
                }
                case ActionType.REVEAL_INPUT_AWAIT: {
                    const latestMove = state.game.moves[state.game.moves.length - 1];
                    const revealResult = gameState.attackSquare(latestMove.x, latestMove.y);
                    console.log("reveal: ", revealToString(revealResult.reveal));

                    

                    if (revealResult.reveal === Reveal.Sink) {
                        sinks++;
                    }

                    // TODO: ship index
                    let action =
                        revealResult.reveal === Reveal.Sink
                            ? Action.proposeTransactionState(
                                  new RevealSunkProposeStateUpdate(
                                      latestMove.x,
                                      latestMove.y,
                                      revealResult.ship!.x1,
                                      revealResult.ship!.y1,
                                      revealResult.ship!.x2,
                                      revealResult.ship!.y2,
                                      revealResult.ship!.r,
                                      revealResult.shipIndex!,
                                      0
                                  )
                              )
                            : Action.proposeTransactionState(
                                  new RevealSlotProposeStateUpdate(
                                      //TODO: change this state round - really it should be managed in the store not here
                                      revealResult.reveal,
                                      latestMove.x,
                                      latestMove.y,
                                      0
                                  )
                              );

                    store.dispatch(action);
                    break;
                }
                case ActionType.OPEN_SHIPS_INPUT_AWAIT: {
                    // propse the open ships state transition
                    console.log("open ships");
                    const contractAddress = state.game.onChainBattleshipContract!.options.address;
                    state.game.offChainBattleshipContract.methods
                        .round()
                        .call()
                        .then(round => {
                            const openShips = BoardBuilder.constructBasicShips(
                                contractAddress,
                                this.player.address,
                                round
                            );
                            store.dispatch(
                                Action.proposeTransactionState(
                                    new OpenShipsProposeStateUpdate(
                                        openShips.ships.map(s => s.x1),
                                        openShips.ships.map(s => s.y1),
                                        openShips.ships.map(s => s.x2),
                                        openShips.ships.map(s => s.y2),
                                        openShips.ships.map(s => s.r),
                                        0
                                    )
                                )
                            );
                        });
                    break;
                }

                case ActionType.FINISH_GAME_INPUT_AWAIT: {
                    console.log("finish game");
                    store.dispatch(Action.proposeTransactionState(new FinishGameProposeStateUpdate(0)));
                    break;
                }

                case ActionType.PLACE_BET_INPUT_AWAIT: {
                    completedGames++;
                    console.log("place bet");
                    console.log("completed games", completedGames);
                    if (completedGames % 20 === 0) {
                        console.log("writing logs", completedGames);
                        // write the log files
                        // const log_file = fs.createWriteStream(
                        //     __dirname + "/" + id + "-" + completedGames + "-intro.log",
                        //     { flags: "w" }
                        // );
                        // TimeLogger.theLogger.timeSpanDataLogs.map(l =>
                        //     log_file.write(util.format(l.serialise()) + "\n")
                        // );
                        // write the log files
                        const log_file = fs.createWriteStream(
                            __dirname + "/" + id + "-" + completedGames + "-subs.log",
                            { flags: "w" }
                        );
                        TimeLogger.theLogger.timeSpanDataSubSubLogs.map(l =>
                            log_file.write(util.format(l.serialise()) + "\n")
                        );
                        if (completedGames === 100) {
                            console.log("games ended");
                            this.complete = true;
                            return;
                        }


                    }

                    store.dispatch(Action.proposeTransactionState(new PlaceBetProposeStateUpdate(10, 0)));
                    break;
                }
                case ActionType.STORE_SHIPS_INPUT_AWAIT: {
                    console.log("store ships");
                    gameState.resetAttacks();
                    attackIterator = gameState.nextAttack();
                    const contractAddress = state.game.onChainBattleshipContract!.options.address;

                    // get the counterparties signature - we're submmiting boards on their behalf
                    // get the round
                    state.game.offChainBattleshipContract.methods
                        .round()
                        .call()
                        .then(round => {
                            const boardAndShips = BoardBuilder.constructBasicShips(
                                contractAddress,
                                state.opponent.address,
                                round
                            );

                            const ships = committedShips(
                                state.game.onChainBattleshipContract.options.address,
                                boardAndShips.ships.map(s => s.size),
                                boardAndShips.ships.map(s => s.commitment),
                                round,
                                state.opponent.address
                            );

                            state.web3.eth.sign(ships.commitment, state.opponent.address).then(sig => {
                                store.dispatch(
                                    Action.proposeTransactionState(
                                        new StoreShipsProposeStateUpdate(
                                            boardAndShips.ships.map(s => s.size),
                                            boardAndShips.ships.map(a => a.commitment),
                                            sig,
                                            0
                                        )
                                    )
                                );
                            });
                        });
                    break;
                }

                case ActionType.READY_TO_PLAY_INPUT_AWAIT: {
                    console.log("ready to play");
                    store.dispatch(Action.proposeTransactionState(new ReadyToPlayProposeStateUpdate(0)));
                    break;
                }
                case this.FINAL_STATE:
                    console.log("ended");
                    this.complete = true;

                    break;

                default:
                    break;
            }
        });
    }

    unsubscribe() {
        if (this.mUnsubsribe) this.mUnsubsribe();
    }
}

function revealToString(reveal: Reveal) {
    switch (reveal) {
        case Reveal.Hit:
            return "hit";
        case Reveal.Miss:
            return "miss";
        case Reveal.Sink:
            return "sink";
        default:
            return "reveal state unknown " + reveal;
    }
}

abstract class RevealResult {
    constructor(readonly reveal: Reveal, readonly ship?: IShip, readonly shipIndex?: number) {}
}

class HitOrMissReveal extends RevealResult {
    constructor(readonly reveal: Reveal.Hit | Reveal.Miss) {
        super(reveal);
    }
}

class SinkReveal extends RevealResult {
    constructor(ship: IShip, shipIndex: number) {
        super(Reveal.Sink, ship, shipIndex);
    }
}

class GameState {
    constructor(private readonly board: string[][], private readonly ships: IShip[]) {}

    public attackSquare(x: number, y: number): RevealResult {
        /// lookup the position on the board. and find if it's a hit or miss
        const square = this.board[x][y];
        // TODO: magic strings here
        if (square == "0") return new HitOrMissReveal(Reveal.Miss);
        else {
            // decide if it's a normal hit or a sink

            // find the ship with this id
            const ship = this.ships.filter(ship => ship.id === square)[0];
            if (!ship) throw new Error(`Could not find ship at position ${x}:${y}.`);
            let index = this.ships.indexOf(ship);

            // increment the hits
            ship.hits++;

            // are the hits equal to the size of the ship?
            return ship.hits === ship.size ? new SinkReveal(ship, index) : new HitOrMissReveal(Reveal.Hit);
        }
    }

    private x = 0;
    private y = 0;
    public resetAttacks() {
        this.x = 0;
        this.y = 0;
        // TODO: dont do this, we should be creating a new gamestate for each round
        this.ships.forEach(s => (s.hits = 0));
    }

    public *nextAttack() {
        while (this.x < 10 && this.y < 10) {
            yield { x: this.x, y: this.y };
            this.y++;
            if (this.y % 5 == 0) {
                this.x++;
                this.y = 0;
            }
        }
    }
}

describe("Saga setup", () => {
    const actionSetupDeploy = Action.setupDeploy(10);

    // it("deployBattleship should end in await for ships", async () => {
    //     return;
    //     const { storeState } = await expectSaga(deployBattleship, actionSetupDeploy)
    //         .withReducer(rootReducer, state1)
    //         .run(10000);
    //     expect((storeState as IStore).game.battleshipContract).to.exist;
    //     expect((storeState as IStore).game.battleshipContract!.options.address).to.exist;
    //     expect((storeState as IStore).game.battleshipContract!.options.address).to.equal(
    //         store2.getState().game.battleshipContract!.options.address
    //     );

    //     console.log((storeState as IStore).currentActionType);
    //     console.log(store2.getState().currentActionType);
    //     // expect((storeState as IStore).currentActionType).to.equal(ActionType.SETUP_AWAIT_SHIPS);
    //     // expect(store2.getState().currentActionType).to.equal(ActionType.SETUP_AWAIT_SHIPS);

    //     //console.log(store1.getState().game.battleshipContract!.options.address)
    //     // expect(store2.getState().game.battleshipContract!.options.address)
    // });

    it("is my next test", async () => {
        let timeStamp = Date.now();

        const bot1 = new TestBot(store1, 1);
        const bot2 = new TestBot(store2, 2);

        store1.dispatch(actionSetupDeploy);

        while (!bot1.complete || !bot2.complete) {
            if (Date.now() - timeStamp > 300000000) throw new Error("exceeded timeout");
            await delay(1000);
        }

        bot1.unsubscribe();
        bot2.unsubscribe();
    }).timeout(300000000);

    const delay = time =>
        new Promise(resolve => {
            setTimeout(resolve, time);
        });

    // it("should run total gameengine ", async () => {
    //     testBot1.dispatch(actionSetupDeploy);
    //     const { storeState } = await expectSaga(deployBattleship, actionSetupDeploy)
    //         .withReducer(rootReducer, state1)
    //         .run(500);
    //     expect((storeState as IStore).game.battleshipContract).to.exist;
    //     expect((storeState as IStore).game.battleshipContract!.options.address).to.exist;
    // });
});
