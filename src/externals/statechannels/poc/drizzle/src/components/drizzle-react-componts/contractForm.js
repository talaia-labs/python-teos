import { drizzleConnect } from "drizzle-react";
import React, { Component } from "react";
import PropTypes from "prop-types";
import Web3Util from "web3-utils";

/*
 * Create component.
 */

class ContractForm extends Component {
    constructor(props, context) {
        super(props);

        this.handleInputChange = this.handleInputChange.bind(this);
        this.handleSubmit = this.handleSubmit.bind(this);

        this.contracts = context.drizzle.contracts;

        // Get the contract ABI
        const abi = this.contracts[this.props.contract].abi;

        this.inputs = [];
        var initialState = {};

        // Iterate over abi for correct function.
        for (var i = 0; i < abi.length; i++) {
            if (abi[i].name === this.props.method) {
                this.inputs = abi[i].inputs;

                for (let j = 0; j < this.inputs.length; j++) {
                    initialState[this.inputs[j].name] = "";
                }

                break;
            }
        }

        this.state = initialState;
    }

    handleSubmit() {
        // hack for bytes32 arg
        let currentState = Object.assign({}, this.state);
        if (currentState.blindingFactor) {
            currentState.blindingFactor = Web3Util.toHex(currentState.blindingFactor);
        }

        // hack for comma separated arrays
        let sendData = Object.values(currentState)
            .map(p => {
                if (p.indexOf(",") !== -1) {
                    // contains a comma, perform a split and wrap in an array
                    return p.split(",");
                } else return p;
            })

        sendData = sendData === undefined ? [] : sendData;

        if (this.props.sendArgs) {
            this.contracts[this.props.contract].methods[this.props.method].cacheSend(...sendData, this.props.sendArgs);
        } else {
            this.contracts[this.props.contract].methods[this.props.method].cacheSend(...sendData);
        }
    }

    handleInputChange(event) {
        this.setState({ [event.target.name]: event.target.value });
    }

    translateType(type) {
        // use this for recognising types
        // https://github.com/ethereum/web3.js/blob/1.0ES6/packages/web3-eth-abi/src/index.js

        switch (true) {
            // case /^uint/.test(type):
            //     return "number";
            //     break;
            // case /^string/.test(type) || /^bytes/.test(type):
            //     return "text";
            //     break;
            // case /^bool/.test(type):
            //     return "checkbox";
            //     break;
            default:
                return "text";
        }
    }

    render() {
        return (
            <form className="pure-form pure-form-stacked">
                {this.inputs.map((input, index) => {
                    var inputType = this.translateType(input.type);
                    var inputLabel = this.props.labels ? this.props.labels[index] : input.name;
                    // check if input type is struct and if so loop out struct fields as well
                    return (
                        <input
                            key={input.name}
                            type={inputType}
                            name={input.name}
                            value={this.state[input.name]}
                            placeholder={inputLabel}
                            onChange={this.handleInputChange}
                        />
                    );
                })}
                <button key="submit" className="pure-button" type="button" onClick={this.handleSubmit}>
                    Submit
                </button>
            </form>
        );
    }
}

ContractForm.contextTypes = {
    drizzle: PropTypes.object
};

/*
 * Export connected component.
 */

const mapStateToProps = state => {
    return {
        contracts: state.contracts
    };
};

export default drizzleConnect(ContractForm, mapStateToProps);
