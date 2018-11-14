import * as chai from "chai";
import "mocha";
import request from "request-promise";
import { KitsuneTools } from "./../kitsuneTools";
import { ethers } from "ethers";
import { KitsuneInspector } from "./../inspector";
import { KitsuneWatcher } from "./../watcher";
import { PisaService } from "./../service";
import { IConfig } from "./../dataEntities/config";
import Ganache from "ganache-core";
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

    before(async () => {
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

    after(() => {
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
