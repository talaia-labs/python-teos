import { solidityKeccak256 } from "ethers/utils";
import { IAppointment } from "./dataEntities/appointment";
import { Contract, utils } from "ethers";
const StateChannel = require("../statechannels/build/contracts/StateChannel.json");


/**
 * A library of the Kitsune specific functionality
 */
export class KitsuneTools {
    public static hashForSetState(hState: string, round: number, channelAddress: string) {
        return solidityKeccak256(["bytes32", "uint256", "address"], [hState, round, channelAddress]);
    }

    public static disputeEvent = "EventDispute(uint256)";
    public static async respond(contract: Contract, appointment: IAppointment) {
        let sig0 = utils.splitSignature(appointment.stateUpdate.signatures[0]);
        let sig1 = utils.splitSignature(appointment.stateUpdate.signatures[1]);

        const tx = await contract.setstate(
            [sig0.v - 27, sig0.r, sig0.s, sig1.v - 27, sig1.r, sig1.s],
            appointment.stateUpdate.round,
            appointment.stateUpdate.hashState
        );
        return await tx.wait();
    }

    public static async participants(contract: Contract) {
        return [await contract.plist(0), await contract.plist(1)] as string[];
    }

    public static async round(contract: Contract) {
        return await contract.bestRound();
    }

    public static async disputePeriod(contract: Contract) {
        return await contract.disputePeriod();
    }

    public static async status(contract: Contract) {
        return await contract.status();
    }

    public static ContractBytecode = StateChannel.bytecode;
    public static ContractDeployedBytecode = StateChannel.deployedBytecode;
    public static ContractAbi = StateChannel.abi;
}
