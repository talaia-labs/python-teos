import React, { Component, Children } from "react";
import { PropTypes } from "prop-types"

export const DrizzleProvider = React.createContext();

export class DrizzleProvider2 extends Component {
    static propTypes = {
        drizzle: PropTypes.object.isRequired
    };

    // you must specify what you’re adding to the context
    static childContextTypes = {
        drizzle: PropTypes.object.isRequired,
        drizzleStore: PropTypes.object.isRequired
    };

    getChildContext() {
        return { drizzle: this.props.drizzle, drizzleStore: this.props.drizzle.store };
    }

    render() {
        // `Children.only` enables us not to add a <div /> for nothing
        return Children.only(this.props.children);
    }
}

export default DrizzleProvider;
