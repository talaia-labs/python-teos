const StateChannel = artifacts.require("./StateChannel.sol");
const RockPaperScissors = artifacts.require("./RockPaperScissors.sol");

module.exports = function(deployer) {
    deployer.deploy(StateChannel, [], 10).then(() => {
        deployer.deploy(RockPaperScissors, 100, 25, 10, StateChannel.address);
    });
};
