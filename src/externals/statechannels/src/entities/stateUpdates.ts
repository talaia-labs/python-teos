import { Contract } from "web3-eth-contract";
import { Reveal } from "./gameEntities";
import Web3Util from "web3-utils";
import { Action } from "./../action/rootAction";

export interface IStateUpdate {
    name: string;
    stateRound: number;
    serialiseData();
    hashData(moveCtr: number, round: number, contractAddress: string);
    // TODO: nullable to support transaction style state updates
    getFunction(contract: Contract, sig?: string);
}

export interface IProposeStateUpdate extends IStateUpdate {
    storeUpdateAction(
        stateUpdate: string,
        stateUpdateSig: string,
        moveCtr: number,
        round: number,
        onChainDataSig: string
    );
    createVerifyStateUpdate(
        offChainTransaction: string,
        onChainDataSig: string,
        offChainDatasig: string,
        stateUpdateSig: string
    );
}

export interface IVerifyStateUpdate extends IStateUpdate {
    onChainDataSig: string;
    offChainDataSig: string;
    stateUpdateSig: string;
    offChainTransaction: any;

    storeUpdateAction(
        stateUpdate: string,
        stateUpdateSig: string,
        moveCtr: number,
        round: number,
        onChainDataSig: string
    );
    createAcknowledgeStateUpdate(stateUpdateSig: string);
}

export interface IAcknowledgeStateUpdate extends IStateUpdate {
    stateUpdateSig: string;
    // TODO: these args are all wrong
    storeUpdateAction(stateUpdate: string, stateUpdateSig: string, moveCtr: number, round: number);
}

class RevealSlotStateUpdate implements IStateUpdate {
    public name = "revealslot";
    constructor(
        public readonly reveal: Reveal,
        public readonly x: number,
        public readonly y: number,
        public readonly stateRound: number
    ) {}

    private static revealToString(reveal: Reveal) {
        switch (reveal) {
            case Reveal.Hit:
                return "hit";
            case Reveal.Miss:
                return "miss";
            case Reveal.Sink:
                return "sink";
            default:
                throw new Error("Unrecognised reveal " + reveal);
        }
    }

    serialiseData() {
        return `${RevealSlotStateUpdate.revealToString(this.reveal)}-${this.x},${this.y}`;
    }

    hashData(moveCtr: number, round: number, contractAddress: string) {
        return Web3Util.soliditySha3(
            { t: "uint8", v: this.x },
            { t: "uint8", v: this.y },
            { t: "bool", v: this.reveal === Reveal.Hit ? true : false },
            { t: "uint", v: moveCtr },
            { t: "uint", v: round },
            { t: "address", v: contractAddress }
        );
    }

    getFunction(contract: Contract, sig: string) {
        return contract.methods[this.name](this.reveal === Reveal.Hit, sig);
    }
}

export class RevealSlotProposeStateUpdate extends RevealSlotStateUpdate implements IProposeStateUpdate {
    constructor(
        public readonly reveal: Reveal,
        public readonly x: number,
        public readonly y: number,
        public readonly stateRound: number
    ) {
        super(reveal, x, y, stateRound);
    }

    createVerifyStateUpdate(
        offChainTransaction: string,
        onChainDataSig: string,
        offChainDatasig: string,
        stateUpdateSig: string
    ) {
        return new RevealSlotVerifyStateUpdate(
            this.reveal,
            this.x,
            this.y,
            offChainTransaction,
            onChainDataSig,
            offChainDatasig,
            stateUpdateSig,
            this.stateRound
        );
    }

    storeUpdateAction(
        stateUpdate: string,
        stateUpdateSig: string,
        moveCtr: number,
        round: number,
        onChainDataSig: string
    ) {
        return Action.moveCreate({
            // TODO: hack - should be this or reveal sig - depending on the move
            reveal: this.reveal,
            moveSig: onChainDataSig,
            channelSig: stateUpdateSig,
            hashState: stateUpdate,
            moveCtr: moveCtr,
            round: round,
            x: this.x,
            y: this.y
        });
    }
}

