import { committedShip } from "./shipTools";

// TODO: this was quickly ported from js, requires better typing

export class BoardBuilder {
    private static readonly shipSizes = [5, 4, 3, 3, 2];
    private static readonly alphabet = "abcde";
    private static readonly random = 66;

    static constructBasicShips(contractAddress: string, player: string, round: number) {
        const createArray = <T1>(size: number, elementCreator: () => T1): Array<T1> =>
            Array.apply(null, Array(size)).map(elementCreator);
        const createEmptyBoard = () => createArray(10, () => createArray<string>(10, () => "0"));

        const emptyBoard = createEmptyBoard();

        const ships = this.shipSizes.map((element, index) => {
            const id = this.alphabet[index];
            const size = element;
            const x1 = index;
            const y1 = 0;
            const x2 = index;
            const y2 = element - 1;

            this.addShipToBoard(id, x1, y1, x2, y2, emptyBoard);

            return committedShip(id, size, x1, y1, x2, y2, this.random, player, round, contractAddress);
        });

        return { ships, board: emptyBoard };
    }

    private static addShipToBoard(id, x1, y1, x2, y2, board) {
        for (let i = x1; i <= x2; i++) {
            for (let j = y1; j <= y2; j++) {
                board[i][j] = id;
            }
        }
    }
}
