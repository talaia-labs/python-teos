import React from "react";
import Web3Utils from "web3-utils";
import { drizzleConnect } from "drizzle-react";
import { PropTypes } from "prop-types";

class GameControls extends React.Component {
    // create a commitment
    constructor(props, context) {
        super(props, context);

        this.state = { commitment: "" };
        this.blindingFactorInput = React.createRef();
        this.choiceInput = React.createRef();
        this.commit = this.commit.bind(this);

        this.roundInput = React.createRef();
        this.hstateInput = React.createRef();
        this.hashAndSign = this.hashAndSign.bind(this);

        this.transformSig = this.transformSig.bind(this);
    }

    hashAndSign(e) {
        // stop the form submitting
        e.preventDefault();

        this.props.addSignature(this.context.drizzle, this.roundInput.current.value, this.hstateInput.current.value);
    }

    commit(e) {
        // stop the form submitting
        e.preventDefault();

        // create a commitment
        if (!this.blindingFactorInput.current.value) console.log("No blind");
        if (!this.choiceInput.current.value) console.log("No choice selected");

        let choice = this.choiceInput.current.value;
        let rand = Web3Utils.fromAscii(this.blindingFactorInput.current.value);

        let commitment = Web3Utils.soliditySha3(
            { t: "address", v: this.props.account },
            { t: "uint8", v: choice },
            { t: "bytes32", v: rand }
        );

        this.setState({ commitment });
    }
    transformSig(sig) {
        const removedHexNotation = sig.slice(2);
        var r = `0x${removedHexNotation.slice(0, 64)}`;
        var s = `0x${removedHexNotation.slice(64, 128)}`;
        var v = `0x${removedHexNotation.slice(128, 130)}`;
        return `${v},${r},${s}`;
    }

    // sign a hstate
    render() {
        return (
            <form className="pure-form">
                <div>
                    <input type="text" placeholder="choice" ref={this.choiceInput} />
                    <input type="text" placeholder="blindingFactor" ref={this.blindingFactorInput} />
                    <button className="pure-button" onClick={this.commit}>
                        Create commitment
                    </button>
                    choice
                    <div>{this.state.commitment}</div>
                </div>
                <div>
                    <input type="text" placeholder="round" ref={this.roundInput} />
                    <input type="text" placeholder="hstate" ref={this.hstateInput} />
                    <button className="pure-button" onClick={this.hashAndSign}>
                        Hash and sign
                    </button>
                    <ul>
                        {this.props.signatures.map((h, i) => (
                            <li key={i}>{`${h.round}:${h.hstate}:${this.transformSig(h.signature)}`}</li>
                        ))}
                    </ul>
                </div>
            </form>
        );
    }
}

GameControls.contextTypes = {
    drizzle: PropTypes.object
};

const mapStateToProps = state => {
    return {
        account: state.app.account,
        stateChannelAddress: state.app.contracts.StateChannel && state.app.contracts.StateChannel.address,
        signatures: state.app.signatures
    };
};

const mapDispatchtoProps = dispatch => {
    return {
        addSignature: (drizzle, round, hstate) => dispatch({ type: "ADD_SIGNATURE", drizzle, round, hstate })
    };
};

export default drizzleConnect(GameControls, mapStateToProps, mapDispatchtoProps);
