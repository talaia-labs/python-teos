import React, { Component } from "react";
import { AppContainer } from "./appContainer";
import instances from "./drizzleInstances";
import { DrizzleProvider2 } from "./drizzleProvider";

export default class OtherProviderSwitch extends Component {
    constructor(props) {
        super(props);
        this.state = { instance: "REMOTE" };
        this.clickMe = this.clickMe.bind(this);
    }

    clickMe() {
        let nextInstance = this.state.instance === "LOCAL" ? "REMOTE" : "LOCAL";

        this.setState({ instance: nextInstance });
    }

    render() {
        return (
            <div>
                {/* <button onClick={this.clickMe}>Switch provider</button> */}
                {/* <div>{"Current provider: " + this.state.instance}</div> */}
                <div>
                    
                        <DrizzleProvider2 drizzle={instances.theLocalDrizzle}>
                            
                                <AppContainer />
                            
                        </DrizzleProvider2>
                    
                        <DrizzleProvider2 drizzle={instances.theRemoteDrizzle}>
                            <AppContainer />
                        </DrizzleProvider2>
                    
                </div>
            </div>
        );
    }
}
