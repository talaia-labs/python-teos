import { Drizzle } from "./../../../adjustedDrizzle/drizzle";
import Web3 from "web3";
import { generateStore } from "./../../generateStore";
const localUrl = "ws://localhost:9545";
const remoteUrl = "ws://localhost:8545";

// TODO: enable message to tell user metamask does not exist

export const drizzleInstance = {
    REMOTE: "REMOTE",
    LOCAL: "LOCAL"
};

const createDrizzleOptions = (provider) => {
    return {
        web3: {
            provider: provider,
            block: false
        },
        contracts: [],
        polls: {
            accounts: 1500
        }
    };
};

function initialiseDrizzleInstance(provider, instanceName) {
    const drizzleOptions = createDrizzleOptions(provider);
    const drizzleStore = generateStore(drizzleOptions);
    drizzleStore.instance = instanceName;
    let drizzle = new Drizzle(drizzleOptions, drizzleStore);
    // TODO: bit of a hack since we had slow initialisation! this line shouldnt be required
    // TODO: check for presence in the containers?
    drizzle.web3 = new Web3(provider);
    drizzle.instance = instanceName;
    return drizzle;
}

const theRemoteDrizzle = initialiseDrizzleInstance(new Web3.providers.WebsocketProvider(remoteUrl), drizzleInstance.REMOTE);
window.remoteDrizzle = theRemoteDrizzle;

const theLocalDrizzle = initialiseDrizzleInstance(new Web3.providers.WebsocketProvider(localUrl), drizzleInstance.LOCAL);
window.localDrizzle = theLocalDrizzle;

export default {
    theRemoteDrizzle,
    theLocalDrizzle,
    getDrizzle: function(key) {
        if (key === drizzleInstance.REMOTE) return theRemoteDrizzle;
        else if (key === drizzleInstance.LOCAL) return theLocalDrizzle;
        else throw new Error(`Unknown drizzle instance: ${key}.`);
    }
};
