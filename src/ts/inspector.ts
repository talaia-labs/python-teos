import { IAppointmentRequest, IAppointment } from "./dataEntities/appointment";
import { KitsuneTools } from "./kitsuneTools";
import { ethers } from "ethers";
import { verifyMessage } from "ethers/utils";
import logger from "./logger";

/**
 * Responsible for deciding whether to accept appointments
 */
export class Inspector {
    constructor(
        private readonly minimumDisputePeriod: number,
        private readonly provider: ethers.providers.BaseProvider,
        private readonly channelAbi: any,
        private readonly hashForSetState: (hState: string, round: number, channelAddress: string) => string,
        private readonly participants: (contract: ethers.Contract) => Promise<string[]>,
        private readonly round: (contract: ethers.Contract) => Promise<number>,
        private readonly disputePeriod: (contract: ethers.Contract) => Promise<number>,
        private readonly status: (contract: ethers.Contract) => Promise<number>
    ) {}

    /**
     * Inspects an appointment to decide whether to accept it. Throws on reject.
     * @param appointment
     */
    public async inspect(appointment: IAppointmentRequest) {
        // log the appointment we're inspecting
        logger.info(`Inspecting appointment ${appointment.stateUpdate.hashState} for contract ${appointment.stateUpdate.contractAddress}.`)
        logger.debug("Appointment request: " + JSON.stringify(appointment));

        // get the participants
        const contract = new ethers.Contract(appointment.stateUpdate.contractAddress, this.channelAbi, this.provider);

        const participants = await this.participants(contract);
        logger.info(`Participants at ${contract.address}: ${JSON.stringify(participants)}`);

        // form the hash
        const setStateHash = this.hashForSetState(
            appointment.stateUpdate.hashState,
            appointment.stateUpdate.round,
            appointment.stateUpdate.contractAddress
        );

        // check the sigs
        this.checkAllSigned(setStateHash, participants, appointment.stateUpdate.signatures);
        logger.info("All participants have signed.");

        // check that the supplied state round is valid
        const channelRound: number = await this.round(contract);
        logger.info(`Round at ${contract.address}: ${channelRound.toString(10)}`);
        if (channelRound >= appointment.stateUpdate.round) {
            throw new Error(
                `Supplied appointment round ${
                    appointment.stateUpdate.round
                } is not greater than channel round ${channelRound}`
            );
        }

        // check that the channel is not in a dispute
        const channelDisputePeriod: number = await this.disputePeriod(contract);
        logger.info(`Dispute period at ${contract.address}: ${channelDisputePeriod.toString(10)}`);
        if (appointment.expiryPeriod <= channelDisputePeriod) {
            throw new Error(
                `Supplied appointment expiryPeriod ${
                    appointment.expiryPeriod
                } is not greater than the channel dispute period ${channelDisputePeriod}`
            );
        }
        // TODO: dispute period is a block number! we're comparing apples to oranges here
        if (channelDisputePeriod < this.minimumDisputePeriod) {
            throw new Error(
                `Channel dispute period ${channelDisputePeriod} is less than the minimum acceptable dispute period ${
                    this.minimumDisputePeriod
                }`
            );
        }

        const channelStatus: number = await this.status(contract);
        logger.info(`Channel status at ${contract.address}: ${JSON.stringify(channelStatus)}`);
        // ON = 0, DISPUTE = 1, OFF = 2
        if (channelStatus != 0) {
            throw new Error(`Channel status is ${channelStatus} not 0.`);
        }

        return this.createAppointment(appointment);
    }

    /**
     * Converts an appointment request into an appointment
     * @param request
     */
    private createAppointment(request: IAppointmentRequest): IAppointment {
        const startTime = Date.now();

        return {
            stateUpdate: request.stateUpdate,
            startTime: startTime,
            endTime: startTime + request.expiryPeriod,
            inspectionTime : Date.now()
        };
    }

    /**
     * Check that every participant that every participant has signed the message.
     * @param message
     * @param participants
     * @param sigs 
     */
    private checkAllSigned(message: string, participants: string[], sigs: string[]) {
        if (participants.length !== sigs.length) {
            throw new Error(
                `Incorrect number of signatures supplied. Participants: ${participants.length}, signers: ${sigs.length}`
            );
        }

        const signers = sigs.map(sig => verifyMessage(ethers.utils.arrayify(message), sig));
        participants.forEach(party => {
            const signerIndex = signers.map(m => m.toLowerCase()).indexOf(party.toLowerCase());
            if (signerIndex === -1) throw new Error(`Party ${party} not present in signatures.`);

            // remove the signer, so that we never look for it again
            signers.splice(signerIndex, 1);
        });
    }
}

export class KitsuneInspector extends Inspector {
    constructor(disputePeriod: number, provider: ethers.providers.BaseProvider) {
        super(
            disputePeriod,
            provider,
            KitsuneTools.ContractAbi,
            KitsuneTools.hashForSetState,
            KitsuneTools.participants,
            KitsuneTools.round,
            KitsuneTools.disputePeriod,
            KitsuneTools.status
        );
    }
}
