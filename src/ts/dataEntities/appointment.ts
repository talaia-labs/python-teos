export interface IAppointmentRequest {
    stateUpdate: IStateUpdate,
    expiryPeriod: number
}

export interface IAppointment  {
    stateUpdate: IStateUpdate,
    startTime: number;
    endTime: number
}

export interface IStateUpdate {
    signatures: string[],
    hashState: string,
    round: number,
    contractAddress: string,
}