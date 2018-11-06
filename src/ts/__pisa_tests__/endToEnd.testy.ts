import * as chai from "chai";
import "mocha";
import { Inspector } from "./../inspector";
import { Watcher } from "./../watcher";
const StateChannel = require("./../../external/statechannels/build/contracts/StateChannel.json");
import { KitsuneTools } from "./../kitsuneTools";
import { ethers } from "ethers";

// TODO: great tidying ensues

describe("End to end", () => {
    let player0: string,
        player1: string,
        pisaAccount,
        hashState: string,
        sig0: string,
        sig1: string,
        channelContract: ethers.Contract,
        round: number,
        provider: ethers.providers.JsonRpcProvider = new ethers.providers.JsonRpcProvider("http://localhost:8545");
    

    before(async () => {
        provider.pollingInterval = 100;
        // set the 2 accounts
        const accounts = await provider.listAccounts();
        player0 = accounts[0];
        player1 = accounts[1];
        pisaAccount = accounts[2];

        // deploy the channel
        const channelContractFactory = new ethers.ContractFactory(
            StateChannel.abi,
            StateChannel.bytecode,
            provider.getSigner(accounts[3])
        );
        channelContract = await channelContractFactory.deploy([player0, player1], 10);
        // set the round
        round = 1;
        // set the hash state
        hashState = ethers.utils.keccak256(ethers.utils.toUtf8Bytes("hello"));
        // set the sigs
        const setStateHash = KitsuneTools.hashForSetState(hashState, round, channelContract.address);
        sig0 = await provider.getSigner(player0).signMessage(ethers.utils.arrayify(setStateHash));
        sig1 = await provider.getSigner(player1).signMessage(ethers.utils.arrayify(setStateHash));
    });

    it("inspect and watch a contract", async () => {
        const inspector = new Inspector(10, provider);
        // 1. Verify appointment
        const appointmentRequest = {
            stateUpdate: {
                contractAddress: channelContract.address,
                hashState: hashState,
                round: 1,
                signatures: [sig0, sig1]
            },
            expiryPeriod: 11
        };
        await inspector.inspect(appointmentRequest);
        // 2. If correct create a receipt
        const appointment = inspector.createReceipt(appointmentRequest);

        // 3. pass this appointment to the watcher
        const watcher = new Watcher(provider, provider.getSigner(pisaAccount));
        const player0Contract = channelContract.connect(provider.getSigner(player0));

        await watcher.addAppointment(appointment);
        // 4. Trigger a dispute
        const tx = await player0Contract.triggerDispute();
        const face = await tx.wait();
        await wait(2000);
    }).timeout(3000);
});

const wait = async timeout => {
    const testPromise = new Promise(function(resolve, reject) {
        setTimeout(function() {
            resolve();
        }, timeout);
    });

    return await testPromise;
};
