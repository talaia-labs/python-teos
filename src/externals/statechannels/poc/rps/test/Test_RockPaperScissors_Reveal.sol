pragma solidity ^0.4.2;

import "truffle/Assert.sol";
import "truffle/DeployedAddresses.sol";
import "../contracts/RockPaperScissors.sol";
import "./ExecutionProxy.sol";
import "../contracts/StateChannel.sol";
import "../contracts/StateChannel.sol";

contract Test_RockPaperScissors_Reveal {
    uint256 public initialBalance = 10 ether;
    
    uint256 depositAmount = 25;
    uint256 betAmount = 100;
    uint256 commitAmount = depositAmount + betAmount;
    
    
    uint256 revealSpan = 10;
    bytes32 rand1 = "abc";
    bytes32 rand2 = "123";

    function commitmentRock(address sender) view private returns (bytes32) {
        return keccak256(abi.encodePacked(sender, RockPaperScissors.Choice.Rock, rand1));
    }
    function commitmentPaper(address sender) view private returns (bytes32) {
        return keccak256(abi.encodePacked(sender, RockPaperScissors.Choice.Paper, rand2));
    }
    function createStateChannel() private returns (StateChannel) {
        address[] memory adds;
        return new StateChannel(adds, 10);
    }
    
    function commitPlayers(RockPaperScissors rps) public 
        returns(ExecutionProxy player1, ExecutionProxy player2) {
        player1 = new ExecutionProxy(rps);
        player2 = new ExecutionProxy(rps);
        RockPaperScissors(player1).commit.value(commitAmount)(commitmentRock(player1));
        RockPaperScissors(player2).commit.value(commitAmount)(commitmentPaper(player2));
        player1.execute();
        player2.execute();

        return (player1, player2);
    }

    // TODO: test that commit correctly sets the address

    function testReveal() public {
        RockPaperScissors rps = new RockPaperScissors(betAmount, depositAmount, revealSpan, createStateChannel());
        ExecutionProxy player1;
        ExecutionProxy player2;
        (player1, player2) = commitPlayers(rps);

        RockPaperScissors(player1).reveal(RockPaperScissors.Choice.Rock, rand1);
        bool result1 = player1.execute();

        bytes32 commitment1;
        RockPaperScissors.Choice choice1;
        address playerAddress1;
        (playerAddress1, commitment1, choice1) = rps.players(0);

        Assert.isTrue(result1, "Could not reveal player 1 rock.");
        Assert.equal(uint256(choice1), uint256(RockPaperScissors.Choice.Rock), "Player 1 did not have rock revealed as choice.");
        Assert.equal(uint(rps.revealDeadline()), uint(block.number + revealSpan), "Deadline not updated.");

        RockPaperScissors(player2).reveal(RockPaperScissors.Choice.Paper, rand2);
        bool result2 = player2.execute();

        bytes32 commitment2;
        RockPaperScissors.Choice choice2;
        address playerAddress2;
        (playerAddress2, commitment2, choice2) = rps.players(1);

        Assert.isTrue(result2, "Could not reveal player 2 paper.");
        Assert.equal(uint(choice2), uint(RockPaperScissors.Choice.Paper), "Player 2 did not have paper revealed as choice.");
    }

    //TODO: maybe also consider checking that player 1 had nothing untoward occur to them

    function testRevealRevertsUnknownSender() public {
        RockPaperScissors rps = new RockPaperScissors(betAmount, depositAmount, revealSpan, createStateChannel());
        ExecutionProxy player1;
        ExecutionProxy player2;
        (player1, player2) = commitPlayers(rps);

        ExecutionProxy nonPlayer = new ExecutionProxy(rps);
        RockPaperScissors(nonPlayer).reveal(RockPaperScissors.Choice.Rock, rand1);
        bool result = nonPlayer.execute();

        Assert.isFalse(result, "Non player was allowed to reveal");
        Assert.equal(uint(rps.revealDeadline()), uint(0), "Deadline was updated.");
    }

    //TODO: test - not in solidity - what happens when int 4 is sent to a contract.
    // is it kicked out?

    function testRevealRevertsInvalidLowerChoice() public {
        RockPaperScissors rps = new RockPaperScissors(betAmount, depositAmount, revealSpan, createStateChannel());
        ExecutionProxy player1 = new ExecutionProxy(rps);
        ExecutionProxy player2 = new ExecutionProxy(rps);
        RockPaperScissors(player1).commit.value(commitAmount)(keccak256(abi.encodePacked(player1, RockPaperScissors.Choice.None, rand1)));
        RockPaperScissors(player2).commit.value(commitAmount)(commitmentPaper(player2));
        player1.execute();
        player2.execute();
        RockPaperScissors(player1).reveal(RockPaperScissors.Choice.None, rand1);
        bool result1 = player1.execute();

        Assert.isFalse(result1, "Player allowed to reveal '0' as choice.");
        Assert.equal(uint(rps.revealDeadline()), uint(0), "Deadline was updated.");
    }


    // //TODO: test that addresses have not changed

    function testRevealPlayerCannotRevealOtherPlayer() public {
        RockPaperScissors rps = new RockPaperScissors(betAmount, depositAmount, revealSpan, createStateChannel());
        ExecutionProxy player1;
        ExecutionProxy player2;
        (player1, player2) = commitPlayers(rps);
        
        RockPaperScissors(player2).reveal(RockPaperScissors.Choice.Rock, rand1);
        bool result1 = player2.execute();
        Assert.isFalse(result1, "Player 2 allowed to reveal player 1.");
        bytes32 commitment;
        RockPaperScissors.Choice choice;
        address playerAddress;
        (playerAddress, commitment, choice) = rps.players(0);
        //TODO: 
        Assert.equal(uint(choice), uint(RockPaperScissors.Choice.None), "player 2 allowed to update choice of player 1.");
    }
}