export class RevealSlotVerifyStateUpdate extends RevealSlotStateUpdate implements IVerifyStateUpdate {
    constructor(
        public readonly reveal: Reveal,
        public readonly x: number,
        public readonly y: number,
        public readonly offChainTransaction: any,
        public readonly onChainDataSig: string,
        public readonly offChainDataSig: string,
        public readonly stateUpdateSig: string,
        public readonly stateRound: number
    ) {
        super(reveal, x, y, stateRound);
    }

    storeUpdateAction(
        stateUpdate: string,
        stateUpdateSig: string,
        moveCtr: number,
        round: number,
        onChainDataSig: string
    ) {
        return Action.moveCreate({
            // TODO: hack - should be this or reveal sig - depending on the move
            reveal: this.reveal,
            moveSig: onChainDataSig,
            channelSig: stateUpdateSig,
            hashState: stateUpdate,
            moveCtr: moveCtr,
            round: round,
            x: this.x,
            y: this.y
        });
    }

    createAcknowledgeStateUpdate(stateUpdateSig: string) {
        return new RevealSlotAcknowledgeStateUpdate(this.reveal, this.x, this.y, stateUpdateSig, this.stateRound);
    }
}

export class RevealSlotAcknowledgeStateUpdate extends RevealSlotStateUpdate implements IAcknowledgeStateUpdate {
    constructor(
        public readonly reveal: Reveal,
        public readonly x: number,
        public readonly y: number,
        public readonly stateUpdateSig: string,
        public readonly stateRound: number
    ) {
        super(reveal, x, y, stateRound);
    }

    storeUpdateAction(stateUpdate: string, stateUpdateSig: string, moveCtr: number, round: number) {
        // TODO: add the channel sig for the latest move
    }
}

class RevealSunkStateUpdate implements IStateUpdate {
    public name = "revealsunk";
    constructor(
        public readonly x: number,
        public readonly y: number,
        public readonly x1: number,
        public readonly y1: number,
        public readonly x2: number,
        public readonly y2: number,
        public readonly r: number,
        public readonly shipIndex: number,
        public readonly stateRound: number
    ) {}

    serialiseData() {
        return `sink-${this.x},${this.y}`;
    }

    hashData(moveCtr: number, round: number, contractAddress: string) {
        return Web3Util.soliditySha3(
            { t: "uint8", v: this.x1 },
            { t: "uint8", v: this.y1 },
            { t: "uint8", v: this.x2 },
            { t: "uint8", v: this.y2 },
            { t: "uint", v: this.r },
            { t: "uint", v: this.shipIndex },
            { t: "uint", v: moveCtr },
            { t: "uint", v: round },
            { t: "address", v: contractAddress }
        );
    }

    getFunction(contract: Contract, sig: string) {
        return contract.methods[this.name](this.shipIndex, this.x1, this.y1, this.x2, this.y2, this.r, sig);
    }
}

export class RevealSunkProposeStateUpdate extends RevealSunkStateUpdate implements IProposeStateUpdate {
    constructor(
        public readonly x: number,
        public readonly y: number,
        public readonly x1: number,
        public readonly y1: number,
        public readonly x2: number,
        public readonly y2: number,
        public readonly r: number,
        public readonly shipIndex: number,
        public readonly stateRound: number
    ) {
        super(x, y, x1, y1, x2, y2, r, shipIndex, stateRound);
    }

    createVerifyStateUpdate(
        offChainTransaction: any,
        onChainDataSig: string,
        offChainDatasig: string,
        stateUpdateSig: string
    ) {
        return new RevealSunkVerifyStateUpdate(
            this.x,
            this.y,
            this.x1,
            this.y1,
            this.x2,
            this.y2,
            this.r,
            this.shipIndex,
            this.stateRound,
            offChainTransaction,
            onChainDataSig,
            offChainDatasig,
            stateUpdateSig
        );
    }

