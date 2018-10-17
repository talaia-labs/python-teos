import React from "react";
import { drizzleConnect } from "drizzle-react";

const EventComponent = props => {
    if (props.event) console.log(props.event.returnValues);
    return <div />;
};

const rpsMapStateToProps = state => {
    return {
        event:
            state.contracts.RockPaperScissors &&
            state.contracts.RockPaperScissors.events &&
            state.contracts.RockPaperScissors.events[state.contracts.RockPaperScissors.events.length - 1]
    };
};

const stateChannelMapStateToProps = state => {
    return {
        event:
            state.contracts.StateChannel &&
            state.contracts.StateChannel.events &&
            state.contracts.StateChannel.events[state.contracts.StateChannel.events.length - 1]
    };
};

export const RpsEvents = drizzleConnect(EventComponent, rpsMapStateToProps);
export const StateChannelEvents = drizzleConnect(EventComponent, stateChannelMapStateToProps);
