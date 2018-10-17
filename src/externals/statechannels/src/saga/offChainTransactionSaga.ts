import { call, takeEvery, select, put } from "redux-saga/effects";
import { Action, ActionType } from "../action/rootAction";
import { Contract } from "web3-eth-contract";
import Tx from "ethereumjs-tx";
import Web3 from "web3";
import Web3Util from "web3-utils";
import ethereumjs from "ethereumjs-util";
import { Selector } from "../store";
import { hashWithAddress } from "./stateChannelSaga";
import { TimeLogger } from "./../utils/TimeLogger";
import { IVerifyStateUpdate, IStateUpdate } from "./../entities/stateUpdates";
export const dummyRandom = 137;

export default function* transactionOffChain() {
    yield takeEvery(ActionType.PROPOSE_TRANSACTION_STATE_UPDATE, proposeTransactionStateUpdate);
    yield takeEvery(ActionType.VERIFY_STATE_UPDATE, verifyTransactionStateUpdate);
    yield takeEvery(ActionType.ACKNOWLEDGE_TRANSACTION_STATE_UPDATE, acknowledgeTransactionStateUpdate);
    yield takeEvery(ActionType.BOTH_PLAYERS_READY_OFF_CHAIN, bothPlayersReadyToPlayOffChain);
}

//TODO: obiously remove - we should have a wallet for handling this
function getPrivKey(address: string) {
    if (address === "0x90f8bf6a479f320ead074411a4b0e7944ea8c9c1") {
        return "0x4f3edf983ac636a65a842ce7c78d9aa706d3b113bce9c46f30d7d21715b23b1d";
    } else if (address === "0xffcf8fdee72ac11b5c542428b35eef5769c409f0") {
        return "0x6cbed15c793ce57650b9877cf6fa156fbef513c4e6134f022a85b1ffdd59b2a1";
    } else throw new Error("Unrecognised address: " + address);
}

export function* bothPlayersReadyToPlayOffChain() {
    const player: ReturnType<typeof Selector.player> = yield select(Selector.player);
    if (player.goesFirst) {
        // transition to await attack
        TimeLogger.theLogger.messageLog(player.address)("Await attack input");
        yield put(Action.updateCurrentActionType(ActionType.ATTACK_INPUT_AWAIT));
    } else {
        // TODO: put in awaits later transition to await attack accept
        //yield put(Action.updateCurrentActionType(ActionType.ATTACK_BROADCAST_AWAIT));
    }
}

const verifySig = (transaction, v: string, r: string, s: string) => {
    transaction.v = v;
    transaction.r = r;
    transaction.s = s;
    return transaction.verifySignature();
};

const createSignedTx = async (web3: Web3, from: string, to: string, data: string, signer: string) => {
    const privateKey = new Buffer(getPrivKey(signer).split("x")[1], "hex");
    const nonce = await web3.eth.getTransactionCount(from);
    const chainId = await web3.eth.net.getId();
    const gasPrice = await web3.eth.getGasPrice();

    const rawTx = {
        nonce: "0x" + nonce.toString(16),
        gasPrice: "0x" + gasPrice.toString(16),
        gasLimit: "0x2dc6c0",
        to,
        //chainId,
        data
        //value: "0x00"
    };

    const tx = new Tx(rawTx);
    tx.sign(privateKey);
    return {
        v: "0x" + tx.v.toString("hex"),
        r: "0x" + tx.r.toString("hex"),
        s: "0x" + tx.s.toString("hex"),
        tx: tx,
        rawTransaction: "0x" + tx.serialize().toString("hex"),
        messageHash: Web3Util.sha3("0x" + tx.serialize().toString("hex"))
    };
};

