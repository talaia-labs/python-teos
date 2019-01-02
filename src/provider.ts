import Ganache from "ganache-core";
import { ethers } from "ethers";
import { IConfig } from "./dataEntities/config";
const config = require("./config.json") as IConfig;

// provide the ability to get different providers

export const getGanacheProvider = () => {
  const ganache = Ganache.provider({
    mnemonic:
      "myth like bonus scare over problem client lizard pioneer submit female collect"
  });
  const ganacheProvider = new ethers.providers.Web3Provider(ganache);
  ganacheProvider.pollingInterval = 100;
  validateProvider(ganacheProvider);
  return ganache;
};

export const getJsonRPCProvider = () => {
  const provider = new ethers.providers.JsonRpcProvider(config.jsonRpcUrl);
  validateProvider(provider);
  return provider;
};

export const getInfuraProvider = (): ethers.providers.InfuraProvider => {
  const infura: any = config.infura;
  const infuraProvider = new ethers.providers.InfuraProvider(
    config.infura.currentNetwork,
    infura[`${config.infura.currentNetwork}`].apikey
  );

  validateProvider(infuraProvider);

  return infuraProvider;
};

export async function validateProvider(provider: ethers.providers.Provider) {
  try {
    /* if the provider is working then a valid response of a number will be returned
            otherwise, an error will be thrown such as invalid JSON response "" which indicates 
            the connection failed, the error will be caught here and a separate error will be thrown.
            The address is a random valid address taken from ethersjs documentation
      */
    await provider.getTransactionCount(
      "0xD115BFFAbbdd893A6f7ceA402e7338643Ced44a6"
    );
  } catch (err) {
    throw new Error(
      `Provider ${JSON.stringify(provider)} failed to connect: ${err}`
    );
  }
}
