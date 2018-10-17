import { all, fork } from "redux-saga/effects";
import setup from "./setupSaga";
import stateChannel from "./stateChannelSaga";
import transactionOffChain from "./offChainTransactionSaga";

export default function* root() {
    yield all([
        fork(setup),
        fork(stateChannel),
        fork(transactionOffChain)
    ]);
}