export function* proposeTransactionStateUpdate(action: ReturnType<typeof Action.proposeState>) {
    // user reveals a value
    const start = Date.now();
    const offChainBattleshipContract: Contract = yield select(Selector.offChainBattleshipContract);
    const onChainBattleshipContract: Contract = yield select(Selector.onChainBattleshipContract);
    const player: ReturnType<typeof Selector.player> = yield select(Selector.player);
    const counterparty: ReturnType<typeof Selector.counterparty> = yield select(Selector.counterparty);
    const web3: ReturnType<typeof Selector.web3> = yield select(Selector.web3);
    
    const storeSelects = Date.now();
    TimeLogger.theLogger.dataSpanSubSubLog( player.address,
        action.payload.name,
        "propose",
        "store-selects",
        action.payload.serialiseData(),
        storeSelects - start)

    const channelAddress = yield call(onChainBattleshipContract.methods.stateChannel().call);
    const moveCtr = yield call(offChainBattleshipContract.methods.move_ctr().call);
    const round = yield call(offChainBattleshipContract.methods.round().call);
    const contractSelects = Date.now();
    TimeLogger.theLogger.dataSpanSubSubLog( player.address,
        action.payload.name,
        "propose",
        "contract-selects",
        action.payload.serialiseData(),
        contractSelects - storeSelects)
    

    // create, sign and execute a transaction
    const hashData = action.payload.hashData(moveCtr, round, offChainBattleshipContract.options.address);
    const sig = yield call(web3.eth.sign, hashData, player.address);
    const func = action.payload.getFunction(offChainBattleshipContract, sig);
    const signedTransaction = yield call(
        createSignedTx,
        web3,
        player.address,
        offChainBattleshipContract.options.address,
        func.encodeABI(),
        player.address
    );
    const createTx = Date.now();
    TimeLogger.theLogger.dataSpanSubSubLog( player.address,
        action.payload.name,
        "propose",
        "create-tx",
        action.payload.serialiseData(),
        createTx - contractSelects)
    yield call(web3.eth.sendSignedTransaction, signedTransaction.rawTransaction);
    const sendTx =Date.now();
    TimeLogger.theLogger.dataSpanSubSubLog( player.address,
        action.payload.name,
        "propose",
        "send-signed-tx",
        action.payload.serialiseData(),
        sendTx - createTx)

    // success, create a sig for the opponent
    const counterpartyData = action.payload.hashData(moveCtr, round, counterparty.offChainBattleshipAddress!);
    const counterpartySig = yield call(web3.eth.sign, counterpartyData, player.address);    
    const counterpartyFunc = action.payload.getFunction(offChainBattleshipContract, counterpartySig);
    const counterpartySignedTransaction = yield call(
        createSignedTx,
        web3,
        player.address,
        counterparty.offChainBattleshipAddress!,
        counterpartyFunc.encodeABI(),
        player.address
    );
    const signCounterpartyTx = Date.now();
    TimeLogger.theLogger.dataSpanSubSubLog( player.address,
        action.payload.name,
        "propose",
        "sign-counterparty-tx",
        action.payload.serialiseData(),
        signCounterpartyTx - sendTx)

    // create a sig against the onchain contract, to be used by the counterparty in a fraud proof
    const onChainData = action.payload.hashData(moveCtr, round, onChainBattleshipContract.options.address);
    const onChainSig = yield call(web3.eth.sign, onChainData, player.address);
    const createOnChainDataAndSig = Date.now();
    TimeLogger.theLogger.dataSpanSubSubLog( player.address,
        action.payload.name,
        "propose",
        "create-onchain-data-and-sig",
        action.payload.serialiseData(),
        createOnChainDataAndSig - signCounterpartyTx)

    // create a state update and sign it
    const { _h } = yield call(offChainBattleshipContract.methods.getState(dummyRandom).call);
    const getState = Date.now();
    TimeLogger.theLogger.dataSpanSubSubLog( player.address,
        action.payload.name,
        "propose",
        "get-state",
        action.payload.serialiseData(),
        getState - createOnChainDataAndSig)

    const hashedWithAddress = hashWithAddress(_h, onChainBattleshipContract.options.address);
    // TODO: this state round hasnt been populated!
    const channelHash = hashForSetState(hashedWithAddress, action.payload.stateRound, channelAddress);
    const channelSig = yield call(web3.eth.sign, channelHash, player.address);
    const stateUpdate = Date.now();
    TimeLogger.theLogger.dataSpanSubSubLog( player.address,
        action.payload.name,
        "propose",
        "state-update",
        action.payload.serialiseData(),
        stateUpdate - getState)

    // TODO: this needs to contain both channel sigs
    let storeUpdate = action.payload.storeUpdateAction(channelHash, channelSig, moveCtr, round, onChainSig);
    if (storeUpdate) yield put(storeUpdate);
    TimeLogger.theLogger.dataSpanLog(
        player.address,
        action.payload.name,
        "propose",
        action.payload.serialiseData(),
        Date.now() - start
    );
    yield call(
        counterparty.sendAction,
        Action.verifyState(
            action.payload.createVerifyStateUpdate(
                counterpartySignedTransaction,
                onChainSig,
                counterpartySig,
                channelSig
            )
        )
    );
}

