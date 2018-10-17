import { expect } from "chai";
import "mocha";
import { checkCurrentActionType } from "./../checkCurrentActionType";
import { select } from "redux-saga/effects";
import { Selector } from "./../../store";
import { ActionType } from "./../../action/rootAction";

describe("Saga checkCurrentActionType", () => {
    const actionType1 = ActionType.ATTACK_ACCEPT_AWAIT;
    const actionType2 = ActionType.ATTACK_BROADCAST_AWAIT;

    it("should return if current action is correct", () => {
        const generator = checkCurrentActionType(actionType1);
        expect(generator.next().value).to.deep.equal(select(Selector.currentActionType));
        expect(generator.next(actionType1).done).to.be.true;
    });

    it("should throw error if action types differ", () => {
        const generator = checkCurrentActionType(actionType1);
        expect(generator.next().value).to.deep.equal(select(Selector.currentActionType));
        expect(() => generator.next(actionType2)).to.throw;
    });
});
