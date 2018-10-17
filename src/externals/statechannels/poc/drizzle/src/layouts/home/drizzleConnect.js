import { connect } from "react-redux";
import React from "react";
import { DrizzleProvider } from "./drizzleProvider";
import { PropTypes } from "prop-types";

export default function drizzleConnect(Component, ...args) {
    var ConnectedWrappedComponent = connect(...args)(Component);

    const DrizzledComponent = props => {
        return (
            <DrizzleProvider.Consumer>
                {value => {
                    return <ConnectedWrappedComponent {...props} store={value.store} drizzle={value} />;
                }}
            </DrizzleProvider.Consumer>
        );
    };

    return DrizzledComponent;
}

export function drizzleConnect2(Component, ...args) {
    var ConnectedWrappedComponent = connect(...args)(Component);

    const DrizzledComponent = (props, context) => (
        <ConnectedWrappedComponent {...props} store={context.drizzleStore} drizzle={context.drizzle} />
    );

    DrizzledComponent.contextTypes = {
        drizzleStore: PropTypes.object,
        drizzle: PropTypes.object
    };

    return DrizzledComponent;
}
