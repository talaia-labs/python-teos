import React, { Component } from "react";
import { PropTypes } from "prop-types";
import { drizzleConnect } from "drizzle-react";
import { SimpleDisplayData, SimpleDisplayForm } from "./displayHelpers";
import { StateChannelEvents } from "./events";

const StateChannelDisplayData = ({ method, methodArgs }) => (
    <SimpleDisplayData method={method} contract="StateChannel" methodArgs={methodArgs} />
);

const StateChannelDisplayForm = ({ method, account }) => {
    const sendArgs = { from: account };
    return <SimpleDisplayForm method={method} contract="StateChannel" sendArgs={sendArgs} />;
};

class StateChannel extends Component {
    render() {
        if (!this.context.drizzle.contracts.StateChannel) {
            return null;
        }

        return (
            <div id="stateChannel">
                <StateChannelEvents />
                <div>
                    <StateChannelDisplayData method="disputePeriod" />
                    <StateChannelDisplayData method="status" />
                    <StateChannelDisplayData method="bestRound" />
                    <StateChannelDisplayData method="t_start" />
                    <StateChannelDisplayData method="deadline" />
                    <StateChannelDisplayData method="hstate" />
                    <StateChannelDisplayData method="plist" methodArgs={[0]} />
                    <StateChannelDisplayData method="plist" methodArgs={[1]} />
                </div>

                <div>
                    <StateChannelDisplayForm
                        method="triggerDispute"
                        account={this.props.store.getState().app.account}
                    />
                    <StateChannelDisplayForm method="setstate" account={this.props.store.getState().app.account} />
                    <StateChannelDisplayForm method="resolve" account={this.props.store.getState().app.account} />
                </div>
            </div>
        );
    }
}

const mapStateToProps = state => {
    return {
        StateChannel: state.contracts.StateChannel,
        address: state.app.contracts.StateChannel
    };
};

StateChannel.contextTypes = {
    drizzle: PropTypes.object
};

export default drizzleConnect(StateChannel, mapStateToProps);
