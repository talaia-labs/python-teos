import { soliditySha3 } from "web3x/utils";
import { solidityKeccak256 } from "ethers/utils";

export class KitsuneTools {
    // TODO: dont need to inject web3 here? not with web3x
    // TODO: remove web3x
    public static hashForSetState(hState: string, round: number, channelAddress: string) {
        return solidityKeccak256(
            [
                "bytes32", "uint256", "address"
            ], [
                hState, round, channelAddress
            ]
        )
        return soliditySha3(
            { t: "bytes32", v: hState },
            { t: "uint256", v: round },
            { t: "address", v: channelAddress }
        )
    }
}
