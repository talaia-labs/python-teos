import Web3Util from "web3-utils";
import { IShip } from "./../entities/gameEntities";

// TODO: these are quick ports from js and should be better typed / OOP'd
// TODO: all over the place we have reference to contractAddress / gameAddress / battshipContract.address, we should be consistent

export const committedShips = (
    contractAddress: string,
    sizes: number[],
    ships: string[],
    round: number,
    player: string
) => {
    const commitment: string = Web3Util.soliditySha3(
        { t: "uint[]", v: sizes },
        { t: "bytes32[]", v: ships },
        { t: "address", v: player },
        { t: "uint", v: round },
        { t: "address", v: contractAddress }
    );

    return {
        sizes,
        ships,
        player,
        round: round,
        gameAddress: contractAddress,
        commitment
    };
};

export const committedShip = (
    id: string,
    size: number,
    x1: number,
    y1: number,
    x2: number,
    y2: number,
    r: number,
    player: string,
    round: number,
    gameAddress: string
): IShip => {
    // ship is commitment to...
    // x1, y1, x2, y2, random, player, game round, contract address(this)
    const commitment = Web3Util.soliditySha3(
        { t: "uint8", v: x1 },
        { t: "uint8", v: y1 },
        { t: "uint8", v: x2 },
        { t: "uint8", v: y2 },
        { t: "uint", v: r },
        { t: "address", v: player },
        { t: "uint", v: round },
        { t: "address", v: gameAddress }
    );

    return {
        id,
        size,
        x1,
        y1,
        x2,
        y2,
        r,
        player,
        round,
        gameAddress,
        commitment,
        hits: 0
    };
};