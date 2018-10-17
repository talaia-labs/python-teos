import { createStore, applyMiddleware, compose } from "redux";
import createSagaMiddleware from "redux-saga";
import rootSaga from "./saga/rootSaga";
import reducer from "./reducer/rootReducer";
import { IStore, Reveal } from "./entities/gameEntities";
import { Action, ActionType } from "./action/rootAction";

export function generateStore(initialStore: IStore) {
    // Redux DevTools
    //    const composeEnhancers = (window && (window as any).__REDUX_DEVTOOLS_EXTENSION_COMPOSE__) || compose;
    const composeEnhancers = compose;

    // create the saga middleware
    const sagaMiddleware = createSagaMiddleware();
    const store = createStore<IStore, Action, {}, {}>(
        reducer,
        initialStore,
        composeEnhancers(applyMiddleware(sagaMiddleware))
    );
    sagaMiddleware.run(rootSaga);

    return store;
}

export class Selector {
    static readonly currentActionType = (store: IStore) => store.currentActionType;
    static readonly onChainBattleshipContract = (store: IStore) => {
        if (!store.game.onChainBattleshipContract) throw new Error("on chain battleshipContract not populated");
        return store.game.onChainBattleshipContract;
    };
    static readonly offChainBattleshipContract = (store: IStore) => {
        if (!store.game.offChainBattleshipContract) throw new Error("off chain battleshipContract not populated");
        return store.game.offChainBattleshipContract;
    };
    static readonly getBattleshipContractByAddress = (address: string) => (store: IStore) => {
        if (store.game.onChainBattleshipContract && store.game.onChainBattleshipContract.options.address == address)
            return store.game.onChainBattleshipContract;
        if (store.game.offChainBattleshipContract && store.game.offChainBattleshipContract.options.address == address)
            return store.game.offChainBattleshipContract;
        throw new Error("no battleship contract found for address " + address);
    };
    static readonly player = (store: IStore) => store.game.player;
    static readonly counterparty = (store: IStore) => store.opponent;
    static readonly web3 = (store: IStore) => store.web3;
    static readonly latestMove = (store: IStore) => store.game.moves[store.game.moves.length - 1];
    static readonly shipSizes = (store: IStore) => store.shipSizes;
    static readonly round = (store: IStore) => store.game.round;
    static readonly totalSinks = (store: IStore) => store.game.moves.filter(m => m.reveal === Reveal.Sink).length;
}

// TODO: organise this store - it's currently a mess
// TODO: doesnt the shipsizes give away which ship has been hit, by the index number - raise this with partrick
