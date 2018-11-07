import * as chai from "chai";
import "mocha";
const StateChannel = require("./../../external/statechannels/build/contracts/StateChannel.json");
import request from "request-promise";
import { KitsuneTools } from "./../kitsuneTools";
import { ethers } from "ethers";
const provider = new ethers.providers.JsonRpcProvider("http://localhost:8545");
provider.pollingInterval = 100;

describe("Service end-to-end", () => {
    let account0,
        account1,
        channelContract: ethers.Contract,
        hashState,
        disputePeriod,
        pisaUrl = "http://localhost:3000";

    before(async () => {
        // accounts
        const accounts = await provider.listAccounts();
        account0 = accounts[0];
        account1 = accounts[1];

        // set the dispute period
        disputePeriod = 10;

        // contract
        const channelContractFactory = new ethers.ContractFactory(
            StateChannel.abi,
            StateChannel.bytecode,
            provider.getSigner()
        );
        channelContract = await channelContractFactory.deploy([account0, account1], disputePeriod);
        hashState = ethers.utils.keccak256(ethers.utils.toUtf8Bytes("face-off"));
    });

    it("create channel, submit appointment, trigger dispute, wait for response", async () => {
        const round = 1,
            setStateHash = KitsuneTools.hashForSetState(hashState, round, channelContract.address),
            sig0 = await provider.getSigner(account0).signMessage(ethers.utils.arrayify(setStateHash)),
            sig1 = await provider.getSigner(account1).signMessage(ethers.utils.arrayify(setStateHash)),
            expiryPeriod = disputePeriod + 1;
        const appointmentRequest = {
            expiryPeriod,
            stateUpdate: {
                contractAddress: channelContract.address,
                hashState,
                round,
                signatures: [sig0, sig1]
            }
        };

        // TODO: should be starting the service ourselves here, for now assume started
        await request.post(pisaUrl, { json: appointmentRequest });

        // now register a callback on the setstate event and trigger a response
        const setStateEvent = "EventEvidence(uint256, bytes32)";
        let successResult = { success: false };
        channelContract.on(setStateEvent, () => {
            channelContract.removeAllListeners(setStateEvent);
            successResult.success = true;
        });

        // trigger a dispute
        const tx = await channelContract.triggerDispute();
        await tx.wait();
        
        try {
            // wait for the success result
            await waitForPredicate(successResult, s => s.success, 400);
        } catch (doh) {
            // fail if we dont get it
            chai.assert.fail(true, false, "EventEvidence not successfully registered.");
        }
    }).timeout(3000);
});

// assess the value of a predicate after a timeout, throws if predicate does not evaluate to true
const waitForPredicate = <T1>(successResult: T1, predicate: (a: T1) => boolean, timeout) => {
    return new Promise((resolve, reject) => {
        setTimeout(() => {
            if (predicate(successResult)) {
                resolve();
            } else {
                reject();
            }
        }, timeout);
    });
};