    storeUpdateAction(
        stateUpdate: string,
        stateUpdateSig: string,
        moveCtr: number,
        round: number,
        onChainDataSig: string
    ) {
        return Action.moveCreate({
            // TODO: hack - should be this or reveal sunk - depending on the move
            reveal: Reveal.Sink,
            moveSig: onChainDataSig,
            channelSig: stateUpdateSig,
            hashState: stateUpdate,
            moveCtr: moveCtr,
            round: round,
            x: this.x,
            y: this.y
        });
    }
}

export class RevealSunkVerifyStateUpdate extends RevealSunkStateUpdate implements IVerifyStateUpdate {
    constructor(
        public readonly x: number,
        public readonly y: number,
        public readonly x1: number,
        public readonly y1: number,
        public readonly x2: number,
        public readonly y2: number,
        public readonly r: number,
        public readonly shipIndex: number,
        public readonly stateRound: number,
        public readonly offChainTransaction: any,
        public readonly onChainDataSig: string,
        public readonly offChainDataSig: string,
        public readonly stateUpdateSig: string
    ) {
        super(x, y, x1, y1, x2, y2, r, shipIndex, stateRound);
    }

    storeUpdateAction(
        stateUpdate: string,
        stateUpdateSig: string,
        moveCtr: number,
        round: number,
        onChainDataSig: string
    ) {
        return Action.moveCreate({
            reveal: Reveal.Sink,
            moveSig: onChainDataSig,
            channelSig: stateUpdateSig,
            hashState: stateUpdate,
            moveCtr: moveCtr,
            round: round,
            x: this.x,
            y: this.y
        });
    }

    createAcknowledgeStateUpdate(stateUpdateSig: string) {
        return new RevealSunkAcknowledgeStateUpdate(
            this.x,
            this.y,
            this.x1,
            this.y1,
            this.x2,
            this.y2,
            this.r,
            this.shipIndex,
            stateUpdateSig,
            this.stateRound
        );
    }
}

export class RevealSunkAcknowledgeStateUpdate extends RevealSunkStateUpdate implements IAcknowledgeStateUpdate {
    constructor(
        public readonly x: number,
        public readonly y: number,
        public readonly x1: number,
        public readonly y1: number,
        public readonly x2: number,
        public readonly y2: number,
        public readonly r: number,
        public readonly shipIndex: number,
        public readonly stateUpdateSig: string,
        public readonly stateRound: number
    ) {
        super(x, y, x1, y1, x2, y2, r, shipIndex, stateRound);
    }

    storeUpdateAction(stateUpdate: string, stateUpdateSig: string, moveCtr: number, round: number) {
        // TODO: add the channel sig for the latest move
    }
}

class AttackStateUpdate implements IStateUpdate {
    public name = "attack";
    constructor(public readonly x: number, public readonly y: number, public readonly stateRound: number) {}

    serialiseData() {
        return `attack-${this.x},${this.y}`;
    }

    hashData(moveCtr: number, round: number, contractAddress: string) {
        return Web3Util.soliditySha3(
            { t: "uint8", v: this.x },
            { t: "uint8", v: this.y },
            { t: "uint", v: moveCtr },
            { t: "uint", v: round },
            { t: "address", v: contractAddress }
        );
    }

    getFunction(contract: Contract, sig: string) {
        return contract.methods[this.name](this.x, this.y, sig);
    }
}

export class AttackProposeStateUpdate extends AttackStateUpdate implements IProposeStateUpdate {
    constructor(public readonly x: number, public readonly y: number, public readonly stateRound: number) {
        super(x, y, stateRound);
    }

    createVerifyStateUpdate(
        offChainTransaction: any,
        onChainDataSig: string,
        offChainDatasig: string,
        stateUpdateSig: string
    ) {
        return new AttackVerifyStateUpdate(
            this.x,
            this.y,
            this.stateRound,
            offChainTransaction,
            onChainDataSig,
            offChainDatasig,
            stateUpdateSig
        );
    }

