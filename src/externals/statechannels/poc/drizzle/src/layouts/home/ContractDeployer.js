import React, { Component } from "react";
import { PropTypes } from "prop-types";
import { drizzleConnect } from "drizzle-react";

// TODO: we should have an app container as well
// we should be able to deploy any contract, by passing in the abi and the name
class ContractDeployer extends Component {
    constructor(props) {
        super(props);
        this.deployContract = this.deployContract.bind(this);
    }

    deployContract() {
        this.props.deployContract(this.context.drizzle);
    }

    render() {
        return (
            <div>
                <button onClick={this.deployContract}>Deploy {this.props.contractName}</button>
                {this.props.children}
            </div>
        );
    }
}

ContractDeployer.contextTypes = {
    drizzle: PropTypes.object
};

const stateChannelMapStateToProps = state => {
    return {
        contractName: "StateChannel"
    };
};

const stateChannelMapDispatchToProps = dispatch => {
    return {
        deployContract: drizzle => dispatch({ type: "ADD_STATE_CHANNEL", drizzle })
    };
};

const rpsMapStateToProps = state => {
    return {
        contractName: "RockPaperScissors"
    };
};

const rpsMapDispatchToProps = dispatch => {
    return {
        deployContract: drizzle => dispatch({ type: "ADD_RPS", drizzle })
    };
};

export const StateChannelDeployer = drizzleConnect(
    ContractDeployer,
    stateChannelMapStateToProps,
    stateChannelMapDispatchToProps
);
export const RpsDeployer = drizzleConnect(ContractDeployer, rpsMapStateToProps, rpsMapDispatchToProps);
