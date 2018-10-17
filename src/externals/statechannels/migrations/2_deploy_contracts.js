const BattleShipWithoutBoard = artifacts.require("./BattleShipWithoutBoard.sol");
const StateChannelFactory = artifacts.require("./StateChannelFactory.sol");

module.exports = async (deployer, network, accounts) => {
    //    await deployer.deploy(StateChannelFactory, [accounts[1], accounts[2]], 20, {from: accounts[6]})
    if (network === "production") {
        await deployer.deploy(StateChannelFactory, { from: accounts[6], gas: 9000000 });
        await deployer.deploy(BattleShipWithoutBoard, accounts[1], accounts[2], 20, {
            from: accounts[5]
            //        gas: 9000000
        });
    }
};
