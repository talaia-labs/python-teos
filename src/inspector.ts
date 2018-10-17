import Web3 from "web3"
const StateChannel = require("./statechannels/contracts/StateChannel.json");

// given an appointment inspect it to see if it's valid for PISA
// 1. Assess the signature of the contract
// 2. Assess the participants of the channel to see if the appointee is valid
// 3. Assess that the appointment has indeed been signed by these participants
// 4. Check that the state round >= round in channel
// 5. Check that expiry is positive / we have time to respond
// 6. Check that the channel is ok state - not dispute
// 7. Check that the expiry period is greater than the channel settle time eg. we have time to respond
// 8. Check that the channel settle time is reasonable, not too small
// 9. If so, we sign a new appointment

interface IAppointment {
    hashState: string,
    round: number,
    contractAddress: string,
    signature: string,
    expiryDate
}

// to be valid for pisa it needs to have a set s
class Inspector {
    constructor(private readonly web3: Web3) { }

    inspect(appointment: IAppointment) {
        try {
            // find the contract and assess it's signature
            // TODO: check that web3 throws an error here
            const contract = new this.web3.eth.Contract(StateChannel.abi, appointment.contractAddress);
            
            
        }


    }
}