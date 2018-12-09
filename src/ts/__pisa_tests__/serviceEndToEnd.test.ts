import * as chai from "chai";
import "mocha";
import request from "request-promise";
import { KitsuneTools } from "../kitsuneTools";
import { ethers } from "ethers";
import { KitsuneInspector } from "../inspector";
import { KitsuneWatcher } from "../watcher";
import { PisaService } from "../service";
import { IConfig } from "../dataEntities/config";
import Ganache from "ganache-core";
import { IAppointmentRequest } from "../dataEntities/appointment";
import logger from "../logger";
logger.transports.forEach(l => (l.level = "max"));

const ganache = Ganache.provider({
    mnemonic: "myth like bonus scare over problem client lizard pioneer submit female collect"
});
const config: IConfig = {
    host: {
        name: "localhost",
        port: 3000
    },
    jsonRpcUrl: "http://localhost:8545",
    watcherKey: "0x6370fd033278c143179d81c5526140625662b8daa446c22ee2d73db3707e620c"
};
const provider = new ethers.providers.Web3Provider(ganache);
provider.pollingInterval = 100;

describe("Service end-to-end", () => {
    let account0: string,
        account1: string,
        channelContract: ethers.Contract,
        hashState: string,
        disputePeriod: number,
        service: PisaService;

    beforeEach(async () => {
        const watcherWallet = new ethers.Wallet(config.watcherKey, provider);
        const watcher = new KitsuneWatcher(provider, watcherWallet);
        const inspector = new KitsuneInspector(10, provider);
        service = new PisaService(config.host.name, config.host.port, inspector, watcher);

        // accounts
        const accounts = await provider.listAccounts();
        account0 = accounts[0];
        account1 = accounts[1];

        // set the dispute period
        disputePeriod = 10;

        // contract
        const channelContractFactory = new ethers.ContractFactory(
            KitsuneTools.ContractAbi,
            KitsuneTools.ContractBytecode,
            provider.getSigner()
        );
        channelContract = await channelContractFactory.deploy([account0, account1], disputePeriod);
        hashState = ethers.utils.keccak256(ethers.utils.toUtf8Bytes("face-off"));
    });

    afterEach(() => {
        service.stop();
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

        await request.post(`http://${config.host.name}:${config.host.port}/appointment`, { json: appointmentRequest });

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

    it("create channel, submit round = 0 too low returns 400", async () => {
        const round = 0,
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

        await failWithCode('400 - "Supplied appointment round', appointmentRequest);
    }).timeout(3000);

    it("create channel, submit round = -1 too low returns 400", async () => {
        const round = -1,
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

        await failWithCode('400 - "Supplied appointment round', appointmentRequest);
    }).timeout(3000);

    it("create channel, expiry = dispute period returns 400", async () => {
        const round = 1,
            setStateHash = KitsuneTools.hashForSetState(hashState, round, channelContract.address),
            sig0 = await provider.getSigner(account0).signMessage(ethers.utils.arrayify(setStateHash)),
            sig1 = await provider.getSigner(account1).signMessage(ethers.utils.arrayify(setStateHash)),
            expiryPeriod = disputePeriod;
        const appointmentRequest = {
            expiryPeriod,
            stateUpdate: {
                contractAddress: channelContract.address,
                hashState,
                round,
                signatures: [sig0, sig1]
            }
        };

        await failWithCode('400 - "Supplied appointment expiryPeriod', appointmentRequest);
    }).timeout(3000);

    it("create channel, expiry period = dispute period - 1 too low returns 400", async () => {
        const round = 1,
            setStateHash = KitsuneTools.hashForSetState(hashState, round, channelContract.address),
            sig0 = await provider.getSigner(account0).signMessage(ethers.utils.arrayify(setStateHash)),
            sig1 = await provider.getSigner(account1).signMessage(ethers.utils.arrayify(setStateHash)),
            expiryPeriod = disputePeriod - 1;
        const appointmentRequest = {
            expiryPeriod,
            stateUpdate: {
                contractAddress: channelContract.address,
                hashState,
                round,
                signatures: [sig0, sig1]
            }
        };

        await failWithCode('400 - "Supplied appointment expiryPeriod', appointmentRequest);
    }).timeout(3000);

    it("create channel, non existant contact returns 400", async () => {
        const round = 1,
            setStateHash = KitsuneTools.hashForSetState(hashState, round, channelContract.address),
            sig0 = await provider.getSigner(account0).signMessage(ethers.utils.arrayify(setStateHash)),
            sig1 = await provider.getSigner(account1).signMessage(ethers.utils.arrayify(setStateHash)),
            expiryPeriod = disputePeriod + 1;
        const appointmentRequest = {
            expiryPeriod,
            stateUpdate: {
                // random address
                contractAddress: "0x4bf3A7dFB3b76b5B3E169ACE65f888A4b4FCa5Ee",
                hashState,
                round,
                signatures: [sig0, sig1]
            }
        };

        await failWithCode(`400 - "No code found at address ${appointmentRequest.stateUpdate.contractAddress}`, appointmentRequest);
    }).timeout(3000);

    it("create channel, invalid contract address returns 400", async () => {
        const round = 1,
            setStateHash = KitsuneTools.hashForSetState(hashState, round, channelContract.address),
            sig0 = await provider.getSigner(account0).signMessage(ethers.utils.arrayify(setStateHash)),
            sig1 = await provider.getSigner(account1).signMessage(ethers.utils.arrayify(setStateHash)),
            expiryPeriod = disputePeriod + 1;
        const appointmentRequest = {
            expiryPeriod,
            stateUpdate: {
                // invalid address
                contractAddress: "0x4bf3A7dFB3b76b",
                hashState,
                round,
                signatures: [sig0, sig1]
            }
        };

        await failWithCode(
            `400 - "${appointmentRequest.stateUpdate.contractAddress} is not a valid address.`,
            appointmentRequest
        );
    }).timeout(3000);

    it("create channel, invalid state hash returns 400", async () => {
        const round = 1,
            setStateHash = KitsuneTools.hashForSetState(hashState, round, channelContract.address),
            sig0 = await provider.getSigner(account0).signMessage(ethers.utils.arrayify(setStateHash)),
            sig1 = await provider.getSigner(account1).signMessage(ethers.utils.arrayify(setStateHash)),
            expiryPeriod = disputePeriod + 1;
        const appointmentRequest = {
            expiryPeriod,
            stateUpdate: {
                contractAddress: channelContract.address,
                // invalid hash state
                hashState: "0x4bf3A7dFB3b76b",
                round,
                signatures: [sig0, sig1]
            }
        };

        await failWithCode(`400 - "Invalid bytes32: ${appointmentRequest.stateUpdate.hashState}`, appointmentRequest);
    }).timeout(3000);

    it("create channel, wrong state hash returns 400", async () => {
        const round = 1,
            setStateHash = KitsuneTools.hashForSetState(hashState, round, channelContract.address),
            sig0 = await provider.getSigner(account0).signMessage(ethers.utils.arrayify(setStateHash)),
            sig1 = await provider.getSigner(account1).signMessage(ethers.utils.arrayify(setStateHash)),
            expiryPeriod = disputePeriod + 1;
        const appointmentRequest = {
            expiryPeriod,
            stateUpdate: {
                contractAddress: channelContract.address,
                // substute the state hash for the set state hash
                hashState: setStateHash,
                round,
                signatures: [sig0, sig1]
            }
        };

        await failWithCode(
            '400 - "Party 0x90F8bf6A479f320ead074411a4B0e7944Ea8c9C1 not present in signatures',
            appointmentRequest
        );
    }).timeout(3000);

    it("create channel, wrong sig on hash returns 400", async () => {
        const expiryPeriod = disputePeriod + 1,
            round = 1,
            // setStateHash = KitsuneTools.hashForSetState(hashState, round, channelContract.address),
            // sign the wrong hash
            sig0 = await provider.getSigner(account0).signMessage(ethers.utils.arrayify(hashState)),
            sig1 = await provider.getSigner(account1).signMessage(ethers.utils.arrayify(hashState));
        const appointmentRequest = {
            expiryPeriod,
            stateUpdate: {
                contractAddress: channelContract.address,
                hashState,
                round,
                signatures: [sig0, sig1]
            }
        };

        await failWithCode(
            '400 - "Party 0x90F8bf6A479f320ead074411a4B0e7944Ea8c9C1 not present in signatures',
            appointmentRequest
        );
    }).timeout(3000);

    it("create channel, sigs by only one player returns 400", async () => {
        const expiryPeriod = disputePeriod + 1,
            round = 1,
            setStateHash = KitsuneTools.hashForSetState(hashState, round, channelContract.address),
            // sign both with account 0
            sig0 = await provider.getSigner(account0).signMessage(ethers.utils.arrayify(setStateHash)),
            sig1 = await provider.getSigner(account0).signMessage(ethers.utils.arrayify(setStateHash));

        const appointmentRequest = {
            expiryPeriod,
            stateUpdate: {
                contractAddress: channelContract.address,
                hashState,
                round,
                signatures: [sig0, sig1]
            }
        };

        await failWithCode(
            '400 - "Party 0xFFcf8FDEE72ac11b5c542428B35EEF5769C409f0 not present in signatures',
            appointmentRequest
        );
    }).timeout(3000);

    it("create channel, missing sig returns 400", async () => {
        const expiryPeriod = disputePeriod + 1,
            round = 1,
            setStateHash = KitsuneTools.hashForSetState(hashState, round, channelContract.address),
            //sig0 = await provider.getSigner(account0).signMessage(ethers.utils.arrayify(setStateHash)),
            sig1 = await provider.getSigner(account1).signMessage(ethers.utils.arrayify(setStateHash));

        const appointmentRequest = {
            expiryPeriod,
            stateUpdate: {
                contractAddress: channelContract.address,
                hashState,
                round,
                signatures: [sig1]
            }
        };

        await failWithCode('400 - "Incorrect number of signatures supplied', appointmentRequest);
    }).timeout(3000);

    it("create channel, sigs in wrong order returns 200", async () => {
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
        try {
            await request.post(`http://${config.host.name}:${config.host.port}/appointment`, {
                json: appointmentRequest
            });
        } catch (doh) {
            chai.assert.fail();
        }
    }).timeout(3000);

    const failWithCode = async (errorMessage: string, appointmentRequest: IAppointmentRequest) => {
        try {
            await request.post(`http://${config.host.name}:${config.host.port}/appointment`, {
                json: appointmentRequest
            });
            chai.assert.fail(true, false, "Request was successful when it should have failed.");
        } catch (doh) {
            if (doh instanceof Error && doh.message.startsWith(errorMessage)) {
                // success
            } else if (doh instanceof Error) {
                chai.assert.fail(true, false, doh.message);
            } else chai.assert.fail(true, false, doh);
        }
    };
});

// assess the value of a predicate after a timeout, throws if predicate does not evaluate to true
const waitForPredicate = <T1>(successResult: T1, predicate: (a: T1) => boolean, timeout: number) => {
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
