import { solidityKeccak256 } from "ethers/utils";
import { IAppointment } from "./dataEntities/appointment";
import { Contract, utils } from "ethers";
import logger from "./logger";
const StateChannel = require("../statechannels/build/contracts/StateChannel.json");

// quick wait
const wait = (timeout: number) => {
    return new Promise((resolve, reject) => {
        setTimeout(() => {
            resolve();
        }, timeout);
    });
};

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

        try {
            logger.debug("a1");

            let trying = true;
            let tries = 0;
            let tx;
            while (trying && tries < 10) {
                try {
                    tx = await contract.setstate(
                        [sig0.v - 27, sig0.r, sig0.s, sig1.v - 27, sig1.r, sig1.s],
                        appointment.stateUpdate.round,
                        appointment.stateUpdate.hashState
                    );
                    trying = false;
                } catch (exe) {
                    // lets retry this hard until we can no longer
                    logger.error(`Failed to set state for contract ${contract.address}, re-tries ${tries}`)
                    tries++;
                    await wait(1000);
                }
            }

            if(trying) throw new Error("Failed after 10 tries.")
            else {
                logger.info(`success after ${tries} tries.`)
            }
            return await tx.wait();
        } catch (soh) {
            logger.error(soh);
            throw soh;
        }
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
