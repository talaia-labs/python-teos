import React from "react";
import { StateChannelDeployer, RpsDeployer } from "./ContractDeployer";
import StateChannel from "./StateChannel";
import Rps from "./rockPaperScissors";
import GameControls from "./gameControls";

export const AppContainer = () => {
    return (
        <div id="app">
            <div>
                <StateChannelDeployer>
                    <StateChannel />
                </StateChannelDeployer>
                <GameControls />
            </div>
            <RpsDeployer>
                <Rps />
            </RpsDeployer>
        </div>
    );
};
