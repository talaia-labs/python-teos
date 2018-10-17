pragma solidity ^0.4.2;

import "truffle/Assert.sol";
import "truffle/DeployedAddresses.sol";
import "../contracts/RockPaperScissors.sol";
import "./RpsProxy.sol";
import "./ExecutionProxy.sol";
import "../contracts/StateChannel.sol";

contract Test_RockPaperScissors_Commit {
    uint256 public initialBalance = 10 ether;
    uint256 depositAmount = 25;
    uint256 betAmount = 100;
    uint256 commitAmount = depositAmount + betAmount;
    uint256 commitAmountGreater = commitAmount + 13;
    
    uint256 revealSpan = 10;

    // TODO: test greater \deposit amounts

    // TODO: test that explicit stages are respected
    // test that only two commits are allowed

    bytes32 rand1 = "abc";
    bytes32 rand2 = "123";

    function commitmentRock(address sender) private view returns (bytes32) {
        return keccak256(abi.encodePacked(sender, RockPaperScissors.Choice.Rock, rand1));
    }
    function commitmentPaper(address sender) private view returns (bytes32) {
        return keccak256(abi.encodePacked(sender, RockPaperScissors.Choice.Paper, rand2));
    }

    function createStateChannel() private returns (StateChannel) {
        address[] memory adds;
        return new StateChannel(adds, 10);
    }

    function testCommitIncreasesBalance() public {
        
        RockPaperScissors rps = new RockPaperScissors(betAmount, depositAmount, revealSpan, createStateChannel());
        uint256 balanceBefore = address(rps).balance;
        rps.commit.value(commitAmount)(commitmentRock(this));
        uint256 balanceAfter = address(rps).balance;

        Assert.equal(balanceAfter - balanceBefore, commitAmount, "Balance not increased by commit amount.");
        Assert.equal(address(this).balance, initialBalance - commitAmount, "Sender acount did not decrease by bet amount.");
    }

    function testCommitIncreasesBalanceOnlyByBetAmount() public {
        RockPaperScissors rps = new RockPaperScissors(betAmount, depositAmount, revealSpan, createStateChannel());
        RpsProxy proxy = new RpsProxy(rps);
        uint256 balanceBefore = address(rps).balance;
        proxy.commit.value(commitAmountGreater)(commitmentRock(proxy));
        uint256 balanceAfter = address(rps).balance;

        Assert.equal(balanceAfter - balanceBefore, commitAmount, "Balance not increased by commit amount when greater commit supplied.");
        Assert.equal(address(proxy).balance, commitAmountGreater - commitAmount, "Sender account did not receive excess.");
    }

    function testCommitReturnsAllWhenCallingFallbackErrors() public {
        RockPaperScissors rps = new RockPaperScissors(betAmount, depositAmount, revealSpan, createStateChannel());
        ExecutionProxy executionProxy = new ExecutionProxy(rps);
        
        rps.commit.value(commitAmount)(commitmentRock(executionProxy));
        RockPaperScissors(executionProxy).commit.value(commitAmountGreater)(commitmentPaper(executionProxy));
        bool result = executionProxy.execute();

        Assert.isFalse(result, "Commit did not fail when fallback implemented with failure on commit call greater than bet.");
        Assert.equal(address(executionProxy).balance, commitAmountGreater, "Caller was not fully refunded when fallback function fails.");
    }


    function testCommitStoresSenderAndCommitmentHashedWithSender() public {
        RockPaperScissors rps = new RockPaperScissors(betAmount, depositAmount, revealSpan, createStateChannel());
        rps.commit.value(commitAmount)(commitmentRock(this));
        bytes32 commitment;
        RockPaperScissors.Choice choice;
        address playerAddress;
        (playerAddress, commitment, choice) = rps.players(0); 
        Assert.equal(commitment, commitmentRock(this), "Commitment not stored against sender address.");
    }

    function testCommitStoresMultipleSendersAndCommitments() public {
        RockPaperScissors rps = new RockPaperScissors(betAmount, depositAmount, revealSpan, createStateChannel());
        ExecutionProxy executionProxy = new ExecutionProxy(rps);
        
        rps.commit.value(commitAmount)(commitmentRock(this));
        RockPaperScissors(executionProxy).commit.value(commitAmount)(commitmentPaper(executionProxy));
        bool result = executionProxy.execute();


        bytes32 commitment1;
        RockPaperScissors.Choice choice1;
        address playerAddress1;
        (playerAddress1, commitment1, choice1) = rps.players(0); 

        bytes32 commitment2;
        RockPaperScissors.Choice choice2;
        address playerAddress2;
        (playerAddress2, commitment2, choice2) = rps.players(1); 

        Assert.isTrue(result, "Execution proxy commit did not succeed.");

        Assert.notEqual(address(executionProxy), address(this), "Execution proxy address is the same as 'this' address");
        Assert.equal(commitment1, commitmentRock(this), "Commit does not store first commitment.");
        Assert.equal(commitment2, commitmentPaper(executionProxy), "Commit does not store second commitment.");
        Assert.equal(address(rps).balance, commitAmount * 2, "Stored value not equal to twice the commit amount.");
    }

    function testCommitRequiresNoMoreThanTwoSenders() public {
        RockPaperScissors rps = new RockPaperScissors(betAmount, depositAmount, revealSpan, createStateChannel());
        ExecutionProxy executionProxy = new ExecutionProxy(rps);
        rps.commit.value(commitAmount)(commitmentRock(this));
        rps.commit.value(commitAmount)(commitmentRock(this));
        
        // TODO: make sure the execution proxy is refunded
        RockPaperScissors(executionProxy).commit.value(commitAmount)(commitmentPaper(executionProxy));
        bool result = executionProxy.execute();

        Assert.isFalse(result, "Third commit did not throw.");
        Assert.equal(address(executionProxy).balance, commitAmount, "Not all of balance returned after fault.");
    }

    function testCommitRequiresSenderBetGreaterThanOrEqualContractBet() public {
        RockPaperScissors rps = new RockPaperScissors(betAmount, depositAmount, revealSpan, createStateChannel());
        ExecutionProxy executionProxy = new ExecutionProxy(rps);

        RockPaperScissors(executionProxy).commit.value(commitAmount - 1)(commitmentPaper(executionProxy));
        bool result = executionProxy.execute();

        Assert.isFalse(result, "Commit amount less than contact bet amount did not throw.");
        Assert.equal(address(executionProxy).balance, commitAmount - 1, "Not all of balance returned after fault.");
    }
}