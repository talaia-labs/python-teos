import { createStore, applyMiddleware, compose } from "redux";
import createSagaMiddleware from "redux-saga";
import rootSaga from "./saga/rootSaga";
import reducer from "./reducer/rootReducer";
import { generateContractsInitialState } from "./../adjustedDrizzle/drizzle";

export function generateStore(options) {
    // Redux DevTools
    const composeEnhancers = window.__REDUX_DEVTOOLS_EXTENSION_COMPOSE__ || compose;

    // Preloaded state
    const preloadedState = {
        contracts: generateContractsInitialState(options)
    };

    // create the saga middleware
    const sagaMiddleware = createSagaMiddleware();
    const store = createStore(reducer, preloadedState, composeEnhancers(applyMiddleware(sagaMiddleware)));
    sagaMiddleware.run(rootSaga);

    return store;
}