export function* verifyTransactionStateUpdate(action: ReturnType<typeof Action.verifyState>) {
    // verify a sig of the data hashed with the onchain address
    const start = Date.now();
    const player: ReturnType<typeof Selector.player> = yield select(Selector.player);
    const offChainBattleshipContract: Contract = yield select(Selector.offChainBattleshipContract);
    const onChainBattleshipContract: Contract = yield select(Selector.onChainBattleshipContract);
    const counterparty: ReturnType<typeof Selector.counterparty> = yield select(Selector.counterparty);
    const web3: ReturnType<typeof Selector.web3> = yield select(Selector.web3);

    const storeSelects = Date.now();
    TimeLogger.theLogger.dataSpanSubSubLog( player.address,
        action.payload.name,
        "verify",
        "store-selects",
        action.payload.serialiseData(),
        storeSelects - start)

    const onChainStateChannel = yield call(onChainBattleshipContract.methods.stateChannel().call);
    const moveCtr = yield call(offChainBattleshipContract.methods.move_ctr().call);
    const round = yield call(offChainBattleshipContract.methods.round().call);
    
    const contractSelects = Date.now();
    TimeLogger.theLogger.dataSpanSubSubLog( player.address,
        action.payload.name,
        "verify",
        "contract-selects",
        action.payload.serialiseData(),
        contractSelects - storeSelects)

    //verify the onchain move data sig
    const dataHash = action.payload.hashData(moveCtr, round, onChainBattleshipContract.options.address);
    const dataSigner = recover(dataHash, action.payload.onChainDataSig);
    if (dataSigner !== counterparty.address) {
        throw new Error(`Data hash state signed by: ${dataSigner}, not by counteryparty: ${counterparty.address}`);
    }

    const dataHashTime = Date.now();
    TimeLogger.theLogger.dataSpanSubSubLog( player.address,
        action.payload.name,
        "verify",
        "verify-on-chain-data",
        action.payload.serialiseData(),
        dataHashTime - contractSelects)

    // verify that the offchain data sig matches data that is supplied in the transaction.
    const offChainDataHash = action.payload.hashData(moveCtr, round, offChainBattleshipContract.options.address);
    const offChainSigner = recover(offChainDataHash, action.payload.offChainDataSig);
    if (offChainSigner !== counterparty.address) {
        throw new Error(`Off chain data hash signed by: ${dataSigner}, not by counteryparty: ${counterparty.address}`);
    }

    const verifyOffchainData = Date.now();
    TimeLogger.theLogger.dataSpanSubSubLog( player.address,
        action.payload.name,
        "verify",
        "verify-off-chain-data",
        action.payload.serialiseData(),
        verifyOffchainData - dataHashTime)

    const offChainFunc = action.payload.getFunction(offChainBattleshipContract, action.payload.offChainDataSig);
    const signedTransaction = yield call(
        createSignedTx,
        web3,
        counterparty.address,
        offChainBattleshipContract.options.address,
        offChainFunc.encodeABI(),
        player.address
    );

    const createTx = Date.now();
    TimeLogger.theLogger.dataSpanSubSubLog( player.address,
        action.payload.name,
        "verify",
        "create-tx",
        action.payload.serialiseData(),
        createTx - verifyOffchainData)

    // check the transaction was signed by the counterparty
    if (
        !verifySig(
            signedTransaction.tx,
            action.payload.offChainTransaction.v,
            action.payload.offChainTransaction.r,
            action.payload.offChainTransaction.s
        )
    ) {
        throw new Error(`Transaction not signed by ${counterparty.address}`);
    }

    const verifyTxSig = Date.now();
    TimeLogger.theLogger.dataSpanSubSubLog( player.address,
        action.payload.name,
        "verify",
        "verify-tx-sig",
        action.payload.serialiseData(),
        verifyTxSig - createTx)

    yield call(web3.eth.sendSignedTransaction, action.payload.offChainTransaction.rawTransaction);

    const sendTransaction = Date.now();
    TimeLogger.theLogger.dataSpanSubSubLog( player.address,
        action.payload.name,
        "verify",
        "send-signed-tx",
        action.payload.serialiseData(),
        sendTransaction - verifyTxSig)

    // get the state
    const state = yield call(offChainBattleshipContract.methods.getState(dummyRandom).call);

    const getState = Date.now();
    TimeLogger.theLogger.dataSpanSubSubLog( player.address,
        action.payload.name,
        "verify",
        "get-state",
        action.payload.serialiseData(),
        getState - sendTransaction)

    // hash it with the address of the on chain contract
    const hashedWithOnChainAddress = hashWithAddress(state._h, onChainBattleshipContract.options.address);
    // verify the channel sig
    const channelHash = hashForSetState(hashedWithOnChainAddress, action.payload.stateRound, onChainStateChannel);
    const channelHashSigner = recover(channelHash, action.payload.stateUpdateSig);
    if (channelHashSigner !== counterparty.address) {
        throw new Error(
            `Channel hash state signed by: ${channelHashSigner}, not by counteryparty: ${counterparty.address}`
        );
    }

    const verifyState = Date.now();
    TimeLogger.theLogger.dataSpanSubSubLog( player.address,
        action.payload.name,
        "verify",
        "verify-state",
        action.payload.serialiseData(),
        verifyState - getState)


    // create a signature over this state as well
    const channelSig: string = yield call(web3.eth.sign, channelHash, player.address);

    const signState = Date.now();
    TimeLogger.theLogger.dataSpanSubSubLog( player.address,
        action.payload.name,
        "verify",
        "sign-state",
        action.payload.serialiseData(),
        signState - verifyState)

    // TODO: this needs to contain both channel sigs
    let storeUpdate = action.payload.storeUpdateAction(channelHash, channelSig, moveCtr, round, dataHash);
    if (storeUpdate) yield put(storeUpdate);

    TimeLogger.theLogger.dataSpanLog(
        player.address,
        action.payload.name,
        "verify",
        action.payload.serialiseData(),
        Date.now() - start
    );

    yield call(actionAfterVerify, action.payload, offChainBattleshipContract, player.address);
    yield call(
        counterparty.sendAction,
        Action.acknowledgeTransactionState(action.payload.createAcknowledgeStateUpdate(channelSig))
    );
}