    storeUpdateAction(
        stateUpdate: string,
        stateUpdateSig: string,
        moveCtr: number,
        round: number,
        onChainDataSig: string
    ) {
        return Action.moveCreate({
            // TODO: hack - should be this or reveal sunk - depending on the move
            //reveal: this.reveal,
            moveSig: onChainDataSig,
            channelSig: stateUpdateSig,
            hashState: stateUpdate,
            moveCtr: moveCtr,
            round: round,
            x: this.x,
            y: this.y
        });
    }
}

export class AttackVerifyStateUpdate extends AttackStateUpdate implements IVerifyStateUpdate {
    constructor(
        public readonly x: number,
        public readonly y: number,
        public readonly stateRound: number,
        public readonly offChainTransaction: any,
        public readonly onChainDataSig: string,
        public readonly offChainDataSig: string,
        public readonly stateUpdateSig: string
    ) {
        super(x, y, stateRound);
    }

    storeUpdateAction(
        stateUpdate: string,
        stateUpdateSig: string,
        moveCtr: number,
        round: number,
        onChainDataSig: string
    ) {
        return Action.moveCreate({
            // TODO: hack - should be this or reveal sig - depending on the move
            //reveal: this.reveal,
            moveSig: onChainDataSig,
            channelSig: stateUpdateSig,
            hashState: stateUpdate,
            moveCtr: moveCtr,
            round: round,
            x: this.x,
            y: this.y
        });
    }

    createAcknowledgeStateUpdate(stateUpdateSig: string) {
        return new AttackAcknowledgeStateUpdate(this.x, this.y, stateUpdateSig, this.stateRound);
    }
}

export class AttackAcknowledgeStateUpdate extends AttackStateUpdate implements IAcknowledgeStateUpdate {
    constructor(
        public readonly x: number,
        public readonly y: number,
        public readonly stateUpdateSig: string,
        public readonly stateRound: number
    ) {
        super(x, y, stateRound);
    }

    storeUpdateAction(stateUpdate: string, stateUpdateSig: string, moveCtr: number, round: number) {
        // TODO: add the channel sig for the latest move
    }
}

class OpenShipsStateUpdate implements IStateUpdate {
    public name = "openships";
    constructor(
        public readonly x1: number[],
        public readonly y1: number[],
        public readonly x2: number[],
        public readonly y2: number[],
        public readonly r: number[],
        public readonly stateRound: number
    ) {}

    serialiseData() {
        const reducer = (a: string, b: number) => a + "-" + b.toString();
        return `attack-{${this.x1.reduce(reducer, "")}},{${this.y1.reduce(reducer, "")}},{${this.x2.reduce(
            reducer,
            ""
        )}},{${this.y2.reduce(reducer, "")}}`;
    }

    hashData(moveCtr: number, round: number, contractAddress: string) {
        // TODO: remove this - not necessary
        return Web3Util.soliditySha3({ t: "uint8[]", v: this.x1 });
    }

    // TODO: useless sig
    getFunction(contract: Contract, sig: string) {
        return contract.methods[this.name](this.x1, this.y1, this.x2, this.y2, this.r);
    }
}

export class OpenShipsProposeStateUpdate extends OpenShipsStateUpdate implements IProposeStateUpdate {
    constructor(
        public readonly x1: number[],
        public readonly y1: number[],
        public readonly x2: number[],
        public readonly y2: number[],
        public readonly r: number[],
        public readonly stateRound: number
    ) {
        super(x1, y1, x2, y2, r, stateRound);
    }

    createVerifyStateUpdate(
        offChainTransaction: any,
        onChainDataSig: string,
        offChainDatasig: string,
        stateUpdateSig: string
    ) {
        return new OpenShipsVerifyStateUpdate(
            this.x1,
            this.y1,
            this.x2,
            this.y2,
            this.r,
            this.stateRound,
            offChainTransaction,
            onChainDataSig,
            offChainDatasig,
            stateUpdateSig
        );
    }

    storeUpdateAction(
        stateUpdate: string,
        stateUpdateSig: string,
        moveCtr: number,
        round: number,
        onChainDataSig: string
    ) {
        // TODO: do nothing:
    }
}

