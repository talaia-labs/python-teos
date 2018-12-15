import { IAppointment } from "./dataEntities/appointment";
import { ethers } from "ethers";
import { KitsuneTools } from "./kitsuneTools";
import logger from "./logger";
import { inspect } from "util";

/**
 * A watcher is responsible for watching for, and responding to, events emitted on-chain.
 */
export class Watcher {
    constructor(
        private readonly provider: ethers.providers.BaseProvider,
        private readonly signer: ethers.Signer,
        private readonly channelAbi: any,
        private readonly eventName: string,
        private readonly eventCallback: (
            contract: ethers.Contract,
            appointment: IAppointment,
            ...args: any[]
        ) => Promise<any>
    ) {}

    /**
     * Watch for an event specified by the appointment, and respond if it the event is raised.
     * @param appointment Contains information about where to watch for events, and what information to suppli as part of a response
     */
    async watch(appointment: IAppointment) {
        // PSA: safety check the appointment - check the inspection time?

        // create a contract
        logger.info(
            `Begin watching for event ${this.eventName} in contract ${appointment.stateUpdate.contractAddress}.`
        );
        logger.debug(`Watching appointment: ${appointment}.`);

        const contract = new ethers.Contract(
            appointment.stateUpdate.contractAddress,
            this.channelAbi,
            this.provider
        ).connect(this.signer);

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
                // an error occured whilst responding to the callback - this is serious and the problem needs to be correctly diagnosed
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

export class KitsuneWatcher extends Watcher {
    constructor(provider: ethers.providers.BaseProvider, signer: ethers.Signer) {
        super(provider, signer, KitsuneTools.ContractAbi, "EventDispute(uint256)", KitsuneTools.respond);
    }
}
