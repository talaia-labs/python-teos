export interface IAppointmentRequest {
    stateUpdate: IStateUpdate;
    expiryPeriod: number;
}

export interface IAppointment {
    stateUpdate: IStateUpdate;
    startTime: number;
    endTime: number;
}

export interface IStateUpdate {
    signatures: string[];
    hashState: string;
    round: number;
    contractAddress: string;
}

// TODO: tests for these
export function parseAppointment(obj: any) {
    if (!obj) throw new Error("Appointment not defined.");
    propertyExistsAndIsOfType("expiryPeriod", "number", obj);
    doesPropertyExist("stateUpdate", obj);
    isStateUpdate(obj["stateUpdate"]);
    return obj as IAppointmentRequest;
}
function isStateUpdate(obj: any) {
    if (!obj) throw new Error("State update does not exist.");
    propertyExistsAndIsOfType("hashState", "string", obj);
    propertyExistsAndIsOfType("round", "number", obj);
    propertyExistsAndIsOfType("contractAddress", "string", obj);
    doesPropertyExist("signatures", obj);
    isArrayOfStrings(obj["signatures"])
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
    if (!obj[property]) throw new Error(`${property} not defined.`);
}

function isPropertyOfType(property: string, basicType: string, obj: any) {
    if (typeof obj[property] !== basicType) {
        throw new Error(`${property} is of type: ${typeof obj[property]} not ${basicType}.`);
    }
}
