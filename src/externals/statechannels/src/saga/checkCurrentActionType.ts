import { ActionType } from "./../action/rootAction";
import { Selector } from "./../store";
import { select } from "redux-saga/effects";

// TODO: rename to checkCurrentGameState
export function* checkCurrentActionType(actionType: ActionType) {
    const currentActionType: ReturnType<typeof Selector.currentActionType> = yield select(Selector.currentActionType);
    if (currentActionType !== actionType) {
        //TODO: uh-oh we've failed our sanity check
        // exit, race condition?
        // TODO: throw or return boolean? seems like we need to exit, probably in the same way?
        throw new Error(`Supplied action type ${actionType} is not equal to stored action type ${currentActionType}.`);
    }
}
