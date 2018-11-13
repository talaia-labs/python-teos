import { IAppointment } from "./dataEntities/appointment";
import { ethers } from "ethers";
import { KitsuneTools } from "./kitsuneTools";
const StateChannel = require("./../external/statechannels/build/contracts/StateChannel.json");
import logger from "./logger";
import { inspect } from "util";

// TODO: in here and in the inspector refuse to accept multiple requests for the same job?
// TODO: initially yes

export class Watcher {
    // TODO: this class is not thread safe, and we should have readonly here
    constructor(
        private readonly provider: ethers.providers.BaseProvider,
        private readonly signer: ethers.Signer,
        private readonly channelAbi: any,
        // TODO: this should be response event / response callback
        private readonly eventName: string,
        private readonly eventCallback: (
            contract: ethers.Contract,
            appointment: IAppointment,
            ...args: any[]
        ) => Promise<any>
    ) {}

    // TODO:
    // adds appointment to a watch list
    // subscribes to the correct events on the appointed contract
    // dont throw errors in the callback

    // TODO: this should really be a watcher factory class - it should produce watchers

    async watch(appointment: IAppointment) {
        // TODO: how to 'type' the callback?
        // TODO: it has multiple types, wrap into one type T1 + eventInfo
        //     // add this appointment to the watch list
        //     // TODO: safety check the appointment
        //     // TODO: the time constraints

        // create a contract
        logger.info(`Begin watching for event ${this.eventName} in contract ${appointment.stateUpdate.contractAddress}.`);
        logger.debug(`Watching appointment: ${appointment}.`)

        const contract = new ethers.Contract(
            appointment.stateUpdate.contractAddress,
            this.channelAbi,
            this.provider
        ).connect(this.signer);

        // TODO: lock this, it shouldnt be triggered concurrently for the same subscription
        // TODO: we lack error handling throughout
        // TODO: require detailed tracing for all actions

        // TODO: if we have multiple watchers for the same job we need to not submit multiple transactions

        // TODO: 2. check that the dispute was triggered within the correct time period

        // watch the supplied event
        contract.on(this.eventName, async (...args: any[]) => {
            // this callback should not throw exceptions as they cannot be handled elsewhere
            

            // call the callback
            try {
                logger.info(
                    `Observed event ${this.eventName} in contract ${contract.address} with arguments : ${args.slice(
                        0,
                        args.length - 1
                    )}. Beginning response.`
                );
                logger.debug(`Event info ${inspect(args[1])}`);
                await this.eventCallback(contract, appointment, ...args);
            } catch (doh) {
                // an error occured whilst responding to the callback - this is serious and the problem needs to be correctly diagnosed.
                // TODO: we need retry behaviour here + clever diagnosis + error escalation
                logger.error(
                    `Error occured whilst responding to event ${this.eventName} in contract ${contract.address}.`
                );
            }

            // remove subscription - we've satisfied our appointment
            try {
                logger.info(`Reponse successful, removing listener.`);
                contract.removeAllListeners(this.eventName);
                logger.info(`Listener removed.`);
            } catch (doh) {
                logger.error(`Failed to remove listener on event ${this.eventName} in contract ${contract.address}.`);
            }
        });
    }
}

// TODO: documentation in this file
export class KitsuneWatcher extends Watcher {
    constructor(provider: ethers.providers.BaseProvider, signer: ethers.Signer) {
        super(provider, signer, StateChannel.abi, "EventDispute(uint256)", KitsuneTools.respond);
    }
}
