import Ganache from "ganache-core";
import ethers from "ethers";

// provide the ability to get different providers
const getGanacheProvider = () => {
    const ganache = Ganache.provider({
        mnemonic: "myth like bonus scare over problem client lizard pioneer submit female collect"
    });
    const ganacheProvider = new ethers.providers.Web3Provider(ganache);
    ganacheProvider.pollingInterval = 100;
    return ganache;
};
