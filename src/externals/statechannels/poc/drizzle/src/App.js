import React, { Component } from "react";
import OtherProviderSwitch from "./layouts/home/OtherProviderSwitch";
import { hot } from "react-hot-loader";

// Styles
import "./css/oswald.css";
import "./css/open-sans.css";
import "./css/pure-min.css";
import "./css/app.css";

class App extends Component {
    render() {
        return <OtherProviderSwitch />;
    }
}

// export default App;
export default hot(module)(App);