export class OpenShipsVerifyStateUpdate extends OpenShipsStateUpdate implements IVerifyStateUpdate {
    constructor(
        public readonly x1: number[],
        public readonly y1: number[],
        public readonly x2: number[],
        public readonly y2: number[],
        public readonly r: number[],
        public readonly stateRound: number,
        public readonly offChainTransaction: any,
        public readonly onChainDataSig: string,
        public readonly offChainDataSig: string,
        public readonly stateUpdateSig: string
    ) {
        super(x1, y1, x2, y2, r, stateRound);
    }

    storeUpdateAction(
        stateUpdate: string,
        stateUpdateSig: string,
        moveCtr: number,
        round: number,
        onChainDataSig: string
    ) {
        // TODO: do nothing
    }

    createAcknowledgeStateUpdate(stateUpdateSig: string) {
        return new OpenShipsAcknowledgeStateUpdate(
            this.x1,
            this.y1,
            this.x2,
            this.y2,
            this.r,
            stateUpdateSig,
            this.stateRound
        );
    }
}

export class OpenShipsAcknowledgeStateUpdate extends OpenShipsStateUpdate implements IAcknowledgeStateUpdate {
    constructor(
        public readonly x1: number[],
        public readonly y1: number[],
        public readonly x2: number[],
        public readonly y2: number[],
        public readonly r: number[],
        public readonly stateUpdateSig: string,
        public readonly stateRound: number
    ) {
        super(x1, y1, x2, y2, r, stateRound);
    }

    storeUpdateAction(stateUpdate: string, stateUpdateSig: string, moveCtr: number, round: number) {
        // TODO: add the channel sig for the latest move
    }
}

class FinishGameStateUpdate implements IStateUpdate {
    public name = "finishGame";
    constructor(public readonly stateRound: number) {}

    serialiseData() {
        return "finishGame";
    }

    hashData(moveCtr: number, round: number, contractAddress: string) {
        // TODO: remove this - not necessary
        return Web3Util.soliditySha3({ t: "uint8", v: 0 });
    }

    // TODO: useless sig
    getFunction(contract: Contract, sig: string) {
        return contract.methods[this.name]();
    }
}

export class FinishGameProposeStateUpdate extends FinishGameStateUpdate implements IProposeStateUpdate {
    constructor(public readonly stateRound: number) {
        super(stateRound);
    }

    createVerifyStateUpdate(
        offChainTransaction: any,
        onChainDataSig: string,
        offChainDatasig: string,
        stateUpdateSig: string
    ) {
        return new FinishGameVerifyStateUpdate(
            this.stateRound,
            offChainTransaction,
            onChainDataSig,
            offChainDatasig,
            stateUpdateSig
        );
    }

    storeUpdateAction(
        stateUpdate: string,
        stateUpdateSig: string,
        moveCtr: number,
        round: number,
        onChainDataSig: string
    ) {
        // TODO: do nothing:
    }
}

export class FinishGameVerifyStateUpdate extends FinishGameStateUpdate implements IVerifyStateUpdate {
    constructor(
        public readonly stateRound: number,
        public readonly offChainTransaction: any,
        public readonly onChainDataSig: string,
        public readonly offChainDataSig: string,
        public readonly stateUpdateSig: string
    ) {
        super(stateRound);
    }

    storeUpdateAction(
        stateUpdate: string,
        stateUpdateSig: string,
        moveCtr: number,
        round: number,
        onChainDataSig: string
    ) {
        // TODO: do nothing
    }

    createAcknowledgeStateUpdate(stateUpdateSig: string) {
        return new FinishGameAcknowledgeStateUpdate(stateUpdateSig, this.stateRound);
    }
}

export class FinishGameAcknowledgeStateUpdate extends FinishGameStateUpdate implements IAcknowledgeStateUpdate {
    constructor(public readonly stateUpdateSig: string, public readonly stateRound: number) {
        super(stateRound);
    }

    storeUpdateAction(stateUpdate: string, stateUpdateSig: string, moveCtr: number, round: number) {
        // TODO: add the channel sig for the latest move
    }
}

class PlaceBetStateUpdate implements IStateUpdate {
    public name = "placeBet";
    constructor(public readonly bet: number, public readonly stateRound: number) {}

