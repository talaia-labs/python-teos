const StateChannel = artifacts.require("StateChannel");
const RockPaperScissors = artifacts.require("RockPaperScissors");

module.exports = function(deployer) {
    deployer.deploy(StateChannel, [], 10).then(() => {
        deployer.deploy(RockPaperScissors, 100, 25, 10, StateChannel.address);
    });
};