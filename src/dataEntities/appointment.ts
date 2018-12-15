import { utils } from "ethers";

export interface IAppointmentRequest {
    stateUpdate: IStateUpdate;
    expiryPeriod: number;
}

export interface IAppointment {
    stateUpdate: IStateUpdate;
    startTime: number;
    endTime: number;
    inspectionTime: number;
}

export interface IStateUpdate {
    signatures: string[];
    hashState: string;
    round: number;
    contractAddress: string;
}

export class PublicValidationError extends Error {}

export function parseAppointment(obj: any) {
    if (!obj) throw new PublicValidationError("Appointment not defined.");
    propertyExistsAndIsOfType("expiryPeriod", "number", obj);
    doesPropertyExist("stateUpdate", obj);
    isStateUpdate(obj["stateUpdate"]);
    return obj as IAppointmentRequest;
}

function isStateUpdate(obj: any) {
    if (!obj) throw new PublicValidationError("stateUpdate does not exist.");
    propertyExistsAndIsOfType("hashState", "string", obj);
    const hexLength = utils.hexDataLength(obj.hashState);
    if (hexLength !== 32) {
        throw new PublicValidationError(`Invalid bytes32: ${obj.hashState}`);
    }

    propertyExistsAndIsOfType("round", "number", obj);
    propertyExistsAndIsOfType("contractAddress", "string", obj);
    try {
        // is this a valid address?
        utils.getAddress(obj.contractAddress);
    } catch (doh) {
        throw new PublicValidationError(
            `${obj.contractAddress} is not a valid address.`
        );
    }

    doesPropertyExist("signatures", obj);
    isArrayOfStrings(obj["signatures"]);
}

function isArrayOfStrings(obj: any) {
    if (obj instanceof Array) {
        obj.forEach(function(item) {
            if (typeof item !== "string") {
                return false;
            }
        });
        return true;
    }
    return false;
}

function propertyExistsAndIsOfType(property: string, basicType: string, obj: any) {
    doesPropertyExist(property, obj);
    isPropertyOfType(property, basicType, obj);
}

function doesPropertyExist(property: string, obj: any) {
    if (typeof obj[property] === typeof undefined) throw new PublicValidationError(`${property} not defined.`);
}

function isPropertyOfType(property: string, basicType: string, obj: any) {
    if (typeof obj[property] !== basicType) {
        throw new PublicValidationError(`${property} is of type: ${typeof obj[property]} not ${basicType}.`);
    }
}
