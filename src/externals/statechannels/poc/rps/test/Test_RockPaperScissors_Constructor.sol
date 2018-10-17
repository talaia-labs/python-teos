pragma solidity ^0.4.2;

import "truffle/Assert.sol";
import "truffle/DeployedAddresses.sol";
import "../contracts/RockPaperScissors.sol";
import "../contracts/StateChannel.sol";

contract Test_RockPaperScissors_Constructor {
    uint256 public initialBalance = 10 ether;
    uint256 commitAmount = 100;
    uint256 depositAmount = 25;
    uint256 revealSpan = 10;

    function createStateChannel() private returns (StateChannel) {
        address[] memory adds;
        return new StateChannel(adds, 10);
    }

    function testConstructorSetsBet() public {
        RockPaperScissors rps = new RockPaperScissors(commitAmount, depositAmount, revealSpan, createStateChannel());
        
        Assert.equal(rps.bet(), commitAmount, "Contract bet amount does not equal supplied bet amount.");
    }

    function testConstructorSetsDeposit() public {
        RockPaperScissors rps = new RockPaperScissors(commitAmount, depositAmount, revealSpan, createStateChannel());
        
        Assert.equal(rps.deposit(), depositAmount, "Contract desposit amount does not equal supplied deposit amount.");
    }

    function testConstructorSetRevealSpan() public {
        RockPaperScissors rps = new RockPaperScissors(commitAmount, depositAmount, revealSpan, createStateChannel());
        
        Assert.equal(rps.revealSpan(), revealSpan, "Contract reveal span amount does not equal supplied reveal span amount.");
    }
}