export function* acknowledgeTransactionStateUpdate(action: ReturnType<typeof Action.acknowledgeStateUpdate>) {
    const start = Date.now();
    const player: ReturnType<typeof Selector.player> = yield select(Selector.player);
    const offChainBattleshipContract: ReturnType<typeof Selector.offChainBattleshipContract> = yield select(
        Selector.offChainBattleshipContract
    );
    const onChainBattleshipContract: ReturnType<typeof Selector.onChainBattleshipContract> = yield select(
        Selector.onChainBattleshipContract
    );
    const counterparty: ReturnType<typeof Selector.counterparty> = yield select(Selector.counterparty);

    const storeSelects = Date.now();
    TimeLogger.theLogger.dataSpanSubSubLog( player.address,
        action.payload.name,
        "acknowledge",
        "store-selects",
        action.payload.serialiseData(),
        storeSelects - start)

    const channelAddress: string = yield call(onChainBattleshipContract.methods.stateChannel().call);
    const moveCtr = yield call(offChainBattleshipContract.methods.move_ctr().call);
    const round = yield call(offChainBattleshipContract.methods.round().call);
    const contractSelects = Date.now();
    TimeLogger.theLogger.dataSpanSubSubLog( player.address,
        action.payload.name,
        "acknowledge",
        "contract-selects",
        action.payload.serialiseData(),
        contractSelects - storeSelects)

    const state = yield call(offChainBattleshipContract.methods.getState(dummyRandom).call);

    const getState = Date.now();
    TimeLogger.theLogger.dataSpanSubSubLog( player.address,
        action.payload.name,
        "acknowledge",
        "get-state",
        action.payload.serialiseData(),
        getState - contractSelects)
    

    // hash it with the address of the on chain contract
    const hashedWithOnChainAddress = hashWithAddress(state._h, onChainBattleshipContract.options.address);
    // verify the channel sig
    const channelHash = hashForSetState(hashedWithOnChainAddress, action.payload.stateRound, channelAddress);
    // verify that the counterparty did actually sign this move
    const signer = recover(channelHash, action.payload.stateUpdateSig);
    if (signer !== counterparty.address) {
        throw new Error(`Channel hash state signed by: ${signer}, not by counteryparty: ${counterparty.address}`);
    }

    const verifySig = Date.now();
    TimeLogger.theLogger.dataSpanSubSubLog( player.address,
        action.payload.name,
        "acknowledge",
        "verify-sig",
        action.payload.serialiseData(),
        verifySig - getState)

    // TODO: these args dont make sense
    const storeAction = action.payload.storeUpdateAction(channelHash, action.payload.stateUpdateSig, moveCtr, round);
    if (storeAction) yield put(storeAction);

    TimeLogger.theLogger.dataSpanLog(
        player.address,
        action.payload.name,
        "acknowledge",
        action.payload.serialiseData(),
        Date.now() - start
    );
    yield call(actionAfterAcknowledge, action.payload, offChainBattleshipContract);
}

