import { all, fork } from "redux-saga/effects";
import { drizzleSagas } from "./../../adjustedDrizzle/drizzle";
import appSaga from "./appSaga";

export default function* root() {
    yield all([fork(appSaga), ...drizzleSagas.map(saga => fork(saga))]);
}
