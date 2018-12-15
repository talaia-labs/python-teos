export interface IConfig {
    jsonRpcUrl: string;
    host: {
        name: string;
        port: number;
    },
    watcherKey: string;
    infura?: {
        currentNetwork: string
        ropsten: {
            apikey: string;
            url: string
        },
        rinkeby: {
            apikey: string;
            url: string
        }
    }
}