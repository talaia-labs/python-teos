import request from "request-promise";
import { KitsuneTools } from "../../src/kitsuneTools";
import { ethers } from "ethers";
import { IConfig } from "../../src/dataEntities/config";
import { getJsonRPCProvider } from "../../src/provider";
const config = require("../../config.json") as IConfig;
let account0: string, account1: string, channelContract: ethers.Contract, hashState: string, disputePeriod: number;

let setup = async () => {
    // accounts
    const provider = await getJsonRPCProvider();
    const accounts = await provider.listAccounts();
    account0 = accounts[0];
    account1 = accounts[1];

    // set the dispute period
    disputePeriod = 15;

    // contract
    const channelContractFactory = new ethers.ContractFactory(
        KitsuneTools.ContractAbi,
        KitsuneTools.ContractBytecode,
        provider.getSigner()
    );
    channelContract = await channelContractFactory.deploy([account0, account1], disputePeriod);
    hashState = ethers.utils.keccak256(ethers.utils.toUtf8Bytes("face-off"));
};

let execute = async () => {
    const provider = await getJsonRPCProvider();
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

    await request.post(`http://${config.host.name}:${config.host.port}/appointment`, {
        json: appointmentRequest
    });

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

    // wait for the success result
    await waitForPredicate(successResult, s => s.success, 1000);
};

// assess the value of a predicate after a timeout, throws if predicate does not evaluate to true
const waitForPredicate = <T1>(successResult: T1, predicate: (a: T1) => boolean, timeout: number) => {
    return new Promise((resolve, reject) => {
        setTimeout(() => {
            if (predicate(successResult)) {
                resolve();
            } else {
                reject("Predicate not satisfied.");
            }
        }, timeout);
    });
};

let flow = async () => {
    await setup();
    await execute();
};
console.log("Executing smoke tests");
flow().then(
    () => {
        console.log("Tests passed.");
        process.exit(0);
    },
    err => {
        console.log("Tests failed!");
        console.log(err);
        process.exit(1);
    }
);
