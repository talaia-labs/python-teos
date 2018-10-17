import { call, put, takeLatest, takeEvery, select } from "redux-saga/effects";
import StateChannelContract from "./../../build/contracts/StateChannel.json";
import RpsContract from "./../../build/contracts/RockPaperScissors.json";

function* addStateChannel({ drizzle }) {
    const contract = new drizzle.web3.eth.Contract(StateChannelContract.abi);

    let account = yield select(state => state.app.account);
    let deployedContract = yield call(
        contract.deploy({ data: StateChannelContract.bytecode, arguments: [[account, account], 10] }).send,
        { from: account, gas: 2000000 }
    );
    console.log("State channel deployed at: ", deployedContract.options.address);

    const contractConfig = {
        contractName: "StateChannel",
        web3Contract: deployedContract
    };
    yield put({
        type: "ADD_CONTRACT",
        drizzle,
        contractConfig,
        events: [ ],
        web3: drizzle.web3
    });
    yield put({ type: "ADD_CONTRACT_ADDRESS", name: "StateChannel", address: deployedContract.options.address });
}

function* addRps({ drizzle }) {
    if (!drizzle.contracts.StateChannel) {
        console.log("State channel not initialised");
        return;
    }

    const contract = new drizzle.web3.eth.Contract(RpsContract.abi);

    let account = yield select(state => state.app.account);
    let deployedContract = yield call(
        contract.deploy({
            data: RpsContract.bytecode,
            arguments: [100, 25, 10, drizzle.contracts.StateChannel.address]
        }).send,
        { from: account, gas: 2000000 }
    );
    console.log("RPS deployed at: ", deployedContract.options.address);

    const contractConfig = {
        contractName: "RockPaperScissors",
        web3Contract: deployedContract
    };
    yield put({
        type: "ADD_CONTRACT",
        drizzle,
        contractConfig,
        events: [ ],
        web3: drizzle.web3
    });
    yield put({ type: "ADD_CONTRACT_ADDRESS", name: "RockPaperScissors", address: deployedContract.options.address });
}

function* addAppAccount() {
    let account = yield select(state => state.accounts[0]);
    yield put({ type: "STORE_APP_ACCOUNT", account });
}

function* addSignature({ drizzle, round, hstate }) {
    const stateChannel = yield select(state => state.app.contracts.StateChannel);

    if (!stateChannel) {
        console.log("No state channel deployed.");
        return;
    }
    let msg = drizzle.web3.utils.soliditySha3(
        { t: "bytes32", v: hstate },
        { t: "uint256", v: round },
        { t: "address", v: stateChannel.address }
    );
    const account = yield select(state => state.app.account);
    const signature = yield call(drizzle.web3.eth.sign, msg, account);
    yield put({ type: "STORE_SIGNATURE", round, hstate, signature });
}

function* appSaga() {
    yield takeLatest("ADD_STATE_CHANNEL", addStateChannel);
    yield takeLatest("ADD_RPS", addRps);
    yield takeEvery("ADD_SIGNATURE", addSignature);
    yield takeEvery("DRIZZLE_INITIALIZED", addAppAccount);
}

export default appSaga;
