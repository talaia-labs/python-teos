import { IAppointment } from "./dataEntities/appointment";
const StateChannel = require("./external/statechannels/build/contracts/StateChannel.json");
import { ethers } from "ethers";

// TODO: better name for this
interface IRegisteredAppointment {
    appointment: IAppointment;
    contract: ethers.Contract;
}

// TODO: in here and in the inspector refuse to accept multiple requests for the same job?
// TODO: initially yes

export class Watcher {
    private readonly disputeEventName = "EventDispute(uint256)";
    private readonly disputeEventCallback: ethers.providers.Listener = (deadline, eventInfo) => {
        return this.respondToDispute(eventInfo);
    }
    // TODO: this class is not thread safe, and we should have readonly here
    private readonly appointments: IRegisteredAppointment[] = [];
    constructor(private readonly provider: ethers.providers.BaseProvider, private readonly signer: ethers.Signer) {}

    async addAppointment(appointment: IAppointment) {
        // add this appointment to the watch list
        // TODO: safety check the appointment

        // TODO: the time constraints

        // create a contract for this appointment
        const contract = new ethers.Contract(
            appointment.stateUpdate.contractAddress,
            StateChannel.abi,
            this.provider
        ).connect(this.signer);
        // register a callback for the supplied event
        contract.on(this.disputeEventName, this.disputeEventCallback);

        // store the appointments for later
        this.appointments.push({
            appointment,
            contract
        });
    }

    public async respondToDispute(event) {
        // TODO: lock this, it shouldnt be triggered concurrently for the same subscription
        // TODO: we lack error handling throughout
        // TODO: require detailed tracing for all actions

        // TODO: if we have multiple watchers for the same job we need to not submit multiple transactions

        // respond by calling setstate
        // 1. find the appointment
        const appointment = this.appointments.filter(
            a => a.appointment.stateUpdate.contractAddress === event.address
        )[0];
        // TODO: unsafe array access?

        if (!appointment) {
            // the appointment couldnt be found, this should never happen,
            // subscription should always be removed before the appointment
            throw new Error(`Missing appointment for contract ${event.address}`);
        }

        // TODO: 2. check that the dispute was triggered within the correct time period

        // TODO: 3. Check that we still have time to respond - if not then we're in trouble, deposit will be lost
        let sig0 = ethers.utils.splitSignature(appointment.appointment.stateUpdate.signatures[0]);
        let sig1 = ethers.utils.splitSignature(appointment.appointment.stateUpdate.signatures[0]);
        // TODO: order the sigs dont expect them to be in a correct order - or do, explicitly
        const tx = await appointment.contract.setstate(
            [sig0.v - 27, sig0.r, sig0.s, sig1.v - 27, sig1.r, sig1.s],
            appointment.appointment.stateUpdate.round,
            appointment.appointment.stateUpdate.hashState
        );
        await tx.wait();

        // remove subscription - we've satisfied our claim
        appointment.contract.removeListener(this.disputeEventName, this.disputeEventCallback);

        // remove the appoitment from the array
        this.appointments.splice(this.appointments.indexOf(appointment), 1);
    }
}