export function* actionAfterAcknowledge(state: IStateUpdate, contract: Contract) {
    if(state.name === "attack") {
        // set the counterparty to await reveal
        const counterparty: ReturnType<typeof Selector.counterparty> = yield select(Selector.counterparty)
        yield call(counterparty.sendAction, Action.updateCurrentActionType(ActionType.REVEAL_INPUT_AWAIT));
    }
    else if (state.name === "revealslot") {
        yield put(Action.updateCurrentActionType(ActionType.ATTACK_INPUT_AWAIT));
    } else if (state.name === "revealsunk") {
        const phase = parseInt(yield call(contract.methods.phase().call), 10);
        if (phase === 3) {
            // a winner has been declared, inform the counterparty
            const counterparty: ReturnType<typeof Selector.counterparty> = yield select(Selector.counterparty)
            yield call(counterparty.sendAction, Action.updateCurrentActionType(ActionType.OPEN_SHIPS_INPUT_AWAIT));
        
        } else yield put(Action.updateCurrentActionType(ActionType.ATTACK_INPUT_AWAIT));
    } else if (state.name === "openships") {
        const web3 = yield select(Selector.web3);
        const player = yield select(Selector.player);
        const counterparty = yield select(Selector.counterparty);
        yield call(pass20Blocks, web3, player.address, counterparty.address);

        // now finish game
        yield put(Action.updateCurrentActionType(ActionType.FINISH_GAME_INPUT_AWAIT));
    } else if (state.name === "finishGame") {
        // TODO: some of these awaits could be removed from the bot - as they require no input there
        // start the game again - place a bet
        yield put(Action.updateCurrentActionType(ActionType.PLACE_BET_INPUT_AWAIT));
    } else if (state.name === "placeBet") {
        // we've placed a bet and had it acknowledged - we should now store ships
        yield put(Action.updateCurrentActionType(ActionType.STORE_SHIPS_INPUT_AWAIT));
    } else if (state.name === "storeShips") {
        // we've placed a bet and had it acknowledged - we should now store ships
        yield put(Action.updateCurrentActionType(ActionType.READY_TO_PLAY_INPUT_AWAIT));
    } else if (state.name === "readyToPlay") {
        // if the player goes first, then wait for the opponent to be ready as well
        const player: ReturnType<typeof Selector.player> = yield select(Selector.player);
        const counterparty: ReturnType<typeof Selector.counterparty> = yield select(Selector.counterparty);
        if (player.goesFirst) {
            // the counterparty needs to get ready
            yield call(counterparty.sendAction, Action.updateCurrentActionType(ActionType.PLACE_BET_INPUT_AWAIT));
        } else {
            // if the counterparty is also ready to play, then they should start
            yield call(counterparty.sendAction, Action.updateCurrentActionType(ActionType.ATTACK_INPUT_AWAIT));
        }
    }
}

// TODO: move this into the class structure
export function* actionAfterVerify(verifyState: IVerifyStateUpdate, contract: Contract, playerAddress: string) {
    // if (verifyState.name === "attack") {
    //     yield put(Action.updateCurrentActionType(ActionType.REVEAL_INPUT_AWAIT));
    // } 
    
    // else 
    // if (verifyState.name === "revealsunk") {
        
    // }
}

