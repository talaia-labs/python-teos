import * as chai from "chai";
import "mocha";
import { KitsuneInspector } from "./../inspector";
import { KitsuneTools } from "./../kitsuneTools";
import { ethers } from "ethers";
import Ganache from "ganache-core";
const ganache = Ganache.provider({
    mnemonic: "myth like bonus scare over problem client lizard pioneer submit female collect"
});
const provider: ethers.providers.Web3Provider = new ethers.providers.Web3Provider(ganache);
const expect = chai.expect;

const isRejected = async (result: Promise<any>) => {
    return await result.then(
        () => {
            chai.assert.fail();
        },
        reject => {
            expect(reject).to.exist;
        }
    );
};

describe("Inspector", () => {
    let account0: string, account1: string, channelContract: ethers.Contract, hashState: string, disputePeriod: number;

    before(async () => {
        // accounts
        const accounts = await provider.listAccounts();
        account0 = accounts[0];
        account1 = accounts[1];

        // set the dispute period
        disputePeriod = 11;

        // contract
        const channelContractFactory = new ethers.ContractFactory(
            KitsuneTools.ContractAbi,
            KitsuneTools.ContractBytecode,
            provider.getSigner()
        );
        channelContract = await channelContractFactory.deploy([account0, account1], disputePeriod);
        hashState = ethers.utils.keccak256(ethers.utils.toUtf8Bytes("face-off"));
    });

    it("accepts appointment", async () => {
        const round = 1,
            setStateHash = KitsuneTools.hashForSetState(hashState, round, channelContract.address),
            sig0 = await provider.getSigner(account0).signMessage(ethers.utils.arrayify(setStateHash)),
            sig1 = await provider.getSigner(account1).signMessage(ethers.utils.arrayify(setStateHash)),
            expiryPeriod = disputePeriod + 1;
        const inspector = new KitsuneInspector(10, provider);
        await inspector.inspect({
            expiryPeriod,
            stateUpdate: {
                contractAddress: channelContract.address,
                hashState,
                round,
                signatures: [sig0, sig1]
            }
        });

    });

    it("throws for round too low", async () => {
        const round = 0,
            setStateHash = KitsuneTools.hashForSetState(hashState, round, channelContract.address),
            sig0 = await provider.getSigner(account0).signMessage(ethers.utils.arrayify(setStateHash)),
            sig1 = await provider.getSigner(account1).signMessage(ethers.utils.arrayify(setStateHash)),
            expiryPeriod = disputePeriod + 1;

        const inspector = new KitsuneInspector(10, provider);
        await isRejected(
            inspector.inspect({
                expiryPeriod,
                stateUpdate: {
                    contractAddress: channelContract.address,
                    hashState,
                    round,
                    signatures: [sig0, sig1]
                }
            })
        );
    });

    it("throws for expiry equal dispute time", async () => {
        const expiryPeriod = disputePeriod,
            round = 1,
            setStateHash = KitsuneTools.hashForSetState(hashState, round, channelContract.address),
            sig0 = await provider.getSigner(account0).signMessage(ethers.utils.arrayify(setStateHash)),
            sig1 = await provider.getSigner(account1).signMessage(ethers.utils.arrayify(setStateHash));

        const inspector = new KitsuneInspector(10, provider);
        await isRejected(
            inspector.inspect({
                expiryPeriod,
                stateUpdate: {
                    contractAddress: channelContract.address,
                    hashState,
                    round,
                    signatures: [sig0, sig1]
                }
            })
        );
    });

    it("throws for expiry less than dispute time", async () => {
        const expiryPeriod = disputePeriod - 1,
            round = 1,
            setStateHash = KitsuneTools.hashForSetState(hashState, round, channelContract.address),
            sig0 = await provider.getSigner(account0).signMessage(ethers.utils.arrayify(setStateHash)),
            sig1 = await provider.getSigner(account1).signMessage(ethers.utils.arrayify(setStateHash));

        const inspector = new KitsuneInspector(10, provider);
        await isRejected(
            inspector.inspect({
                expiryPeriod,
                stateUpdate: {
                    contractAddress: channelContract.address,
                    hashState,
                    round,
                    signatures: [sig0, sig1]
                }
            })
        );
    });

    it("throws for non existant contract", async () => {
        const expiryPeriod = disputePeriod + 1,
            round = 1,
            setStateHash = KitsuneTools.hashForSetState(hashState, round, channelContract.address),
            sig0 = await provider.getSigner(account0).signMessage(ethers.utils.arrayify(setStateHash)),
            sig1 = await provider.getSigner(account1).signMessage(ethers.utils.arrayify(setStateHash));

        const inspector = new KitsuneInspector(10, provider);
        await isRejected(
            inspector.inspect({
                expiryPeriod,
                stateUpdate: {
                    // random address
                    contractAddress: "0x4bf3A7dFB3b76b5B3E169ACE65f888A4b4FCa5Ee",
                    hashState,
                    round,
                    signatures: [sig0, sig1]
                }
            })
        );
    });

    it("throws for invalid contract address", async () => {
        const expiryPeriod = disputePeriod + 1,
            round = 1,
            setStateHash = KitsuneTools.hashForSetState(hashState, round, channelContract.address),
            sig0 = await provider.getSigner(account0).signMessage(ethers.utils.arrayify(setStateHash)),
            sig1 = await provider.getSigner(account1).signMessage(ethers.utils.arrayify(setStateHash));

        const inspector = new KitsuneInspector(10, provider);

        await isRejected(
            inspector.inspect({
                expiryPeriod,
                stateUpdate: {
                    // invalid address
                    contractAddress: "0x4bf3A7dFB3b76b",
                    hashState,
                    round,
                    signatures: [sig0, sig1]
                }
            })
        );
    });

    it("throws for invalid state hash", async () => {
        const expiryPeriod = disputePeriod + 1,
            round = 1,
            setStateHash = KitsuneTools.hashForSetState(hashState, round, channelContract.address),
            sig0 = await provider.getSigner(account0).signMessage(ethers.utils.arrayify(setStateHash)),
            sig1 = await provider.getSigner(account1).signMessage(ethers.utils.arrayify(setStateHash));

        const inspector = new KitsuneInspector(10, provider);
        await isRejected(
            inspector.inspect({
                expiryPeriod,
                stateUpdate: {
                    contractAddress: channelContract.address,
                    // invalid hash state
                    hashState: "0x4bf3A7dFB3b76b",
                    round,
                    signatures: [sig0, sig1]
                }
            })
        );
    });

    it("throws for wrong state hash", async () => {
        const expiryPeriod = disputePeriod + 1,
            round = 1,
            setStateHash = KitsuneTools.hashForSetState(hashState, round, channelContract.address),
            sig0 = await provider.getSigner(account0).signMessage(ethers.utils.arrayify(setStateHash)),
            sig1 = await provider.getSigner(account1).signMessage(ethers.utils.arrayify(setStateHash));

        const inspector = new KitsuneInspector(10, provider);
        await isRejected(
            inspector.inspect({
                expiryPeriod,
                stateUpdate: {
                    contractAddress: channelContract.address,
                    // substute the state hash for the set state hash
                    hashState: setStateHash,
                    round,
                    signatures: [sig0, sig1]
                }
            })
        );
    });

    it("throws for sigs on wrong hash", async () => {
        const expiryPeriod = disputePeriod + 1,
            round = 1,
            // setStateHash = KitsuneTools.hashForSetState(hashState, round, channelContract.address),
            // sign the wrong hash
            sig0 = await provider.getSigner(account0).signMessage(ethers.utils.arrayify(hashState)),
            sig1 = await provider.getSigner(account1).signMessage(ethers.utils.arrayify(hashState));

        const inspector = new KitsuneInspector(10, provider);
        await isRejected(
            inspector.inspect({
                expiryPeriod,
                stateUpdate: {
                    contractAddress: channelContract.address,
                    hashState,
                    round,
                    signatures: [sig0, sig1]
                }
            })
        );
    });

    it("throws for sigs by only one player", async () => {
        const expiryPeriod = disputePeriod + 1,
            round = 1,
            setStateHash = KitsuneTools.hashForSetState(hashState, round, channelContract.address),
            // sign both with account 0
            sig0 = await provider.getSigner(account0).signMessage(ethers.utils.arrayify(setStateHash)),
            sig1 = await provider.getSigner(account0).signMessage(ethers.utils.arrayify(setStateHash));

        const inspector = new KitsuneInspector(10, provider);
        await isRejected(
            inspector.inspect({
                expiryPeriod,
                stateUpdate: {
                    contractAddress: channelContract.address,
                    hashState,
                    round,
                    signatures: [sig0, sig1]
                }
            })
        );
    });

    it("throws for missing sig", async () => {
        const expiryPeriod = disputePeriod + 1,
            round = 1,
            setStateHash = KitsuneTools.hashForSetState(hashState, round, channelContract.address),
            //sig0 = await provider.getSigner(account0).signMessage(ethers.utils.arrayify(setStateHash)),
            sig1 = await provider.getSigner(account1).signMessage(ethers.utils.arrayify(setStateHash));

        const inspector = new KitsuneInspector(10, provider);
        await isRejected(
            inspector.inspect({
                expiryPeriod,
                stateUpdate: {
                    contractAddress: channelContract.address,
                    hashState,
                    round,
                    signatures: [sig1]
                }
            })
        );
    });

    it("accepts sigs in wrong order", async () => {
        const expiryPeriod = disputePeriod + 1,
            round = 1,
            setStateHash = KitsuneTools.hashForSetState(hashState, round, channelContract.address),
            sig0 = await provider.getSigner(account0).signMessage(ethers.utils.arrayify(setStateHash)),
            sig1 = await provider.getSigner(account1).signMessage(ethers.utils.arrayify(setStateHash));

        const inspector = new KitsuneInspector(10, provider);
        await inspector.inspect({
            expiryPeriod,
            stateUpdate: {
                contractAddress: channelContract.address,
                hashState,
                round,
                signatures: [sig1, sig0]
            }
        });
    });
});