    serialiseData() {
        return "placeBet";
    }

    hashData(moveCtr: number, round: number, contractAddress: string) {
        // TODO: remove this - not necessary
        return Web3Util.soliditySha3({ t: "uint8", v: 1 });
    }

    // TODO: useless sig
    getFunction(contract: Contract, sig: string) {
        return contract.methods[this.name](this.bet);
    }
}

export class PlaceBetProposeStateUpdate extends PlaceBetStateUpdate implements IProposeStateUpdate {
    constructor(public readonly bet: number, public readonly stateRound: number) {
        super(bet, stateRound);
    }

    createVerifyStateUpdate(
        offChainTransaction: any,
        onChainDataSig: string,
        offChainDatasig: string,
        stateUpdateSig: string
    ) {
        return new PlaceBetVerifyStateUpdate(
            this.bet,
            this.stateRound,
            offChainTransaction,
            onChainDataSig,
            offChainDatasig,
            stateUpdateSig
        );
    }

    storeUpdateAction(
        stateUpdate: string,
        stateUpdateSig: string,
        moveCtr: number,
        round: number,
        onChainDataSig: string
    ) {
        // TODO: do nothing:
    }
}

export class PlaceBetVerifyStateUpdate extends PlaceBetStateUpdate implements IVerifyStateUpdate {
    constructor(
        public readonly bet: number,
        public readonly stateRound: number,
        public readonly offChainTransaction: any,
        public readonly onChainDataSig: string,
        public readonly offChainDataSig: string,
        public readonly stateUpdateSig: string
    ) {
        super(bet, stateRound);
    }

    storeUpdateAction(
        stateUpdate: string,
        stateUpdateSig: string,
        moveCtr: number,
        round: number,
        onChainDataSig: string
    ) {
        // TODO: do nothing
    }

    createAcknowledgeStateUpdate(stateUpdateSig: string) {
        return new PlaceBetAcknowledgeStateUpdate(this.bet, stateUpdateSig, this.stateRound);
    }
}

export class PlaceBetAcknowledgeStateUpdate extends PlaceBetStateUpdate implements IAcknowledgeStateUpdate {
    constructor(
        public readonly bet: number,
        public readonly stateUpdateSig: string,
        public readonly stateRound: number
    ) {
        super(bet, stateRound);
    }

    storeUpdateAction(stateUpdate: string, stateUpdateSig: string, moveCtr: number, round: number) {
        // TODO: add the channel sig for the latest move
    }
}

class StoreShipsStateUpdate implements IStateUpdate {
    public name = "storeShips";
    constructor(
        public readonly sizes: number[],
        public readonly ships: string[],
        public readonly signature: string,
        public readonly stateRound: number
    ) {}

    serialiseData() {
        return "storeShips";
    }

    hashData(moveCtr: number, round: number, contractAddress: string) {
        // TODO: remove this - not necessary
        return Web3Util.soliditySha3({ t: "uint8", v: 1 });
    }

    // TODO: useless sig
    getFunction(contract: Contract, sig: string) {
        return contract.methods[this.name](this.sizes, this.ships, this.signature);
    }
}

export class StoreShipsProposeStateUpdate extends StoreShipsStateUpdate implements IProposeStateUpdate {
    constructor(
        public readonly sizes: number[],
        public readonly ships: string[],
        public readonly signature: string,
        public readonly stateRound: number
    ) {
        super(sizes, ships, signature, stateRound);
    }

    createVerifyStateUpdate(
        offChainTransaction: any,
        onChainDataSig: string,
        offChainDatasig: string,
        stateUpdateSig: string
    ) {
        return new StoreShipsVerifyStateUpdate(
            this.sizes,
            this.ships,
            this.signature,
            this.stateRound,
            offChainTransaction,
            onChainDataSig,
            offChainDatasig,
            stateUpdateSig
        );
    }

    storeUpdateAction(
        stateUpdate: string,
        stateUpdateSig: string,
        moveCtr: number,
        round: number,
        onChainDataSig: string
    ) {
        // TODO: do nothing:
    }
}

