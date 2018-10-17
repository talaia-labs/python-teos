// TODO: null state?

const appReducer = (state = { contracts: {}, signatures: [] }, action) => {
    if (action.type === "STORE_APP_ACCOUNT") {
        return { ...state, account: action.account };
    } else if (action.type === "ADD_CONTRACT_ADDRESS") {
        return {
            ...state,
            contracts: {
                ...state.contracts,
                [action.name]: {
                    ...state.contracts[action.name],
                    address: action.address
                }
            }
        };
    } else if (action.type === "STORE_SIGNATURE") {
        return {
            ...state,
            signatures: [
                ...state.signatures,
                {
                    round: action.round,
                    hstate: action.hstate,
                    signature: action.signature
                }
            ]
        };
    } else {
        return state;
    }
};

export default appReducer;