async function pass20Blocks(web3: Web3, player0: string, player1: string) {
    // TODO: call this separately
    await increaseTimeStamp(30, web3);
    // TODO: pass 20 blocks - need to do this on both chains - or set up to let 0
    await web3.eth.sendTransaction({ from: player0, to: player1, value: 10 });
    await web3.eth.sendTransaction({ from: player0, to: player1, value: 10 });
    await web3.eth.sendTransaction({ from: player0, to: player1, value: 10 });
    await web3.eth.sendTransaction({ from: player0, to: player1, value: 10 });
    await web3.eth.sendTransaction({ from: player0, to: player1, value: 10 });
    await web3.eth.sendTransaction({ from: player0, to: player1, value: 10 });
    await web3.eth.sendTransaction({ from: player0, to: player1, value: 10 });
    await web3.eth.sendTransaction({ from: player0, to: player1, value: 10 });
    await web3.eth.sendTransaction({ from: player0, to: player1, value: 10 });
    await web3.eth.sendTransaction({ from: player0, to: player1, value: 10 });
    await web3.eth.sendTransaction({ from: player0, to: player1, value: 10 });
    await web3.eth.sendTransaction({ from: player0, to: player1, value: 10 });
    await web3.eth.sendTransaction({ from: player0, to: player1, value: 10 });
    await web3.eth.sendTransaction({ from: player0, to: player1, value: 10 });
    await web3.eth.sendTransaction({ from: player0, to: player1, value: 10 });
    await web3.eth.sendTransaction({ from: player0, to: player1, value: 10 });
    await web3.eth.sendTransaction({ from: player0, to: player1, value: 10 });
    await web3.eth.sendTransaction({ from: player0, to: player1, value: 10 });
    await web3.eth.sendTransaction({ from: player0, to: player1, value: 10 });
    await web3.eth.sendTransaction({ from: player0, to: player1, value: 10 });
    await web3.eth.sendTransaction({ from: player0, to: player1, value: 10 });
}
async function increaseTimeStamp(seconds: number, web3: Web3) {
    return new Promise((resolve, reject) => {
        web3.currentProvider.send(
            {
                jsonrpc: "2.0",
                method: "evm_increaseTime",
                params: [seconds],
                id: new Date().getSeconds()
            },
            (err, rep) => {
                if (err) {
                    reject(err);
                } else {
                    resolve(rep);
                }
            }
        );
    });
}

function recover2(message: string, signature: string, v: number) {
    const messageBuffer = Buffer.from(message.split("x")[1], "hex");
    // break the sig

    const splitSignature = signature.split("x")[1];
    const r = Buffer.from(splitSignature.substring(0, 64), "hex");
    const s = Buffer.from((signature.length === 128 ? "00" : "") + splitSignature.substring(64, 128), "hex");
    // we use ethereumjs because web3.eth.personal.ecrecover doesnt work with ganache
    const pub = ethereumjs.ecrecover(messageBuffer, v, r, s);
    const recoveredAddress = "0x" + (ethereumjs.pubToAddress(pub) as any).toString("hex");
    return recoveredAddress;
}

function recover(message: string, signature: string) {
    // buffer and prefix the message
    const prefixedMessage = hashWithPrefix(message);
    const messageBuffer = Buffer.from(prefixedMessage.split("x")[1], "hex");
    // break the sig
    const splitSignature = signature.split("x")[1];
    const r = Buffer.from(splitSignature.substring(0, 64), "hex");
    const s = Buffer.from(splitSignature.substring(64, 128), "hex");
    const v = parseInt(splitSignature.substring(128, 130)) + 27;
    // we use ethereumjs because web3.eth.personal.ecrecover doesnt work with ganache
    const pub = ethereumjs.ecrecover(messageBuffer, v, r, s);
    const recoveredAddress = "0x" + (ethereumjs.pubToAddress(pub) as any).toString("hex");
    return recoveredAddress;
}

function hashWithPrefix(hash: string) {
    return Web3Util.soliditySha3(
        {
            t: "string",
            v: "\u0019Ethereum Signed Message:\n32"
        },
        {
            t: "bytes32",
            v: hash
        }
    );
}

function hashForSetState(hash: string, round: number, channelAddress: string) {
    return Web3Util.soliditySha3(
        {
            t: "bytes32",
            v: hash
        },
        {
            t: "uint",
            v: round
        },
        {
            t: "address",
            v: channelAddress
        }
    );
}
