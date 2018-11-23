export interface IConfig {
    jsonRpcUrl: string;
    host: {
        name: string;
        port: number;
    },
    watcherKey: string;
}
// PISA: the inspector should take the dispute period value from config