export class StoreShipsVerifyStateUpdate extends StoreShipsStateUpdate implements IVerifyStateUpdate {
    constructor(
        public readonly sizes: number[],
        public readonly ships: string[],
        public readonly signature: string,
        public readonly stateRound: number,
        public readonly offChainTransaction: any,
        public readonly onChainDataSig: string,
        public readonly offChainDataSig: string,
        public readonly stateUpdateSig: string
    ) {
        super(sizes, ships, signature, stateRound);
    }

    storeUpdateAction(
        stateUpdate: string,
        stateUpdateSig: string,
        moveCtr: number,
        round: number,
        onChainDataSig: string
    ) {
        // TODO: do nothing
    }

    createAcknowledgeStateUpdate(stateUpdateSig: string) {
        return new StoreShipsAcknowledgeStateUpdate(
            this.sizes,
            this.ships,
            this.signature,
            stateUpdateSig,
            this.stateRound
        );
    }
}

export class StoreShipsAcknowledgeStateUpdate extends StoreShipsStateUpdate implements IAcknowledgeStateUpdate {
    constructor(
        public readonly sizes: number[],
        public readonly ships: string[],
        public readonly signature: string,
        public readonly stateUpdateSig: string,
        public readonly stateRound: number
    ) {
        super(sizes, ships, signature, stateRound);
    }

    storeUpdateAction(stateUpdate: string, stateUpdateSig: string, moveCtr: number, round: number) {
        // TODO: add the channel sig for the latest move
    }
}

class ReadyToPlayStateUpdate implements IStateUpdate {
    public name = "readyToPlay";
    constructor(public readonly stateRound: number) {}

    serialiseData() {
        return "readyToPlay";
    }

    hashData(moveCtr: number, round: number, contractAddress: string) {
        // TODO: remove this - not necessary
        return Web3Util.soliditySha3({ t: "uint8", v: 2 });
    }

    // TODO: useless sig
    getFunction(contract: Contract, sig: string) {
        return contract.methods[this.name]();
    }
}

export class ReadyToPlayProposeStateUpdate extends ReadyToPlayStateUpdate implements IProposeStateUpdate {
    constructor(public readonly stateRound: number) {
        super(stateRound);
    }

    createVerifyStateUpdate(
        offChainTransaction: any,
        onChainDataSig: string,
        offChainDatasig: string,
        stateUpdateSig: string
    ) {
        return new ReadyToPlayVerifyStateUpdate(
            this.stateRound,
            offChainTransaction,
            onChainDataSig,
            offChainDatasig,
            stateUpdateSig
        );
    }

    storeUpdateAction(
        stateUpdate: string,
        stateUpdateSig: string,
        moveCtr: number,
        round: number,
        onChainDataSig: string
    ) {
        // TODO: do nothing:
    }
}

export class ReadyToPlayVerifyStateUpdate extends ReadyToPlayStateUpdate implements IVerifyStateUpdate {
    constructor(
        public readonly stateRound: number,
        public readonly offChainTransaction: any,
        public readonly onChainDataSig: string,
        public readonly offChainDataSig: string,
        public readonly stateUpdateSig: string
    ) {
        super(stateRound);
    }

    storeUpdateAction(
        stateUpdate: string,
        stateUpdateSig: string,
        moveCtr: number,
        round: number,
        onChainDataSig: string
    ) {
        // TODO: do nothing
    }

    createAcknowledgeStateUpdate(stateUpdateSig: string) {
        return new ReadyToPlayAcknowledgeStateUpdate(stateUpdateSig, this.stateRound);
    }
}

export class ReadyToPlayAcknowledgeStateUpdate extends ReadyToPlayStateUpdate implements IAcknowledgeStateUpdate {
    constructor(public readonly stateUpdateSig: string, public readonly stateRound: number) {
        super(stateRound);
    }

    storeUpdateAction(stateUpdate: string, stateUpdateSig: string, moveCtr: number, round: number) {
        // TODO: add the channel sig for the latest move
    }
}
