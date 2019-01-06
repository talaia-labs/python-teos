import request from "request-promise";
import { KitsuneTools } from "../../src/kitsuneTools";
import { ethers } from "ethers";
import { IConfig } from "../../src/dataEntities/config";
import { getJsonRPCProvider } from "../../src/provider";
let config = require("../../config.json") as IConfig;

let account0: string,
    account1: string,
    channelContracts: ethers.Contract[] = [],
    hashState: string,
    disputePeriod: number;

// concurrently watch for x events
let setup = async (creationCount: number) => {
    const provider = await getJsonRPCProvider();
    if (creationCount <= 0) {
        console.error("Specify more than 0 requests.");
        process.exit(1);
    }
    // accounts
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

    for (let contractIndex = 0; contractIndex < creationCount; contractIndex++) {
        let contract = await channelContractFactory.deploy([account0, account1], disputePeriod);
        channelContracts.push(contract);
    }
    hashState = ethers.utils.keccak256(ethers.utils.toUtf8Bytes("face-off"));
};

let execute = async (timeToWait: number) => {
    const provider = await getJsonRPCProvider();
    const eventReceived: boolean[] = [];

    for (let index = 0; index < channelContracts.length; index++) {
        const channelContract = channelContracts[index];

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

        // now register a callback on the setstate event and trigger a response
        const setStateEvent = "EventEvidence(uint256, bytes32)";
        eventReceived[index] = false;
        channelContract.on(setStateEvent, () => {
            channelContract.removeAllListeners(setStateEvent);
            console.log(`Set state acknowleged for contract ${channelContract.address}.`);
            eventReceived[index] = true;
        });

        // now send the appointment
        await request.post(`http://${config.host.name}:${config.host.port}/appointment`, {
            json: appointmentRequest
        });
        console.log(`Appointment request made for contract: ${channelContract.address}.`);
    }

    await Promise.all(
        channelContracts.map(async c => {
            const tx = await c.triggerDispute();
            await tx;
            console.log(`Dispute triggered for ${c.address}`);
        })
    );

    // wait a little
    await waitForPredicate({}, () => true, timeToWait);

    // wait for the success result
    await waitForPredicate(eventReceived, s => s.length == channelContracts.length && s.reduce((a, b) => a && b), 400);
    console.log(`${eventReceived.length} appointments accepted.`);
};

// TODO: there are multiple versions of this around
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

const flow = async (requestCount: number, waitTime: number) => {
    await setup(requestCount);
    await execute(waitTime);
};
if (process.argv.length !== 4) {
    console.error("Incorrect arguments supplied. Supply number of requests to make and the time to wait (ms).");
    process.exit(1);
}

const requestCount = parseInt(process.argv[2], 10);
const waitTimeMs = parseInt(process.argv[3], 10);
console.log("Executing load tests");
flow(
    requestCount,
    waitTimeMs
).then(
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
