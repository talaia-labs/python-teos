import * as chai from "chai";
import "mocha";
const chaiAsPromised = require("chai-as-promised");
chai.use(chaiAsPromised);
const expect = chai.expect;

import { attackInput } from "./../attackRevealSaga";
import { Action, ActionType } from "./../../action/rootAction";

import { Selector, IStore, ICounterpartyClient, generateStore } from "./../../store";
import { runSaga } from "redux-saga";
import Web3 = require("web3");
import Web3Util from "web3-utils";

const web3 = new Web3("ws://localhost:8545");
import BigNumber from "bignumber.js";

const mochaAsync = fn => {
    return async done => {
        try {
            await fn();
            done();
        } catch (err) {
            done(err);
        }
    };
};

let counterparty: ICounterpartyClient = {
    sendAttack: () => {},
    sendSig: () => {},
    sendReveal: () => {},
    sendContract: () => {},
    sendStageUpdate: () => {},
    address: "0xffcf8fdee72ac11b5c542428b35eef5769c409f0",
    isReadyToPlay: false,
    goesFirst: false
};

let initialState: IStore = {
    currentActionType: ActionType.ATTACK_INPUT_AWAIT,
    game: {
        onChainBattleshipContract: {
            options: { address: "0x90f8bf6a479f320ead074411a4b0e7944ea8c9c1" },
            methods: {
                move_ctr: () => {
                    return { call: async () => await new BigNumber(0) };
                },
                round: () => {
                    return { call: async () => await 1 };
                },
                attack: () => {
                    return { send: async () => await {} };
                },
                getState: () => {
                    return {
                        call: async () => {
                            const attackHash = Web3Util.soliditySha3({
                                t: "address",
                                v: "0x90f8bf6a479f320ead074411a4b0e7944ea8c9c1"
                            });
                            return { _h: attackHash };
                        }
                    };
                }
            }
        } as any,
        moves: [],
        player:{ address: "0x90f8bf6a479f320ead074411a4b0e7944ea8c9c1", isReadyToPlay: false, goesFirst: true},
        round: 0
    },
    opponent: counterparty,
    shipSizes: [ 5, 4, 3, 3, 2 ],
    web3: web3
};

describe("Saga attackReceiveInput", () => {
    const action = Action.attackInput(0, 0);

    it("should end in REVEAL_BROADCAST_AWAIT", async () => {
        const dispatched: Action[] = [];
        const result = await runSaga(
            {
                dispatch: (dispatchedAction: Action) => dispatched.push(dispatchedAction),
                getState: () => initialState
            },
            attackInput,
            action
        ).done;

        expect(dispatched.map(a => a.type)).to.deep.equal([ActionType.UPDATE_CURRENT_ACTION_TYPE]);
    });
});
