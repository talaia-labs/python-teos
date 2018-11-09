import { solidityKeccak256 } from "ethers/utils";
import { IAppointment } from "./dataEntities/appointment";
import { ethers } from "ethers";

// TODO: this class...

export class KitsuneTools {
    public static hashForSetState(hState: string, round: number, channelAddress: string) {
        return solidityKeccak256(["bytes32", "uint256", "address"], [hState, round, channelAddress]);
    }

    public static disputeEvent = "EventDispute(uint256)";
    public static async respond(contract: ethers.Contract, appointment: IAppointment) {
        let sig0 = ethers.utils.splitSignature(appointment.stateUpdate.signatures[0]);
        let sig1 = ethers.utils.splitSignature(appointment.stateUpdate.signatures[1]);

        // TODO: order the sigs dont expect them to be in a correct order - or do, explicitly
        const tx = await contract.setstate(
            [sig0.v - 27, sig0.r, sig0.s, sig1.v - 27, sig1.r, sig1.s],
            appointment.stateUpdate.round,
            appointment.stateUpdate.hashState
        );
        return await tx.wait();
    }

    public static async participants(contract: ethers.Contract) {
        return [await contract.plist(0), await contract.plist(1)] as string[];
    }

    public static async round(contract: ethers.Contract) {
        return await contract.bestRound();
    }

    public static async disputePeriod(contract: ethers.Contract) {
        return await contract.disputePeriod();
    }

    public static async status(contract: ethers.Contract) {
        return await contract.status();
    }
}
