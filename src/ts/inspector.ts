const StateChannel = require("./../external/statechannels/build/contracts/StateChannel.json");
import { IAppointmentRequest, IAppointment } from "./dataEntities/appointment";
import { KitsuneTools } from "./kitsuneTools";
import { ethers } from "ethers";
import { verifyMessage } from "ethers/utils";
import logger from "./logger";

// given an appointment inspect it to see if it's valid for PISA
// 1. Assess the signature of the contract
// 2. Assess the participants of the channel to see if the appointee is valid
// *** 3. Assess that the appointment has indeed been signed by these participants
// *** 4. Check that the state round > round in channel
// *** 5. Check that expiry is positive and that it is greater than the time specified in the channel
// *** 6. Check that the channel is ok state - not dispute
// 8. Check that the channel settle time is reasonable, not too small
// 9. If so, we sign a new appointment

// to be valid for pisa it needs to have a set s
export class Inspector {
    constructor(
        private readonly minimumDisputePeriod: number,
        private readonly provider: ethers.providers.BaseProvider
    ) {}
    // TODO: break this class
    // TODO: document public methods

    // TODO: some of the validation below is not strictly necessary right?
    // TODO: the watchtower could accept the an invalid appointment, which it would be unable to fulfil
    // TODO: but in some cases the appointment could also not be used to penalise the tower - as it was invalid

    /**
     * Inspects an appointment to decide whether to take a job. Throws on reject.
     * @param appointment
     */
    public async inspect(appointment: IAppointmentRequest) {
        // TODO: check that the contract was instantiated by the correct factory contract
        // TODO: accept any appointment, however, if a channel is not already in a specific registry that it cannot be included! - this could be resolved at custodian dispute time
        // TODO: we could augment the state channel factory to achieve this - add a mapping there

        // TODO: the validation in here is a dos vector, especially if it's expensive

        // const bytecode = await this.web3.eth.getCode(appointment.contractAddress);
        // console.log((bytecode as string).substring(0, 100));
        // if (bytecode != StateChannel.bytecode) {
        //     throw new Error(`Contract at address ${appointment.contractAddress} does not have correct bytecode.`);
        // }

        // log the appointment we're inspecting
        logger.info("Appointment request: " + JSON.stringify(appointment));

        // get the participants
        const contract = new ethers.Contract(appointment.stateUpdate.contractAddress, StateChannel.abi, this.provider);

        // TODO: we're assuming 2 party here - this is because we would need to add plist.getLength() function
        // TODO: since at the moment we cant check for the length of an array just with an array getter
        const participants = [await contract.plist(0), await contract.plist(1)] as string[];
        logger.info(`Participants at ${contract.address}: ${JSON.stringify(participants)}`);

        // check the sigs
        this.checkAllSigned(
            appointment.stateUpdate.hashState,
            appointment.stateUpdate.contractAddress,
            appointment.stateUpdate.round,
            participants,
            appointment.stateUpdate.signatures
        );
        logger.info("All participants have signed.");

        // check that the supplied state round is valid
        const channelRound: number = await contract.bestRound();
        logger.info(`Round at ${contract.address}: ${channelRound.toString(10)}`);
        if (channelRound >= appointment.stateUpdate.round) {
            throw new Error(
                `Supplied appointment round ${
                    appointment.stateUpdate.round
                } is not greater than channel round ${channelRound}`
            );
        }

        // check that the channel is not in a dispute
        const channelDisputePeriod: number = await contract.disputePeriod();
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

        const channelStatus: number = await contract.status();
        logger.info(`Channel status at ${contract.address}: ${JSON.stringify(channelStatus)}`);
        // ON = 0, DISPUTE = 1, OFF = 2
        // TODO: better logging: ON, OFF, etc
        if (channelStatus != 0) {
            // TODO: we actually just need to check that the status is not "dispute"
            throw new Error(`Channel status is ${channelStatus} not 0.`);
        }
    }

    // TODO: this doesnt belong in this class
    public createAppointment(request: IAppointmentRequest): IAppointment {
        const startTime = Date.now();

        return {
            stateUpdate: request.stateUpdate,
            startTime: startTime,
            endTime: startTime + request.expiryPeriod
        };
    }

    private checkAllSigned(
        hashState: string,
        channelAddress: string,
        round: number,
        participants: string[],
        sigs: string[]
    ) {
        if (participants.length !== sigs.length) {
            throw new Error(
                `Incorrect number of signatures supplied. Participants: ${participants.length}, signers: ${sigs.length}`
            );
        }

        // form the hash
        const setStateHash = KitsuneTools.hashForSetState(hashState, round, channelAddress);
        const signers = sigs.map(sig => verifyMessage(ethers.utils.arrayify(setStateHash), sig));
        participants.forEach(party => {
            const signerIndex = signers.map(m => m.toLowerCase()).indexOf(party.toLowerCase());
            if (signerIndex === -1) throw new Error(`Party ${party} not present in signatures.`);

            // remove the signer, so that we never look for it again
            signers.splice(signerIndex, 1);
        });
    }
}

//QUESTION: is there preference over offchain message being signed with the Ethereum Signed Message - currently necessary for web3 users
//QUESTION: do L4 use block.number or block.timestamp
