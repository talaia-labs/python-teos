import React from "react";
import { drizzleConnect } from "drizzle-react";
import { PropTypes } from "prop-types";
import { SimpleDisplayData, SimpleDisplayForm } from "./displayHelpers";
import { RpsEvents } from "./events"

const RpsDisplayData = ({ method, methodArgs }) => (
    <SimpleDisplayData method={method} contract="RockPaperScissors" methodArgs={methodArgs} />
);

const RpsDisplayForm = ({ method, sendArgs }) => {
    return <SimpleDisplayForm method={method} contract="RockPaperScissors" sendArgs={sendArgs} />;
};

const RockPaperScissors = (props, context) => {
    if (!context.drizzle.contracts.RockPaperScissors) {
        return <div>Not yet</div>;
    }

    const fromArgs = { from: props.store.getState().app.account, gas: 2000000 };
    const valueArgs = { ...fromArgs, value: 125 };
    return (
        <div id="rps">
            <RpsEvents/>
            <div>
                <RpsDisplayData method="bet" />
                <RpsDisplayData method="deposit" />
                <RpsDisplayData method="revealSpan" />
                <RpsDisplayData method="players" methodArgs={[0]} />
                <RpsDisplayData method="players" methodArgs={[1]} />
                <RpsDisplayData method="revealDeadline" />
                <RpsDisplayData method="stage" />
                <RpsDisplayData method="stateChannel" />
                <RpsDisplayData method="locked" />
                <RpsDisplayData method="getStateHash" />
            </div>
            <div>
                <RpsDisplayForm method="lock" sendArgs={fromArgs} />
                <RpsDisplayForm method="unlock" sendArgs={fromArgs} />
                <RpsDisplayForm method="commit" sendArgs={valueArgs} />
                <RpsDisplayForm method="reveal" sendArgs={fromArgs} />
                <RpsDisplayForm method="distribute" sendArgs={fromArgs} />
            </div>
        </div>
    );
};

const mapStateToProps = state => {
    return {
        RockPaperScissors: state.contracts.RockPaperScissors
    };
};

RockPaperScissors.contextTypes = {
    drizzle: PropTypes.object
};

export default drizzleConnect(RockPaperScissors, mapStateToProps);
